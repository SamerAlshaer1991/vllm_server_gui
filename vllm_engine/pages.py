from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .schema import load_schema


@dataclass(frozen=True)
class Page:
    slug: str
    path: str
    aliases: tuple[str, ...]
    title: str
    template_name: str
    command_parts: tuple[str, ...]
    summary: str


SERVE_PAGE = Page(
    slug="serve",
    path="/",
    aliases=("/serve",),
    title="vLLM Serve",
    template_name="vllm_engine.html",
    command_parts=("vllm", "serve"),
    summary="Build, save, preview, and run the local `vllm serve` command.",
)

PAGES = [SERVE_PAGE]


def resolve_page(path: str) -> Page | None:
    normalized = path if path == "/" else path.rstrip("/")
    if normalized in {SERVE_PAGE.path, *SERVE_PAGE.aliases}:
        return SERVE_PAGE
    return None


def build_page_context(page: Page) -> dict[str, Any]:
    schema = load_schema()
    return {
        "page_title": page.title,
        "schema": schema,
        "sections": schema["sections"],
        "source_urls": schema.get("source_urls", []),
        "command_parts": page.command_parts,
        "command_display": " ".join(page.command_parts),
        "command_summary": page.summary,
    }
