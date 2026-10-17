"""Small dependency-free HTTP API and static server for the memory demo."""

from __future__ import annotations

import argparse
import json
import mimetypes
import threading
import webbrowser
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

from memory_core import MemoryService


ROOT = Path(__file__).resolve().parent
STATIC_ROOT = ROOT / "static"
DEFAULT_DB = ROOT / "data" / "memory_demo.db"


class MemoryAPIHandler(BaseHTTPRequestHandler):
    server_version = "CognitiveMemoryDemo/1.0"

    @property
    def service(self) -> MemoryService:
        return self.server.memory_service  # type: ignore[attr-defined]

    def log_message(self, fmt: str, *args: object) -> None:
        print(f"[{self.log_date_time_string()}] {self.address_string()} {fmt % args}")

    def _json(self, payload: object, status: int = 200) -> None:
        body = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _read_json(self) -> dict:
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError as exc:
            raise ValueError("Content-Length 无效") from exc
        if length > 1_000_000:
            raise ValueError("请求体过大")
        if length == 0:
            return {}
        try:
            value = json.loads(self.rfile.read(length).decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ValueError("请求体必须是 UTF-8 JSON") from exc
        if not isinstance(value, dict):
            raise ValueError("JSON 顶层必须是对象")
        return value

    def _serve_static(self, request_path: str) -> None:
        relative = "index.html" if request_path == "/" else unquote(request_path.lstrip("/"))
        target = (STATIC_ROOT / relative).resolve()
        try:
            target.relative_to(STATIC_ROOT.resolve())
        except ValueError:
            self.send_error(HTTPStatus.FORBIDDEN)
            return
        if not target.is_file():
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        content = target.read_bytes()
        mime = mimetypes.guess_type(target.name)[0] or "application/octet-stream"
        if mime.startswith("text/") or mime in {"application/javascript", "application/json"}:
            mime += "; charset=utf-8"
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", mime)
        self.send_header("Content-Length", str(len(content)))
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        self.wfile.write(content)

    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        params = parse_qs(parsed.query)
        user_id = params.get("user_id", ["demo-user"])[0]
        try:
            if parsed.path == "/api/health":
                self._json({"status": "ok", "service": "cognitive-memory-demo", "version": "1.0.0"})
            elif parsed.path == "/api/config":
                self._json(self.service.stats(user_id)["config"])
            elif parsed.path == "/api/stats":
                self._json(self.service.stats(user_id))
            elif parsed.path == "/api/memories":
                include_archived = params.get("include_archived", ["false"])[0].lower() == "true"
                self._json({"items": self.service.list_memories(user_id, include_archived=include_archived)})
            elif parsed.path == "/api/audit":
                self._json({"items": self.service.list_audit(user_id)})
            elif parsed.path.startswith("/api/"):
                self._json({"error": "not_found", "message": "接口不存在"}, HTTPStatus.NOT_FOUND)
            else:
                self._serve_static(parsed.path)
        except ValueError as exc:
            self._json({"error": "validation_error", "message": str(exc)}, HTTPStatus.BAD_REQUEST)
        except Exception as exc:  # pragma: no cover - defensive HTTP boundary
            self._json({"error": "internal_error", "message": str(exc)}, HTTPStatus.INTERNAL_SERVER_ERROR)

    def do_POST(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        try:
            payload = self._read_json()
            if parsed.path == "/api/memories":
                self._json(self.service.add_memory(payload), HTTPStatus.CREATED)
            elif parsed.path == "/api/search":
                result = self.service.search(
                    str(payload.get("user_id", "demo-user")),
                    str(payload.get("query", "")),
                    int(payload.get("top_k", 5)),
                    str(payload.get("active_goal", "")),
                    str(payload.get("recent_focus", "")),
                )
                self._json(result)
            elif parsed.path == "/api/maintenance/retention":
                self._json(self.service.run_retention(str(payload.get("user_id", "demo-user"))))
            elif parsed.path == "/api/demo/seed":
                user_id = str(payload.get("user_id", "demo-user"))
                self._json({"events": self.service.seed_demo(user_id), "stats": self.service.stats(user_id)})
            else:
                self._json({"error": "not_found", "message": "接口不存在"}, HTTPStatus.NOT_FOUND)
        except ValueError as exc:
            self._json({"error": "validation_error", "message": str(exc)}, HTTPStatus.BAD_REQUEST)
        except Exception as exc:  # pragma: no cover - defensive HTTP boundary
            self._json({"error": "internal_error", "message": str(exc)}, HTTPStatus.INTERNAL_SERVER_ERROR)

    def do_DELETE(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        params = parse_qs(parsed.query)
        user_id = params.get("user_id", ["demo-user"])[0]
        prefix = "/api/memories/"
        if parsed.path.startswith(prefix):
            memory_id = unquote(parsed.path[len(prefix) :])
            deleted = self.service.delete_memory(user_id, memory_id)
            if deleted:
                self._json({"deleted": True, "memory_id": memory_id})
            else:
                self._json({"deleted": False, "message": "记忆不存在"}, HTTPStatus.NOT_FOUND)
        else:
            self._json({"error": "not_found", "message": "接口不存在"}, HTTPStatus.NOT_FOUND)


class MemoryHTTPServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True

    def __init__(self, address: tuple[str, int], service: MemoryService):
        super().__init__(address, MemoryAPIHandler)
        self.memory_service = service


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the cognitive memory demo product")
    parser.add_argument("--host", default="127.0.0.1", help="listen host (default: 127.0.0.1)")
    parser.add_argument("--port", default=8765, type=int, help="listen port (default: 8765)")
    parser.add_argument("--db", default=str(DEFAULT_DB), help="SQLite path or :memory:")
    parser.add_argument("--open", action="store_true", help="open the browser after startup")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    service = MemoryService(args.db)
    server = MemoryHTTPServer((args.host, args.port), service)
    url = f"http://{args.host}:{args.port}"
    print("认知长期记忆系统演示已启动")
    print(f"Web UI: {url}")
    print(f"Health: {url}/api/health")
    print(f"SQLite: {args.db}")
    print("按 Ctrl+C 停止服务")
    if args.open:
        threading.Timer(0.7, lambda: webbrowser.open(url)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n正在停止服务...")
    finally:
        server.server_close()
        service.close()


if __name__ == "__main__":
    main()

