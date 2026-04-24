from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock
from typing import Any

from .config import PROFILES_PATH


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _normalize_name(name: str) -> str:
    cleaned = " ".join((name or "").strip().split())
    if not cleaned:
        raise ValueError("Profile name cannot be empty.")
    return cleaned[:80]


@dataclass
class ProfileStore:
    path: Path = PROFILES_PATH

    def __post_init__(self) -> None:
        self._lock = Lock()

    def _read(self) -> list[dict[str, Any]]:
        if not self.path.exists():
            return []
        return json.loads(self.path.read_text(encoding="utf-8"))

    def _write(self, profiles: list[dict[str, Any]]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(profiles, indent=2), encoding="utf-8")

    def list_profiles(self) -> list[dict[str, Any]]:
        with self._lock:
            return sorted(self._read(), key=lambda item: item["name"].lower())

    def save_profile(
        self,
        *,
        name: str,
        state: dict[str, dict[str, Any]],
        command_preview: str,
        selected_count: int,
    ) -> dict[str, Any]:
        normalized = _normalize_name(name)
        profile = {
            "name": normalized,
            "state": state,
            "command_preview": command_preview,
            "selected_count": selected_count,
            "saved_at": _utc_now(),
        }
        with self._lock:
            profiles = [item for item in self._read() if item["name"] != normalized]
            profiles.append(profile)
            self._write(profiles)
        return profile

    def get_profile(self, name: str) -> dict[str, Any]:
        normalized = _normalize_name(name)
        with self._lock:
            for profile in self._read():
                if profile["name"] == normalized:
                    return profile
        raise KeyError(f"Profile '{normalized}' was not found.")

    def delete_profile(self, name: str) -> None:
        normalized = _normalize_name(name)
        with self._lock:
            profiles = self._read()
            filtered = [item for item in profiles if item["name"] != normalized]
            if len(filtered) == len(profiles):
                raise KeyError(f"Profile '{normalized}' was not found.")
            self._write(filtered)
