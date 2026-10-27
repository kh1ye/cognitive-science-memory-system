"""FastAPI application and static server for Cognitive Science Memory System."""

from __future__ import annotations

import argparse
import os
import threading
import webbrowser
from contextlib import asynccontextmanager
from pathlib import Path

import uvicorn
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException

from cognitive_memory import Memory
from conversation_agent import ConversationAgent

from .middleware import RequestPolicyMiddleware
from .responses import error_response
from .routers import architecture, chat, demo, evolution, memories, retrieval, system
from .settings import SERVICE_NAME

ROOT = Path(__file__).resolve().parents[1]
STATIC_ROOT = ROOT / "frontend" / "dist"
DEFAULT_DB = ROOT / "memory_product" / "data" / "memory_demo.db"


def create_app(
    db_path: str | Path = DEFAULT_DB,
    *,
    service: Memory | None = None,
    demo_token: str | None = None,
    chat_db_path: str | Path | None = None,
    chat_model=None,
) -> FastAPI:
    """Create the service; demo seeding requires an explicit token.

    ``None`` reads COGNITIVE_MEMORY_DEMO_TOKEN; an empty token disables seeding.
    Lifespan owns only the Memory instance it creates.
    """

    @asynccontextmanager
    async def lifespan(application: FastAPI):
        application.state.memory = service if service is not None else Memory(db_path)
        conversation = None
        try:
            session_path = chat_db_path
            if session_path is None:
                session_path = os.getenv("CONVERSATION_DB_PATH") or (
                    ":memory:"
                    if str(db_path) == ":memory:" or service is not None
                    else Path(db_path).with_name(Path(db_path).stem + "_sessions.db")
                )
            conversation = ConversationAgent(
                application.state.memory, session_path, model=chat_model
            )
            application.state.conversation_agent = conversation
            yield
        finally:
            if conversation is not None:
                conversation.close()
            if service is None:
                application.state.memory.close()

    application = FastAPI(
        title=SERVICE_NAME, description=SERVICE_NAME, version="1.0.0", lifespan=lifespan
    )

    application.state.demo_token = (
        os.environ.get("COGNITIVE_MEMORY_DEMO_TOKEN", "")
        if demo_token is None
        else demo_token
    ).strip()
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

    for router in (architecture.router, memories.router, retrieval.router, system.router, chat.router, evolution.router):
        application.include_router(router)
    if application.state.demo_token:
        application.include_router(demo.router)

    @application.api_route(
        "/api/{path:path}",
        methods=["GET", "POST", "DELETE", "PUT", "PATCH"],
        include_in_schema=False,
    )
    def unknown_api(path: str):
        return error_response("接口不存在", 404, "not_found")

    # Register last so /docs, /openapi.json and API routes remain reachable.
    if (STATIC_ROOT / "index.html").is_file():
        application.mount(
            "/", StaticFiles(directory=STATIC_ROOT, html=True), name="frontend"
        )
    else:

        @application.get("/", include_in_schema=False)
        def frontend_not_built():
            return JSONResponse(
                {
                    "message": "前端尚未构建。请执行 npm --prefix frontend ci 和 npm --prefix frontend run build。"
                },
                status_code=503,
            )

    return application


app = create_app()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=f"Run {SERVICE_NAME}")
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
    print(f"{SERVICE_NAME}\nWeb UI: {url}\nAPI docs: {url}/docs\nSQLite: {args.db}")
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
