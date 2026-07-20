from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

_MAX_BLOCKS = 4
_MAX_BLOCK_CHARS = 30_000
_MAX_SECTIONS = 12
_MAX_CHARACTERS = 24
_MAX_FIELDS = 20
_MAX_VALUE_CHARS = 2_000

_TEXT_END_RE = re.compile(
    r"<\s*text(?:\s[^>]*)?>\s*(.*?)\s*<\s*end\s*>",
    re.IGNORECASE | re.DOTALL,
)
_STATUS_RE = re.compile(
    r"<\s*status(?:\s[^>]*)?>\s*(.*?)\s*<\s*/\s*status\s*>",
    re.IGNORECASE | re.DOTALL,
)
_SECTION_RE = re.compile(r"^\s*\[([^\]\r\n]{1,80})\]\s*$")
_FIELD_RE = re.compile(r"^\s*([^：:\r\n]{1,80})\s*[：:]\s*(.*?)\s*$")
_STATUS_MARKER_RE = re.compile(r"^__AI_TAVERN_TEXT_STATUS_(\d+)__$")
_EMOJI_SUFFIX_RE = re.compile(r"^(.*?)([\U0001F300-\U0001FAFF\u2600-\u27BF]+)\s*$")


@dataclass(frozen=True)
class _BlockMatch:
    start: int
    end: int
    content: str
    protocol: str


def _clean_text(value: Any, *, limit: int = _MAX_VALUE_CHARS) -> str:
    text = str(value or "").replace("\x00", "").strip()
    return text[:limit]


def _strip_key_icon(raw_key: str) -> tuple[str, str]:
    key = _clean_text(raw_key, limit=80)
    match = re.match(r"^([^\w\u4e00-\u9fff]*)(.*)$", key, flags=re.UNICODE)
    if not match:
        return "", key
    icon = match.group(1).strip()
    label = match.group(2).strip() or key
    return icon[:12], label[:80]


def _section_kind(title: str) -> str:
    compact = re.sub(r"[\s\W_]+", "", title, flags=re.UNICODE).lower()
    if any(token in compact for token in ("角色状态", "人物状态", "characterstatus", "characters")):
        return "characters"
    if any(token in compact for token in ("关系互动", "关系状态", "互动关系", "interaction", "relationship")):
        return "interaction"
    if any(token in compact for token in ("场景氛围", "环境氛围", "氛围", "atmosphere")):
        return "atmosphere"
    if any(token in compact for token in ("环境", "场景信息", "世界信息", "environment")):
        return "environment"
    return "generic"


def _parse_field(line: str) -> dict[str, str] | None:
    match = _FIELD_RE.match(line)
    if not match:
        return None
    icon, label = _strip_key_icon(match.group(1))
    value = _clean_text(match.group(2))
    if not label or not value:
        return None
    field = {"label": label, "value": value}
    if icon:
        field["icon"] = icon
    return field


def _character_header(line: str) -> tuple[str, str]:
    text = _clean_text(line, limit=120)
    match = _EMOJI_SUFFIX_RE.match(text)
    if match and match.group(1).strip():
        return match.group(1).strip()[:100], match.group(2).strip()[:12]
    return text[:100], ""


def _parse_characters(lines: list[str]) -> list[dict[str, Any]]:
    characters: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None

    for raw in lines:
        line = raw.strip()
        if not line:
            continue
        field = _parse_field(line)
        if field:
            if current is None:
                current = {"name": "角色状态", "fields": []}
                characters.append(current)
            if len(current["fields"]) < _MAX_FIELDS:
                current["fields"].append(field)
            continue

        if len(characters) >= _MAX_CHARACTERS:
            continue
        name, badge = _character_header(line)
        if not name:
            continue
        current = {"name": name, "fields": []}
        if badge:
            current["badge"] = badge
        characters.append(current)

    return [item for item in characters if item.get("fields") or item.get("name") != "角色状态"]


def _parse_simple_section(kind: str, title: str, lines: list[str]) -> dict[str, Any]:
    fields: list[dict[str, str]] = []
    text_lines: list[str] = []
    for raw in lines:
        line = raw.strip()
        if not line:
            continue
        field = _parse_field(line)
        if field and len(fields) < _MAX_FIELDS:
            fields.append(field)
        else:
            text_lines.append(_clean_text(line))

    section: dict[str, Any] = {
        "kind": kind,
        "title": _clean_text(title, limit=80),
    }
    if fields:
        section["fields"] = fields
    if text_lines:
        section["text"] = "\n".join(text_lines)[:_MAX_VALUE_CHARS * 2]
    return section


