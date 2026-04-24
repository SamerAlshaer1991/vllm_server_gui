from __future__ import annotations

import json
import mimetypes
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import subprocess
from urllib.parse import urlparse

from jinja2 import Environment, FileSystemLoader, select_autoescape

from .commands import build_command_parts, format_command
from .config import STATIC_DIR, TEMPLATE_DIR
from .envfiles import backend_env_summary
from .maintenance import clear_logs, sync_arguments
from .pages import PAGES, build_page_context, resolve_page
from .profiles import ProfileStore
from .runtime import RuntimeManager

PROFILE_STORE = ProfileStore()
RUNTIME_MANAGER = RuntimeManager()


def _build_environment() -> Environment:
    return Environment(
        loader=FileSystemLoader(str(TEMPLATE_DIR)),
        autoescape=select_autoescape(("html", "xml")),
    )


def _safe_static_path(url_path: str) -> Path | None:
    relative = url_path.removeprefix("/static/").strip("/")
    candidate = (STATIC_DIR / relative).resolve()
    if not candidate.is_file():
        return None
    if not candidate.is_relative_to(STATIC_DIR.resolve()):
        return None
    return candidate


class AppHandler(BaseHTTPRequestHandler):
    env = _build_environment()

    def do_GET(self) -> None:  # noqa: N802
        self._handle_request(send_body=True)

    def do_HEAD(self) -> None:  # noqa: N802
        self._handle_request(send_body=False)

    def do_POST(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        try:
            if parsed.path == "/api/profiles/save":
                self._handle_profile_save()
                return
            if parsed.path == "/api/profiles/load":
                self._handle_profile_load()
                return
            if parsed.path == "/api/profiles/delete":
                self._handle_profile_delete()
                return
            if parsed.path == "/api/runtime/run":
                self._handle_runtime_run()
                return
            if parsed.path == "/api/runtime/stop":
                self._handle_runtime_stop()
                return
            if parsed.path == "/api/logs/clear":
                self._handle_logs_clear()
                return
            if parsed.path == "/api/schema/sync":
                self._handle_schema_sync()
                return
            self._respond_json(
                HTTPStatus.NOT_FOUND,
                {"ok": False, "message": "API route not found."},
            )
        except KeyError as exc:
            self._respond_json(HTTPStatus.NOT_FOUND, {"ok": False, "message": str(exc)})
        except ValueError as exc:
            self._respond_json(HTTPStatus.BAD_REQUEST, {"ok": False, "message": str(exc)})
        except RuntimeError as exc:
            self._respond_json(HTTPStatus.CONFLICT, {"ok": False, "message": str(exc)})
        except subprocess.CalledProcessError as exc:
            message = exc.stderr.strip() or exc.stdout.strip() or str(exc)
            self._respond_json(HTTPStatus.INTERNAL_SERVER_ERROR, {"ok": False, "message": message})
        except Exception as exc:  # noqa: BLE001
            self._respond_json(
                HTTPStatus.INTERNAL_SERVER_ERROR,
                {"ok": False, "message": str(exc) or "Unexpected server error."},
            )

    def _handle_request(self, *, send_body: bool) -> None:
        parsed = urlparse(self.path)
        if parsed.path == "/api/runtime":
            self._respond_json(
                HTTPStatus.OK,
                {"ok": True, "runtime": RUNTIME_MANAGER.status()},
                send_body=send_body,
            )
            return
        if parsed.path.startswith("/static/"):
            self._serve_static(parsed.path, send_body=send_body)
            return

        page = resolve_page(parsed.path)
        if page is None:
            self._respond_text(HTTPStatus.NOT_FOUND, "Page not found.", send_body=send_body)
            return

        context = build_page_context(page)
        context["pages"] = PAGES
        context["current_page"] = page
        default_parts = build_command_parts({}, executable="vllm")
        context["bootstrap"] = {
            "command_parts": list(page.command_parts),
            "command_display": " ".join(page.command_parts),
            "profiles": PROFILE_STORE.list_profiles(),
            "runtime": RUNTIME_MANAGER.status(),
            "env_summary": backend_env_summary(),
            "command_preview": format_command(default_parts),
            "profile_placeholder": "Serve profile",
            "schema_generated_at": context["schema"]["generated_at"],
        }
        rendered = self.env.get_template(page.template_name).render(**context)
        self._respond_bytes(
            HTTPStatus.OK,
            rendered.encode("utf-8"),
            content_type="text/html; charset=utf-8",
            cache_control="no-store",
            send_body=send_body,
        )

    def _read_json_body(self) -> dict[str, object]:
        length = int(self.headers.get("Content-Length", "0"))
        raw = self.rfile.read(length) if length else b"{}"
        return json.loads(raw.decode("utf-8"))

    def _handle_profile_save(self) -> None:
        payload = self._read_json_body()
        profile = PROFILE_STORE.save_profile(
            name=str(payload.get("name", "")),
            state=payload.get("state", {}) if isinstance(payload.get("state", {}), dict) else {},
            command_preview=str(payload.get("command_preview", "vllm serve")),
            selected_count=int(payload.get("selected_count", 0)),
        )
        self._respond_json(
            HTTPStatus.OK,
            {
                "ok": True,
                "message": f"Saved profile '{profile['name']}'.",
                "profile": profile,
                "profiles": PROFILE_STORE.list_profiles(),
            },
        )

    def _handle_profile_load(self) -> None:
        payload = self._read_json_body()
        profile = PROFILE_STORE.get_profile(str(payload.get("name", "")))
        self._respond_json(
            HTTPStatus.OK,
            {"ok": True, "message": f"Loaded profile '{profile['name']}'.", "profile": profile},
        )

    def _handle_profile_delete(self) -> None:
        payload = self._read_json_body()
        name = str(payload.get("name", ""))
        PROFILE_STORE.delete_profile(name)
        self._respond_json(
            HTTPStatus.OK,
            {
                "ok": True,
                "message": f"Deleted profile '{name}'.",
                "profiles": PROFILE_STORE.list_profiles(),
            },
        )

    def _handle_runtime_run(self) -> None:
        payload = self._read_json_body()
        runtime = RUNTIME_MANAGER.run(
            payload.get("state", {}) if isinstance(payload.get("state", {}), dict) else {},
        )
        self._respond_json(
            HTTPStatus.OK,
            {"ok": True, "message": runtime["message"], "runtime": runtime},
        )

    def _handle_runtime_stop(self) -> None:
        runtime = RUNTIME_MANAGER.stop()
        self._respond_json(
            HTTPStatus.OK,
            {"ok": True, "message": runtime["message"], "runtime": runtime},
        )

    def _handle_logs_clear(self) -> None:
        runtime = RUNTIME_MANAGER.status()
        result = clear_logs(
            active_log_path=runtime.get("log_path") if runtime.get("running") else None,
        )
        self._respond_json(HTTPStatus.OK, result)

    def _handle_schema_sync(self) -> None:
        result = sync_arguments()
        self._respond_json(HTTPStatus.OK, result)

    def _serve_static(self, url_path: str, *, send_body: bool) -> None:
        target = _safe_static_path(url_path)
        if target is None:
            self._respond_text(
                HTTPStatus.NOT_FOUND,
                "Static asset not found.",
                send_body=send_body,
            )
            return
        content_type = mimetypes.guess_type(str(target))[0] or "application/octet-stream"
        self._respond_bytes(
            HTTPStatus.OK,
            target.read_bytes(),
            content_type=content_type,
            cache_control="public, max-age=3600",
            send_body=send_body,
        )

    def _respond_text(self, status: HTTPStatus, body: str, *, send_body: bool) -> None:
        self._respond_bytes(
            status,
            body.encode("utf-8"),
            content_type="text/plain; charset=utf-8",
            cache_control="no-store",
            send_body=send_body,
        )

    def _respond_json(
        self,
        status: HTTPStatus,
        payload: dict[str, object],
        *,
        send_body: bool = True,
    ) -> None:
        self._respond_bytes(
            status,
            json.dumps(payload).encode("utf-8"),
            content_type="application/json; charset=utf-8",
            cache_control="no-store",
            send_body=send_body,
        )

    def _respond_bytes(
        self,
        status: HTTPStatus,
        body: bytes,
        *,
        content_type: str,
        cache_control: str,
        send_body: bool,
    ) -> None:
        self.send_response(status.value)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", cache_control)
        self.end_headers()
        if send_body:
            self.wfile.write(body)


def run_server(host: str, port: int) -> None:
    server = ThreadingHTTPServer((host, port), AppHandler)
    print(f"Serving VLLM_Engine on http://{host}:{port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
