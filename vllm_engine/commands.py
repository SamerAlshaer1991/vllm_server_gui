from __future__ import annotations

import re
import shlex
from typing import Any

from .schema import iter_arguments

MULTI_VALUE_SPLIT = re.compile(r"[\n,]+")


def _normalize_value(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value).strip()


def _split_multi_value(raw: str) -> list[str]:
    return [item.strip() for item in MULTI_VALUE_SPLIT.split(raw) if item.strip()]


def build_command_parts(
    state: dict[str, dict[str, Any]],
    *,
    executable: str = "vllm",
) -> list[str]:
    positionals: list[str] = []
    options: list[str] = []

    for argument in iter_arguments():
        item = state.get(argument["key"], {})
        if not item.get("enabled"):
            continue

        control = argument["control"]
        raw_value = _normalize_value(item.get("value", argument.get("initial_value", "")))

        if control == "boolean":
            if raw_value == "true" and argument.get("true_flag"):
                options.append(argument["true_flag"])
            elif raw_value == "false" and argument.get("false_flag"):
                options.append(argument["false_flag"])
            continue

        if argument.get("is_positional"):
            if raw_value:
                positionals.append(raw_value)
            continue

        if argument.get("repeatable"):
            for value in _split_multi_value(raw_value):
                options.extend([argument["primary_flag"], value])
            continue

        if argument.get("accepts_multiple"):
            values = _split_multi_value(raw_value)
            if values:
                options.append(argument["primary_flag"])
                options.extend(values)
            continue

        if raw_value:
            options.extend([argument["primary_flag"], raw_value])

    return [executable, "serve", *positionals, *options]


def format_command(parts: list[str]) -> str:
    return shlex.join(parts)
