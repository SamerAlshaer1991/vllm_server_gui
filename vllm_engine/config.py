from __future__ import annotations

from pathlib import Path

APP_NAME = "VLLM_Engine"
PACKAGE_DIR = Path(__file__).resolve().parent
PROJECT_DIR = PACKAGE_DIR.parent
DATA_DIR = PACKAGE_DIR / "data"
DATA_PATH = DATA_DIR / "serve_builder_schema.json"
PROFILES_PATH = DATA_DIR / "profiles.json"
ENV_PATH = PROJECT_DIR / ".env"
ENV_EXAMPLE_PATH = PROJECT_DIR / ".env.example"
STATIC_DIR = PACKAGE_DIR / "static"
TEMPLATE_DIR = PACKAGE_DIR / "templates"
DEFAULT_GUI_PORT = 8088
