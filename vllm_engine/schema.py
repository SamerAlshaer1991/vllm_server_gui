from __future__ import annotations

import json
from functools import lru_cache
from typing import Any

from markdown import markdown

from .config import DATA_PATH


def render_markdown(value: str) -> str:
    return markdown(
        value or "",
        extensions=["sane_lists", "fenced_code", "tables"],
        output_format="html5",
    )


def _build_intro_markdown(data: dict[str, Any]) -> str:
    source_lines = [
        f"- [{item['label']}]({item['url']})" for item in data.get("source_urls", [])
    ]
    parts = [
        "### Local Source Of Truth",
        (
            "This page is generated from the installed vLLM CLI by running "
            f"`{data['source_command']}`."
        ),
        (
            f"It currently contains **{data['argument_count']}** args across "
            f"**{data['section_count']}** groups for **`{data['command_display']}`**."
        ),
        f"Last generated: `{data['generated_at']}`",
    ]
    if source_lines:
        parts.append("Supporting docs:\n" + "\n".join(source_lines))
    parts.append(
        "Use the checkbox on any field to decide whether that option should appear in "
        "the generated command preview."
    )
    return "\n\n".join(parts)


def _decorate_argument(section_title: str, argument: dict[str, Any]) -> dict[str, Any]:
    search_text = " ".join(
        [
            section_title,
            argument.get("label", ""),
            " ".join(argument.get("names", [])),
            " ".join(argument.get("choices", [])),
            argument.get("default", ""),
            argument.get("help_markdown", ""),
        ]
    ).lower()
    argument["help_html"] = render_markdown(argument.get("help_markdown", ""))
    argument["search_text"] = search_text
    return argument


@lru_cache(maxsize=1)
def load_schema() -> dict[str, Any]:
    data = json.loads(DATA_PATH.read_text(encoding="utf-8"))
    data["intro_html"] = render_markdown(_build_intro_markdown(data))
    for section in data["sections"]:
        note_source = section.get("note_markdown") or section.get("description", "")
        section["note_html"] = render_markdown(note_source)
        section["args"] = [
            _decorate_argument(section["title"], argument) for argument in section["args"]
        ]
    return data


@lru_cache(maxsize=1)
def load_argument_index() -> dict[str, dict[str, Any]]:
    return {
        argument["key"]: argument
        for section in load_schema()["sections"]
        for argument in section["args"]
    }


def iter_arguments() -> list[dict[str, Any]]:
    return [argument for section in load_schema()["sections"] for argument in section["args"]]


def clear_schema_cache() -> None:
    load_schema.cache_clear()
    load_argument_index.cache_clear()
