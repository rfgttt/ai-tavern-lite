from __future__ import annotations

import hashlib
import re
from typing import Any

STATUS_PLACEHOLDER_RE = re.compile(r"<\s*statusplaceholderimpl\s*/?\s*>", re.IGNORECASE)

DIALOGUE_RE = re.compile(
    r"^(?:【(?P<bracket>[^】]{1,40})】|(?P<plain>[^：:\n]{1,40}))\s*[：:]\s*[“\"「](?P<text>.*?)[”\"」]\s*$"
)


def speaker_color(name: str) -> str:
    digest = hashlib.sha256(name.strip().encode("utf-8")).digest()
    hue = int.from_bytes(digest[:2], "big") % 360
    saturation = 58 + digest[2] % 18
    lightness = 62 + digest[3] % 10
    return f"hsl({hue} {saturation}% {lightness}%)"


def _paragraphs(text: str) -> list[str]:
    return [item.strip() for item in re.split(r"\n\s*\n", text or "") if item.strip()]


def parse_message_ast(text: str) -> dict[str, Any]:
    """Parse common roleplay prose into safe display segments.

    This is intentionally conservative: unmatched paragraphs remain markdown/text blocks.
    Imported status placeholders become native segments and never execute card HTML/JS.
    """
    segments: list[dict[str, Any]] = []
    speakers: dict[str, dict[str, str]] = {}
    marker = "__AI_TAVERN_CARD_STATE_PLACEHOLDER__"
    normalized_text = STATUS_PLACEHOLDER_RE.sub(f"\n\n{marker}\n\n", text or "")

    for paragraph in _paragraphs(normalized_text):
        if paragraph == marker:
            segments.append({"type": "card-state-placeholder"})
            continue
        match = DIALOGUE_RE.match(paragraph)
        if match:
            speaker = (match.group("bracket") or match.group("plain") or "").strip()
            dialogue = match.group("text").strip()
            speakers.setdefault(speaker, {"color": speaker_color(speaker)})
            segments.append({"type": "dialogue", "speaker": speaker, "text": dialogue})
            continue

        if paragraph.startswith("**") and paragraph.endswith("**") and len(paragraph) >= 4:
            segments.append({"type": "thought", "text": paragraph[2:-2].strip()})
            continue

        if paragraph.startswith("*") and paragraph.endswith("*") and len(paragraph) >= 2:
            segments.append({"type": "narration", "text": paragraph[1:-1].strip()})
            continue

        action_match = re.match(r"^(?P<speaker>[^：:\n]{1,40})\s*[：:]\s*\*(?P<text>.+)\*$", paragraph)
        if action_match:
            speaker = action_match.group("speaker").strip()
            speakers.setdefault(speaker, {"color": speaker_color(speaker)})
            segments.append({"type": "action", "speaker": speaker, "text": action_match.group("text").strip()})
            continue

        segments.append({"type": "markdown", "text": paragraph})

    return {
        "version": 2,
        "segments": segments,
        "speaker_metadata": speakers,
        "artifacts": [],
    }
