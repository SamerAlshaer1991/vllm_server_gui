#!/usr/bin/env python3
from __future__ import annotations

import argparse
import ast
import json
import os
import re
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

PROJECT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_DIR))

from vllm_engine.config import DATA_PATH  # noqa: E402
from vllm_engine.envfiles import load_backend_env  # noqa: E402

SERVE_ARGS_URL = "https://docs.vllm.ai/en/latest/configuration/serve_args/#cli-arguments"
ENGINE_ARGS_URL = "https://docs.vllm.ai/en/latest/configuration/engine_args/"
SECTION_PATTERN = re.compile(r"^[A-Za-z][A-Za-z0-9 ]*:$")
ARGUMENT_PATTERN = re.compile(r"^\s{2}(?P<header>\S.*?)(?:\s{2,}(?P<help>.+))?$")
LIST_VALUE_PATTERN = re.compile(r"\[[A-Z0-9_\-]+ \.\.\.\]")
JSON_HINTS = (
    "json",
    "dictionary",
    "dict",
    "keys passed individually",
    "configuration.",
    "configurations",
)
CUSTOM_VALUE_HINTS = (
    "custom values can be supported via plugins",
    "name registered in",
)
REPEATABLE_HINTS = (
    "we accept multiple",
    "multiple --middleware arguments",
)