def parse_status_panel(content: str, *, protocol: str) -> dict[str, Any] | None:
    raw = str(content or "")[:_MAX_BLOCK_CHARS]
    lines = raw.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    sections_input: list[tuple[str, str, list[str]]] = []
    current_title = ""
    current_kind = ""
    current_lines: list[str] = []

    def flush() -> None:
        nonlocal current_title, current_kind, current_lines
        if current_title or any(line.strip() for line in current_lines):
            title = current_title or "状态"
            kind = current_kind or "generic"
            sections_input.append((kind, title, current_lines))
        current_title = ""
        current_kind = ""
        current_lines = []

    known_section_seen = False
    section_header_seen = False
    for raw_line in lines:
        line = raw_line.strip()
        if line.startswith("```") and line.rstrip("`").strip() in {"", "html", "text", "status"}:
            continue
        header = _SECTION_RE.match(line)
        if header:
            section_header_seen = True
            flush()
            current_title = _clean_text(header.group(1), limit=80)
            current_kind = _section_kind(current_title)
            known_section_seen = known_section_seen or current_kind != "generic"
            continue
        current_lines.append(raw_line)
    flush()

    if not sections_input:
        return None

    # A <text> tag is generic enough to appear in prose. Only consume it when
    # the body resembles a status protocol. <status> may use a key-value-only body.
    key_value_count = sum(1 for line in lines if _parse_field(line))
    if not known_section_seen:
        status_like = protocol == "status-tag" and (key_value_count >= 2 or (section_header_seen and key_value_count >= 1))
        if not status_like:
            return None

    sections: list[dict[str, Any]] = []
    for kind, title, section_lines in sections_input[:_MAX_SECTIONS]:
        if kind == "characters":
            characters = _parse_characters(section_lines)
            if characters:
                sections.append({"kind": kind, "title": title, "characters": characters})
            else:
                sections.append(_parse_simple_section("generic", title, section_lines))
        else:
            section = _parse_simple_section(kind, title, section_lines)
            if section.get("fields") or section.get("text"):
                sections.append(section)

    if not sections:
        return None

    warnings: list[str] = []
    if len(raw) >= _MAX_BLOCK_CHARS:
        warnings.append("状态块过长，已安全截断")
    if len(sections_input) > _MAX_SECTIONS:
        warnings.append("状态区段过多，仅展示前 12 个")

    return {
        "schema": "ai-tavern-status-panel/1",
        "protocol": protocol,
        "title": "剧情状态",
        "sections": sections,
        "warnings": warnings,
        "source_text": raw,
    }


def extract_status_panels(text: str) -> tuple[str, list[dict[str, Any]]]:
    source = str(text or "")
    matches: list[_BlockMatch] = []
    for pattern, protocol in ((_TEXT_END_RE, "text-end"), (_STATUS_RE, "status-tag")):
        for match in pattern.finditer(source):
            matches.append(_BlockMatch(match.start(), match.end(), match.group(1), protocol))
    matches.sort(key=lambda item: (item.start, item.end))

    selected: list[tuple[_BlockMatch, dict[str, Any]]] = []
    last_end = -1
    for item in matches:
        if len(selected) >= _MAX_BLOCKS or item.start < last_end:
            continue
        parsed = parse_status_panel(item.content, protocol=item.protocol)
        if not parsed:
            continue
        parsed["source_text"] = source[item.start:item.end][:_MAX_BLOCK_CHARS]
        selected.append((item, parsed))
        last_end = item.end

    if not selected:
        return source, []

    chunks: list[str] = []
    cursor = 0
    artifacts: list[dict[str, Any]] = []
    for item, panel in selected:
        chunks.append(source[cursor:item.start])
        index = len(artifacts)
        chunks.append(f"\n\n__AI_TAVERN_TEXT_STATUS_{index}__\n\n")
        artifacts.append({"type": "status-panel", "data": panel})
        cursor = item.end
    chunks.append(source[cursor:])
    return "".join(chunks), artifacts


def status_marker_index(paragraph: str) -> int | None:
    match = _STATUS_MARKER_RE.match(str(paragraph or "").strip())
    return int(match.group(1)) if match else None
