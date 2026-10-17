"""FastAPI HTTP adapter and static server for the memory demo."""

from __future__ import annotations

import argparse
import threading
import webbrowser
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated

import uvicorn
from fastapi import Depends, FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException

from cognitive_memory import Memory
from demo.seed import seed_demo

from .middleware import RequestPolicyMiddleware
from .schemas import MemoryRequest, NamespaceRequest, SearchRequest

ROOT = Path(__file__).resolve().parents[1]
STATIC_ROOT = ROOT / "demo" / "static"
DEFAULT_DB = ROOT / "memory_product" / "data" / "memory_demo.db"


def error_response(message: str, status: int = 400, error: str = "validation_error"):
    return JSONResponse({"error": error, "message": message}, status_code=status)


def get_memory(request: Request) -> Memory:
    return request.app.state.memory


MemoryDependency = Annotated[Memory, Depends(get_memory)]


def create_app(
    db_path: str | Path = DEFAULT_DB, *, service: Memory | None = None
) -> FastAPI:
    """Create an app; lifespan owns only the Memory instance it creates."""

    @asynccontextmanager
    async def lifespan(application: FastAPI):
        application.state.memory = service if service is not None else Memory(db_path)
        try:
            yield
        finally:
            if service is None:
                application.state.memory.close()

    application = FastAPI(
        title="Cognitive Memory API", version="1.0.0", lifespan=lifespan
    )

    application.add_middleware(RequestPolicyMiddleware)

    @application.exception_handler(RequestValidationError)
    async def validation_error(request: Request, exc: RequestValidationError):
        # Preserve the existing UI's 400/error/message contract.
        errors = exc.errors()
        message = "; ".join(
            f"{'.'.join(str(part) for part in item['loc'])}: {item['msg']}"
            for item in errors
        )
        return error_response(message)

    @application.exception_handler(ValueError)
    async def domain_error(request: Request, exc: ValueError):
        return error_response(str(exc))

    @application.exception_handler(Exception)
    async def internal_error(request: Request, exc: Exception):
        return JSONResponse(
            {"error": "internal_error", "message": str(exc)},
            status_code=500,
            headers={"Cache-Control": "no-store"},
        )

    @application.exception_handler(HTTPException)
    async def http_error(request: Request, exc: HTTPException):
        if exc.status_code == 400:
            return error_response(str(exc.detail))
        if exc.status_code == 404 and request.url.path.startswith("/api/"):
            return error_response("接口不存在", 404, "not_found")
        return JSONResponse(
            {"detail": exc.detail}, status_code=exc.status_code, headers=exc.headers
        )

    @application.get("/api/health")
    def health():
        return {"status": "ok", "service": "cognitive-memory-demo", "version": "1.0.0"}

    @application.get("/api/config")
    def config(memory: MemoryDependency, user_id: str = "demo-user"):
        return memory.stats(user_id)["config"]

    @application.get("/api/stats")
    def stats(memory: MemoryDependency, user_id: str = "demo-user"):
        return memory.stats(user_id)

    @application.get("/api/memories")
    def memories(
        memory: MemoryDependency,
        user_id: str = "demo-user",
        include_archived: bool = False,
    ):
        return {
            "items": memory.list_memories(user_id, include_archived=include_archived)
        }

    @application.get("/api/audit")
    def audit(memory: MemoryDependency, user_id: str = "demo-user"):
        return {"items": memory.list_audit(user_id)}

    @application.post("/api/memories", status_code=201)
    def add_memory(payload: MemoryRequest, memory: MemoryDependency):
        return memory.add_memory(payload.model_dump(exclude_unset=True))

    @application.post("/api/search")
    def search(payload: SearchRequest, memory: MemoryDependency):
        return memory.search(
            payload.user_id,
            payload.query,
            payload.top_k,
            payload.active_goal,
            payload.recent_focus,
        )

    @application.post("/api/maintenance/retention")
    def retention(memory: MemoryDependency, payload: NamespaceRequest | None = None):
        return memory.run_retention((payload or NamespaceRequest()).user_id)

    @application.post("/api/demo/seed")
    def seed(memory: MemoryDependency, payload: NamespaceRequest | None = None):
        user_id = (payload or NamespaceRequest()).user_id
        return {"events": seed_demo(memory, user_id), "stats": memory.stats(user_id)}

    @application.delete("/api/memories/{memory_id}")
    def delete(memory_id: str, memory: MemoryDependency, user_id: str = "demo-user"):
        if memory.delete_memory(user_id, memory_id):
            return {"deleted": True, "memory_id": memory_id}
        return JSONResponse(
            {"deleted": False, "message": "记忆不存在"}, status_code=404
        )

    @application.api_route(
        "/api/{path:path}",
        methods=["GET", "POST", "DELETE", "PUT", "PATCH"],
        include_in_schema=False,
    )
    def unknown_api(path: str):
        return error_response("接口不存在", 404, "not_found")

    # Register last so /docs, /openapi.json and API routes remain reachable.
    application.mount("/", StaticFiles(directory=STATIC_ROOT, html=True), name="demo")
    return application


app = create_app()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run the cognitive memory demo product"
    )
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", default=8765, type=int)
    parser.add_argument("--db", default=str(DEFAULT_DB), help="SQLite path or :memory:")
    parser.add_argument(
        "--open", action="store_true", help="open the browser after startup"
    )
    return parser


def main() -> None:
    args = build_parser().parse_args()
    url = f"http://{args.host}:{args.port}"
    print(f"Web UI: {url}\nAPI docs: {url}/docs\nSQLite: {args.db}")
    timer = None
    if args.open:
        timer = threading.Timer(0.7, lambda: webbrowser.open(url))
        timer.daemon = True
        timer.start()
    try:
        uvicorn.run(create_app(args.db), host=args.host, port=args.port)
    finally:
        if timer is not None:
            timer.cancel()


if __name__ == "__main__":
    main()
