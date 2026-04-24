from __future__ import annotations

import os
import shlex
import signal
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock
from typing import Any

from .commands import build_command_parts, format_command
from .envfiles import ensure_runtime_dirs, load_backend_env


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class RuntimeManager:
    def __init__(self) -> None:
        self._lock = Lock()
        self._process: subprocess.Popen[bytes] | None = None
        self._log_handle: Any | None = None
        self._status: dict[str, Any] = {
            "state": "idle",
            "running": False,
            "message": "No vLLM process is running.",
            "command_display": "vllm serve",
            "command_preview": "vllm serve",
            "pid": None,
            "exit_code": None,
            "started_at": None,
            "finished_at": None,
            "log_path": None,
            "pid_path": None,
            "script_path": None,
        }

    def _close_log_handle_locked(self) -> None:
        if self._log_handle is not None:
            self._log_handle.close()
            self._log_handle = None

    def _remove_pid_file_locked(self) -> None:
        pid_path = self._status.get("pid_path")
        if pid_path:
            Path(pid_path).unlink(missing_ok=True)

    def _refresh_locked(self) -> None:
        if self._process is None:
            log_path = self._status.get("log_path")
            if log_path and not Path(log_path).exists():
                self._status["log_path"] = None
            return
        return_code = self._process.poll()
        if return_code is None:
            self._status["running"] = True
            self._status["state"] = "running"
            return
        self._process = None
        self._close_log_handle_locked()
        self._remove_pid_file_locked()
        self._status.update(
            {
                "running": False,
                "state": "stopped" if return_code == 0 else "failed",
                "exit_code": return_code,
                "finished_at": _utc_now(),
                "pid": None,
                "message": (
                    "The vLLM process exited successfully."
                    if return_code == 0
                    else f"The vLLM process exited with code {return_code}."
                ),
            }
        )

    def _write_launch_script(
        self,
        *,
        script_path: Path,
        project_root: Path,
        command: list[str],
    ) -> None:
        script = "\n".join(
            [
                "#!/usr/bin/env bash",
                "set -euo pipefail",
                f"cd {shlex.quote(str(project_root))}",
                f"if [ -f {shlex.quote(str(project_root / '.env'))} ]; then",
                "  set -a",
                f"  source {shlex.quote(str(project_root / '.env'))}",
                "  set +a",
                "fi",
                f"exec {shlex.join(command)}",
                "",
            ]
        )
        script_path.write_text(script, encoding="utf-8")
        script_path.chmod(0o755)

    def status(self) -> dict[str, Any]:
        with self._lock:
            self._refresh_locked()
            return dict(self._status)

    def run(self, state: dict[str, dict[str, Any]]) -> dict[str, Any]:
        with self._lock:
            self._refresh_locked()
            if self._process is not None:
                raise RuntimeError("A vLLM process is already running.")

            env = load_backend_env()
            paths = ensure_runtime_dirs(env)
            display_command = build_command_parts(state, executable="vllm")
            exec_command = build_command_parts(state, executable=env["VLLM_BIN"])
            timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
            log_path = paths["LOGS_DIR"] / f"vllm_serve_{timestamp}.log"
            pid_path = paths["PIDS_DIR"] / "vllm_serve.pid"
            script_path = paths["SCRIPTS_DIR"] / f"vllm_serve_{timestamp}.sh"

            self._write_launch_script(
                script_path=script_path,
                project_root=paths["PROJECT_ROOT"],
                command=exec_command,
            )
            self._log_handle = log_path.open("ab")
            process = subprocess.Popen(
                ["bash", str(script_path)],
                cwd=paths["PROJECT_ROOT"],
                env=env,
                stdout=self._log_handle,
                stderr=subprocess.STDOUT,
                start_new_session=True,
            )
            pid_path.write_text(str(process.pid), encoding="utf-8")
            self._process = process
            self._status.update(
                {
                    "state": "running",
                    "running": True,
                    "message": "Started `vllm serve`.",
                    "command_display": "vllm serve",
                    "command_preview": format_command(display_command),
                    "pid": process.pid,
                    "exit_code": None,
                    "started_at": _utc_now(),
                    "finished_at": None,
                    "log_path": str(log_path),
                    "pid_path": str(pid_path),
                    "script_path": str(script_path),
                }
            )
            return dict(self._status)

    def stop(self) -> dict[str, Any]:
        with self._lock:
            self._refresh_locked()
            if self._process is None:
                raise RuntimeError("No vLLM process is currently running.")

            process = self._process
            try:
                os.killpg(process.pid, signal.SIGTERM)
                process.wait(timeout=8)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, signal.SIGKILL)
                process.wait(timeout=4)

            self._refresh_locked()
            self._status["message"] = "Stopped `vllm serve`."
            return dict(self._status)