def slugify(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")


def title_case_section(value: str) -> str:
    if value in {"positional arguments", "options"}:
        return value.title()
    return value


def split_top_level(value: str) -> list[str]:
    parts: list[str] = []
    buffer: list[str] = []
    depth = 0
    openings = {"{": "}", "[": "]", "(": ")"}
    closings = set(openings.values())
    for char in value:
        if char in openings:
            depth += 1
        elif char in closings and depth > 0:
            depth -= 1
        if char == "," and depth == 0:
            parts.append("".join(buffer).strip())
            buffer = []
            continue
        buffer.append(char)
    if buffer:
        parts.append("".join(buffer).strip())
    return [item for item in parts if item]


def collapse_lines(lines: list[str]) -> str:
    parts: list[str] = []
    paragraph: list[str] = []
    for raw in lines:
        line = raw.strip()
        if not line:
            if paragraph:
                parts.append(" ".join(paragraph))
                paragraph = []
            continue
        if line.startswith("- "):
            if paragraph:
                parts.append(" ".join(paragraph))
                paragraph = []
            parts.append(line)
            continue
        if line.endswith(":"):
            if paragraph:
                parts.append(" ".join(paragraph))
                paragraph = []
            parts.append(line)
            continue
        paragraph.append(line)
    if paragraph:
        parts.append(" ".join(paragraph))
    return "\n".join(parts).strip()


def extract_default(help_text: str) -> tuple[str, str]:
    stripped = help_text.strip()
    marker = "(default:"
    index = stripped.lower().rfind(marker)
    if index == -1 or not stripped.endswith(")"):
        return "", stripped
    default = stripped[index + len(marker) : -1].strip()
    cleaned = stripped[:index].rstrip()
    return ('""' if default == "" else default), cleaned


def extract_header_choices(value_spec: str) -> list[str]:
    brace_match = re.search(r"\{([^{}]+)\}", value_spec)
    if brace_match:
        return [item.strip() for item in brace_match.group(1).split(",") if item.strip()]
    list_match = re.search(r"(\[[^\]]+\])", value_spec)
    if list_match:
        try:
            parsed = ast.literal_eval(list_match.group(1))
        except (SyntaxError, ValueError):
            return []
        if isinstance(parsed, list) and all(isinstance(item, str) for item in parsed):
            return parsed
    return []


def extract_help_choices(help_text: str) -> list[str]:
    choices: list[str] = []
    for line in help_text.splitlines():
        stripped = line.strip()
        match = re.match(r'- (?:"([^"]+)"|`([^`]+)`|(None))(?:\s|:|$)', stripped)
        if match:
            choice = next(group for group in match.groups() if group)
            choices.append(choice)
    return choices


def dedupe(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        result.append(value)
    return result


def infer_repeatable(help_text: str) -> bool:
    lowered = help_text.lower()
    return any(hint in lowered for hint in REPEATABLE_HINTS)


def infer_control(
    *,
    is_boolean: bool,
    accepts_multiple: bool,
    repeatable: bool,
    allows_custom_value: bool,
    choices: list[str],
    default: str,
    help_text: str,
) -> str:
    if is_boolean:
        return "boolean"
    if repeatable or accepts_multiple:
        return "textarea"
    if choices and not allows_custom_value:
        return "select"
    lowered = help_text.lower()
    if default.startswith("{") or default.startswith("[") or len(default) > 120:
        return "textarea"
    if any(hint in lowered for hint in JSON_HINTS):
        return "textarea"
    return "text"


def initial_value_for(
    *,
    control: str,
    default: str,
    choices: list[str],
) -> str:
    if control == "boolean":
        return default.lower() if default in {"True", "False"} else "true"
    if control == "select" and default in choices:
        return default
    if control == "text" and default not in {"", "None"} and len(default) <= 80:
        return default
    return ""


def placeholder_for(
    *,
    control: str,
    default: str,
    accepts_multiple: bool,
    repeatable: bool,
) -> str:
    if accepts_multiple or repeatable:
        return "One value per line or comma-separated"
    if default in {"", "None"}:
        return "Enter a value"
    if control == "textarea":
        return "Enter JSON or a longer value"
    return default


def parse_flag_header(section_title: str, header: str) -> dict[str, Any]:
    if section_title.lower() == "positional arguments":
        name = header.split()[0]
        return {
            "label": header,
            "names": [name],
            "aliases": [],
            "primary_flag": "",
            "true_flag": None,
            "false_flag": None,
            "value_spec": "",
            "is_positional": True,
            "is_boolean": False,
            "accepts_multiple": False,
        }

    variants = split_top_level(header)
    parsed_variants: list[tuple[str, str]] = []
    names: list[str] = []
    aliases: list[str] = []
    positive: list[str] = []
    negative: list[str] = []
    accepts_multiple = False
    bare_flag = True

    for variant in variants:
        flag, _, remainder = variant.partition(" ")
        value_spec = remainder.strip()
        parsed_variants.append((flag, value_spec))
        names.append(flag)
        if flag.startswith("--no-"):
            negative.append(flag)
        elif flag.startswith("--"):
            positive.append(flag)
        elif flag.startswith("-"):
            aliases.append(flag)
        if value_spec:
            bare_flag = False
        if LIST_VALUE_PATTERN.search(value_spec):
            accepts_multiple = True

    primary_flag = positive[0] if positive else (aliases[0] if aliases else names[0])
    value_spec = next(
        (
            variant_value
            for flag, variant_value in parsed_variants
            if flag == primary_flag and variant_value
        ),
        "",
    )
    if not value_spec:
        value_spec = next((variant_value for _, variant_value in parsed_variants if variant_value), "")
    return {
        "label": header,
        "names": names,
        "aliases": aliases,
        "primary_flag": primary_flag,
        "true_flag": positive[0] if bare_flag and positive else None,
        "false_flag": negative[0] if negative else None,
        "value_spec": value_spec,
        "is_positional": False,
        "is_boolean": bare_flag,
        "accepts_multiple": accepts_multiple,
    }


def build_argument(section: dict[str, Any], header: str, help_lines: list[str]) -> dict[str, Any]:
    parsed = parse_flag_header(section["title"], header)
    raw_help = collapse_lines(help_lines)
    default, help_text = extract_default(raw_help)
    header_choices = extract_header_choices(parsed["value_spec"])
    help_choices = extract_help_choices(help_text)
    choices = dedupe(header_choices + help_choices)
    allows_custom_value = any(hint in header.lower() for hint in CUSTOM_VALUE_HINTS) or any(
        hint in help_text.lower() for hint in CUSTOM_VALUE_HINTS
    )
    repeatable = infer_repeatable(help_text)
    control = infer_control(
        is_boolean=parsed["is_boolean"],
        accepts_multiple=parsed["accepts_multiple"],
        repeatable=repeatable,
        allows_custom_value=allows_custom_value,
        choices=choices,
        default=default,
        help_text=help_text,
    )

    if parsed["accepts_multiple"] or repeatable:
        input_note = "Input format: enter one value per line or separate values with commas."
        if help_text:
            help_text = f"{help_text}\n\n{input_note}"
        else:
            help_text = input_note

    key_source = parsed["primary_flag"] or parsed["names"][0]
    return {
        "key": key_source.lstrip("-").replace("-", "_"),
        "label": parsed["label"],
        "names": parsed["names"],
        "aliases": parsed["aliases"],
        "primary_flag": parsed["primary_flag"],
        "true_flag": parsed["true_flag"],
        "false_flag": parsed["false_flag"],
        "choices": choices,
        "default": default,
        "control": control,
        "initial_value": initial_value_for(control=control, default=default, choices=choices),
        "placeholder": placeholder_for(
            control=control,
            default=default,
            accepts_multiple=parsed["accepts_multiple"],
            repeatable=repeatable,
        ),
        "help_markdown": help_text,
        "source_url": section["source_url"],
        "section_title": section["title"],
        "is_positional": parsed["is_positional"],
        "accepts_multiple": parsed["accepts_multiple"],
        "repeatable": repeatable,
    }


def parse_help_sections(help_text: str) -> list[dict[str, Any]]:
    sections: list[dict[str, Any]] = []
    current_section: dict[str, Any] | None = None
    section_notes: list[str] = []
    current_header: str | None = None
    current_help_lines: list[str] = []

    def flush_argument() -> None:
        nonlocal current_header, current_help_lines
        if current_section is not None and current_header is not None:
            current_section["args"].append(
                build_argument(current_section, current_header, current_help_lines)
            )
        current_header = None
        current_help_lines = []

    def flush_notes() -> None:
        nonlocal section_notes
        if current_section is not None and section_notes and not current_section["args"]:
            current_section["description"] = collapse_lines(section_notes)
            current_section["note_markdown"] = current_section["description"]
        section_notes = []

    for raw_line in help_text.splitlines():
        if SECTION_PATTERN.match(raw_line):
            flush_argument()
            flush_notes()
            title = title_case_section(raw_line[:-1])
            source_url = SERVE_ARGS_URL if title in {"Positional Arguments", "Options", "Frontend"} else ENGINE_ARGS_URL
            current_section = {
                "id": slugify(title),
                "title": title,
                "description": "",
                "note_markdown": "",
                "source_url": source_url,
                "args": [],
            }
            sections.append(current_section)
            continue

        if current_section is None:
            continue

        stripped = raw_line.lstrip()
        if not stripped:
            if current_header is not None:
                current_help_lines.append("")
            elif not current_section["args"]:
                section_notes.append("")
            continue

        if current_section["title"] == "Positional Arguments":
            is_argument = bool(re.match(r"^  \S+\s{2,}", raw_line))
        else:
            is_argument = bool(re.match(r"^  -", raw_line))

        if is_argument:
            flush_argument()
            flush_notes()
            match = ARGUMENT_PATTERN.match(raw_line)
            current_header = match.group("header") if match else stripped
            inline_help = match.group("help") if match else ""
            current_help_lines = [inline_help] if inline_help else []
            continue

        if current_header is not None:
            current_help_lines.append(stripped)
        elif not current_section["args"]:
            section_notes.append(stripped)

    flush_argument()
    flush_notes()
    return [section for section in sections if section["args"]]


def find_vllm_binary(explicit: str | None) -> str:
    if explicit:
        return explicit
    env = load_backend_env()
    candidates = [
        env.get("VLLM_BIN"),
        shutil.which("vllm"),
        "/opt/ai/.venv/bin/vllm",
    ]
    for candidate in candidates:
        if not candidate:
            continue
        resolved = shutil.which(candidate) if not Path(candidate).is_absolute() else candidate
        if resolved and Path(resolved).exists():
            return str(resolved)
    raise FileNotFoundError("Could not find a vllm binary. Set VLLM_BIN or pass --vllm-bin.")


def capture_help_text(vllm_bin: str) -> str:
    env = dict(load_backend_env())
    env.setdefault("PATH", os.environ.get("PATH", ""))
    env["COLUMNS"] = "240"
    result = subprocess.run(
        [vllm_bin, "serve", "--help=all"],
        capture_output=True,
        check=True,
        env=env,
        text=True,
    )
    return result.stdout


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate the serve GUI schema from local `vllm serve --help=all` output."
    )
    parser.add_argument(
        "--output",
        default=str(DATA_PATH),
        help="Path to write the generated schema JSON.",
    )
    parser.add_argument(
        "--vllm-bin",
        default=None,
        help="Path to the vllm executable. Defaults to VLLM_BIN, PATH, or /opt/ai/.venv/bin/vllm.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    vllm_bin = find_vllm_binary(args.vllm_bin)
    help_text = capture_help_text(vllm_bin)
    sections = parse_help_sections(help_text)
    data = {
        "command_parts": ["vllm", "serve"],
        "command_display": "vllm serve",
        "source_command": "vllm serve --help=all",
        "source_urls": [
            {"label": "Serve Args Docs", "url": SERVE_ARGS_URL},
            {"label": "Engine Args Docs", "url": ENGINE_ARGS_URL},
        ],
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "section_count": len(sections),
        "argument_count": sum(len(section["args"]) for section in sections),
        "sections": sections,
    }
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    print(
        f"Wrote {data['argument_count']} serve args across {data['section_count']} sections "
        f"to {output_path}"
    )


if __name__ == "__main__":
    main()
