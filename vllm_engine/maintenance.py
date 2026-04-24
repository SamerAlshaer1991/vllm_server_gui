from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from typing import Any

from .config import PROJECT_DIR
from .envfiles import ensure_runtime_dirs, load_backend_env
from .schema import clear_schema_cache, load_schema

SYNC_SCRIPT = PROJECT_DIR / "tools" / "sync_engine_args.py"


def _clear_files(
    target_dir: Path,
    *,
    item_label: str,
    active_path: str | None = None,
) -> dict[str, Any]:
    active = Path(active_path).resolve() if active_path else None
    deleted_count = 0
    skipped_active = False

    for path in sorted(target_dir.rglob("*"), reverse=True):
        if path.is_file():
            if active is not None and path.resolve() == active:
                skipped_active = True
                continue
            path.unlink(missing_ok=True)
            deleted_count += 1
        elif path.is_dir():
            try:
                path.rmdir()
            except OSError:
                pass

    message = f"Cleared {deleted_count} {item_label}{'s' if deleted_count != 1 else ''}."
    if skipped_active:
        message += f" The active running {item_label} was kept."
    return {
        "ok": True,
        "message": message,
        "deleted_count": deleted_count,
        "skipped_active": skipped_active,
    }


def clear_logs(*, active_log_path: str | None = None) -> dict[str, Any]:
    env = load_backend_env()
    paths = ensure_runtime_dirs(env)
    result = _clear_files(
        paths["LOGS_DIR"],
        item_label="log file",
        active_path=active_log_path,
    )
    result["logs_dir"] = str(paths["LOGS_DIR"])
    return result


def clear_scripts() -> dict[str, Any]:
    env = load_backend_env()
    paths = ensure_runtime_dirs(env)
    result = _clear_files(paths["SCRIPTS_DIR"], item_label="script file")
    result["scripts_dir"] = str(paths["SCRIPTS_DIR"])
    return result


def sync_arguments() -> dict[str, Any]:
    env = load_backend_env()
    python_bin = env.get("PYTHON_BIN") or sys.executable
    result = subprocess.run(
        [python_bin, str(SYNC_SCRIPT)],
        cwd=PROJECT_DIR,
        env=env,
        capture_output=True,
        text=True,
        check=True,
    )
    clear_schema_cache()
    schema = load_schema()
    return {
        "ok": True,
        "message": (
            f"Synced serve arguments. Loaded {schema['argument_count']} args across "
            f"{schema['section_count']} sections."
        ),
        "stdout": result.stdout.strip(),
        "stderr": result.stderr.strip(),
        "generated_at": schema["generated_at"],
        "argument_count": schema["argument_count"],
        "section_count": schema["section_count"],
    }
