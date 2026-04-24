from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any

from dotenv import dotenv_values

from .config import ENV_PATH, PROJECT_DIR

VAR_PATTERN = re.compile(r"\$(\w+)|\$\{([^}]+)\}")


def _expand_value(raw: str, variables: dict[str, str]) -> str:
    def replace(match: re.Match[str]) -> str:
        key = match.group(1) or match.group(2) or ""
        return variables.get(key, "")

    return VAR_PATTERN.sub(replace, raw)


def load_backend_env() -> dict[str, str]:
    resolved = dict(os.environ)
    if ENV_PATH.exists():
        for key, raw_value in dotenv_values(ENV_PATH, interpolate=False).items():
            if not key:
                continue
            resolved[key] = _expand_value(raw_value or "", resolved)

    project_root = resolved.setdefault("PROJECT_ROOT", str(PROJECT_DIR))
    resolved.setdefault("SCRIPTS_DIR", f"{project_root}/scripts")
    resolved.setdefault("LOGS_DIR", f"{project_root}/logs")
    resolved.setdefault("PIDS_DIR", f"{project_root}/pids")
    resolved.setdefault("XDG_CACHE_HOME", f"{project_root}/.cache")
    resolved.setdefault("XDG_CONFIG_HOME", f"{resolved['XDG_CACHE_HOME']}/config")
    resolved.setdefault("XDG_DATA_HOME", f"{resolved['XDG_CACHE_HOME']}/data")
    resolved.setdefault("HF_HOME", f"{resolved['XDG_CACHE_HOME']}/huggingface")
    resolved.setdefault("HF_HUB_CACHE", f"{resolved['HF_HOME']}/hub")
    resolved.setdefault("TORCH_HOME", f"{resolved['XDG_CACHE_HOME']}/torch")
    env_prefix = resolved.setdefault("ENV_PREFIX", "/opt/ai/.venv")
    path_prefix = f"{env_prefix}/bin"
    if path_prefix not in resolved.get("PATH", ""):
        resolved["PATH"] = f"{path_prefix}:{resolved.get('PATH', '')}".strip(":")
    resolved.setdefault("PYTHON_BIN", f"{env_prefix}/bin/python")
    resolved.setdefault("VLLM_BIN", f"{env_prefix}/bin/vllm")
    resolved.setdefault("RAY_BIN", f"{env_prefix}/bin/ray")
    resolved.setdefault("HF_TOKEN", "")
    return resolved


def ensure_runtime_dirs(env: dict[str, str]) -> dict[str, Path]:
    keys = [
        "PROJECT_ROOT",
        "SCRIPTS_DIR",
        "LOGS_DIR",
        "PIDS_DIR",
        "XDG_CACHE_HOME",
        "XDG_CONFIG_HOME",
        "XDG_DATA_HOME",
        "HF_HOME",
        "HF_HUB_CACHE",
        "TORCH_HOME",
    ]
    paths = {key: Path(env[key]).expanduser() for key in keys}
    for path in paths.values():
        path.mkdir(parents=True, exist_ok=True)
    return paths


def backend_env_summary() -> dict[str, Any]:
    env = load_backend_env()
    return {
        "env_path": str(ENV_PATH),
        "project_root": env["PROJECT_ROOT"],
        "env_prefix": env["ENV_PREFIX"],
        "logs_dir": env["LOGS_DIR"],
        "scripts_dir": env["SCRIPTS_DIR"],
        "pids_dir": env["PIDS_DIR"],
    }
