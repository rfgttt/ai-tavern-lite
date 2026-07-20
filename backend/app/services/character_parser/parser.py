import json
import base64
import copy
import re
from typing import Dict, Any, Optional, Tuple
from PIL import Image
import io
from ...core.logging import logger


class CharacterCardNormalized:
    """Normalized character card data structure."""

    def __init__(self):
        self.spec: str = "chara_card_v3"
        self.spec_version: str = "3.0"
        self.name: str = ""
        self.description: str = ""
        self.personality: str = ""
        self.scenario: str = ""
        self.first_mes: str = ""
        self.mes_example: str = ""
        self.creator_notes: str = ""
        self.creatorcomment: str = ""
        self.system_prompt: str = ""
        self.post_history_instructions: str = ""
        self.alternate_greetings: list = []
        self.tags: list = []
        self.creator: str = ""
        self.character_version: str = ""
        self.extensions: dict = {}
        self.character_book: dict = {}
        self.group_only_greetings: list = []
        self.ai_tavern_runtime: dict = {}
        self.raw_data: dict = {}

    def to_dict(self) -> dict:
        return {
            "spec": self.spec,
            "spec_version": self.spec_version,
            "name": self.name,
            "description": self.description,
            "personality": self.personality,
            "scenario": self.scenario,
            "first_mes": self.first_mes,
            "mes_example": self.mes_example,
            "creator_notes": self.creator_notes,
            "creatorcomment": self.creatorcomment,
            "system_prompt": self.system_prompt,
            "post_history_instructions": self.post_history_instructions,
            "alternate_greetings": self.alternate_greetings,
            "tags": self.tags,
            "creator": self.creator,
            "character_version": self.character_version,
            "extensions": self.extensions,
            "character_book": self.character_book,
            "group_only_greetings": self.group_only_greetings,
            "ai_tavern_runtime": self.ai_tavern_runtime,
        }


def _normalize_imported_greetings(value):
    """Normalize permissive external-card greetings to API-safe values."""
    if not isinstance(value, list):
        return []
    cleaned = []
    seen = set()
    for item in value:
        if not isinstance(item, str):
            continue
        text = item.strip()
        if not text or text in seen:
            continue
        text = text[:200_000]
        cleaned.append(text)
        seen.add(text)
        if len(cleaned) >= 50:
            break
    return cleaned


def _safe_get(data: dict, *keys, default=""):
    """Safely get nested value from dict."""
    current = data
    for key in keys:
        if isinstance(current, dict) and key in current:
            current = current[key]
        else:
            return default
    return current if current is not None else default


def parse_json_character(json_data: Dict[str, Any]) -> Tuple[CharacterCardNormalized, dict]:
    """
    Parse JSON character card (V2, V3, Tavern format) into normalized structure.
    Returns (normalized, raw_data)
    """
    normalized = CharacterCardNormalized()
    raw_data = json_data

    # Determine if it's V3 with data field
    data_section = json_data.get("data", {})
    has_data_section = isinstance(data_section, dict) and len(data_section) > 0

    # Priority: data section first, then top level fallback
    source = data_section if has_data_section else json_data

    # Spec info
    normalized.spec = _safe_get(json_data, "spec", default="chara_card_v2" if not has_data_section else "chara_card_v3")
    normalized.spec_version = str(_safe_get(json_data, "spec_version", default="2.0" if not has_data_section else "3.0"))

    # Basic fields - try data first, then top level
    normalized.name = str(_safe_get(source, "name", default=_safe_get(json_data, "name", default="未知角色")))
    normalized.description = str(_safe_get(source, "description", default=_safe_get(json_data, "description", default="")))
    normalized.personality = str(_safe_get(source, "personality", default=_safe_get(json_data, "personality", default="")))
    normalized.scenario = str(_safe_get(source, "scenario", default=_safe_get(json_data, "scenario", default="")))
    normalized.first_mes = str(_safe_get(source, "first_mes", default=_safe_get(json_data, "first_mes", default="")))
    normalized.mes_example = str(_safe_get(source, "mes_example", default=_safe_get(json_data, "mes_example", default="")))
    normalized.creator_notes = str(_safe_get(source, "creator_notes", default=_safe_get(json_data, "creator_notes", default="")))
    normalized.creatorcomment = str(_safe_get(source, "creatorcomment", default=_safe_get(json_data, "creatorcomment", default="")))
    normalized.system_prompt = str(_safe_get(source, "system_prompt", default=_safe_get(json_data, "system_prompt", default="")))
    normalized.post_history_instructions = str(_safe_get(source, "post_history_instructions", default=_safe_get(json_data, "post_history_instructions", default="")))

    # Alternate greetings
    alt = _safe_get(source, "alternate_greetings", default=_safe_get(json_data, "alternate_greetings", default=[]))
    normalized.alternate_greetings = _normalize_imported_greetings(alt)

    # Tags
    tags = _safe_get(source, "tags", default=_safe_get(json_data, "tags", default=[]))
    normalized.tags = tags if isinstance(tags, list) else []

    # Creator info
    normalized.creator = str(_safe_get(source, "creator", default=_safe_get(json_data, "creator", default="")))
    normalized.character_version = str(_safe_get(source, "character_version", default=_safe_get(json_data, "character_version", default="1.0")))

    # Extensions - preserve all unknown fields
    ext = _safe_get(source, "extensions", default=_safe_get(json_data, "extensions", default={}))
    normalized.extensions = ext if isinstance(ext, dict) else {}

    # Character book / lorebook
    cb = _safe_get(source, "character_book", default=_safe_get(json_data, "character_book", default={}))
    normalized.character_book = _normalize_lorebook_for_internal(cb)

    # Group only greetings
    gog = _safe_get(source, "group_only_greetings", default=_safe_get(json_data, "group_only_greetings", default=[]))
    normalized.group_only_greetings = gog if isinstance(gog, list) else []

    from ..runtime.card_profile import analyze_card

    profile_source = normalized.to_dict()
    profile_source.pop("ai_tavern_runtime", None)
    normalized.ai_tavern_runtime = analyze_card(profile_source)
    normalized.raw_data = raw_data

    return normalized, raw_data


def parse_png_character(png_bytes: bytes) -> Tuple[CharacterCardNormalized, dict, bytes]:
    """
    Parse PNG character card.
    Returns (normalized, raw_json, avatar_bytes)
    Raises ValueError if no character data found.
    """
    avatar_bytes = png_bytes
    json_str = None

    # Try Pillow first
    try:
        img = Image.open(io.BytesIO(png_bytes))
        text_data = img.info

        # Common keys for character data
        for key in ["chara", "ccv3", "character", "tavern", "Chara", "CCV3", "Character"]:
            if key in text_data:
                value = text_data[key]
                json_str = _try_decode_json_value(value)
                if json_str:
                    break

        if not json_str:
            # Try all text keys that might contain JSON
            for key, value in text_data.items():
                if isinstance(value, str) and value.strip().startswith("{"):
                    json_str = _try_decode_json_value(value)
                    if json_str:
                        break
    except Exception as e:
        logger.warning(f"Pillow PNG parse failed, trying manual chunk parsing: {e}")

    # Fallback: manual PNG chunk parsing
    if not json_str:
        json_str = _parse_png_chunks(png_bytes)

    if not json_str:
        raise ValueError("PNG 文件中未找到角色卡数据，请确认这是一个有效的角色卡 PNG 文件。")

    try:
        json_data = json.loads(json_str)
    except json.JSONDecodeError as e:
        raise ValueError(f"角色卡 JSON 解析失败: {e}")

    normalized, raw_data = parse_json_character(json_data)
    return normalized, raw_data, avatar_bytes


def _try_decode_json_value(value: str) -> Optional[str]:
    """Try to decode a value that might be base64 encoded JSON."""
    if not value:
        return None

    value = value.strip()

    # Already looks like JSON
    if value.startswith("{"):
        try:
            json.loads(value)
            return value
        except json.JSONDecodeError:
            pass

    # Try base64 decode
    try:
        decoded = base64.b64decode(value).decode("utf-8")
        if decoded.startswith("{"):
            json.loads(decoded)
            return decoded
    except Exception:
        pass

    return None


def _parse_png_chunks(png_bytes: bytes) -> Optional[str]:
    """Manual PNG chunk parsing as fallback."""
    # PNG signature
    signature = png_bytes[:8]
    if signature != b'\x89PNG\r\n\x1a\n':
        raise ValueError("不是有效的 PNG 文件")

    offset = 8
    while offset < len(png_bytes):
        if offset + 8 > len(png_bytes):
            break

        # Read chunk length (4 bytes) and type (4 bytes)
        length = int.from_bytes(png_bytes[offset:offset + 4], "big")
        chunk_type = png_bytes[offset + 4:offset + 8].decode("ascii", errors="ignore")

        data_start = offset + 8
        data_end = data_start + length

        if data_end + 4 > len(png_bytes):
            break

        chunk_data = png_bytes[data_start:data_end]

        if chunk_type in ("tEXt", "zTXt", "iTXt"):
            try:
                if chunk_type == "tEXt":
                    # keyword\0data
                    null_pos = chunk_data.find(b'\x00')
                    if null_pos > 0:
                        keyword = chunk_data[:null_pos].decode("latin-1", errors="ignore")
                        text_value = chunk_data[null_pos + 1:].decode("latin-1", errors="ignore")
                        result = _check_chunk_keyword(keyword, text_value)
                        if result:
                            return result

                elif chunk_type == "iTXt":
                    # iTXt international text
                    parts = chunk_data.split(b'\x00', 2)
                    if len(parts) >= 3:
                        keyword = parts[0].decode("utf-8", errors="ignore")
                        text_value = parts[2].decode("utf-8", errors="ignore")
                        result = _check_chunk_keyword(keyword, text_value)
                        if result:
                            return result
            except Exception as e:
                logger.debug(f"Chunk parse error for {chunk_type}: {e}")

        # Skip CRC (4 bytes)
        offset = data_end + 4

        if chunk_type == "IEND":
            break

    return None


def _check_chunk_keyword(keyword: str, value: str) -> Optional[str]:
    """Check if a PNG text chunk keyword contains character data."""
    keyword_lower = keyword.lower()
    chara_keywords = ["chara", "ccv3", "character", "tavern", "character_card"]

    for ck in chara_keywords:
        if ck in keyword_lower:
            result = _try_decode_json_value(value)
            if result:
                return result

    # Also check the value itself
    if value.strip().startswith("{"):
        result = _try_decode_json_value(value)
        if result:
            return result

    return None


CCV3_DATA_FIELDS = {
    "name",
    "description",
    "tags",
    "creator",
    "character_version",
    "mes_example",
    "extensions",
    "system_prompt",
    "post_history_instructions",
    "first_mes",
    "alternate_greetings",
    "personality",
    "scenario",
    "creator_notes",
    "character_book",
    "assets",
    "nickname",
    "creator_notes_multilingual",
    "source",
    "group_only_greetings",
    "creation_date",
    "modification_date",
}

CCV3_LOREBOOK_FIELDS = {
    "name",
    "description",
    "scan_depth",
    "token_budget",
    "recursive_scanning",
    "extensions",
    "entries",
}

CCV3_LOREBOOK_ENTRY_FIELDS = {
    "keys",
    "content",
    "extensions",
    "enabled",
    "insertion_order",
    "case_sensitive",
    "use_regex",
    "constant",
    "name",
    "priority",
    "id",
    "comment",
    "selective",
    "secondary_keys",
    "position",
}


def _normalize_lorebook_for_internal(character_book: Any) -> dict:
    """Keep CCv3 extension data while exposing AI Tavern fields internally."""
    if not isinstance(character_book, dict):
        return {}

    normalized_book = copy.deepcopy(character_book)
    normalized_book.setdefault("extensions", {})
    entries = normalized_book.get("entries", [])
    if not isinstance(entries, list):
        normalized_book["entries"] = []
        return normalized_book

    normalized_entries = []
    for raw_entry in entries:
        if not isinstance(raw_entry, dict):
            continue
        entry = copy.deepcopy(raw_entry)
        extensions = entry.get("extensions") if isinstance(entry.get("extensions"), dict) else {}
        entry["extensions"] = extensions
        if "probability" not in entry and isinstance(extensions.get("probability"), (int, float)):
            entry["probability"] = extensions["probability"]
        normalized_entries.append(entry)
    normalized_book["entries"] = normalized_entries
    return normalized_book


def _coerce_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value]


def _export_lorebook(character_book: Any) -> dict:
    source = character_book if isinstance(character_book, dict) else {}
    exported: dict = {"extensions": copy.deepcopy(source.get("extensions", {})), "entries": []}
    if not isinstance(exported["extensions"], dict):
        exported["extensions"] = {}

    for field in ("name", "description"):
        if field in source:
            exported[field] = str(source[field] or "")
    for field in ("scan_depth", "token_budget"):
        if field in source:
            exported[field] = _coerce_int(source[field])
    if "recursive_scanning" in source:
        exported["recursive_scanning"] = bool(source["recursive_scanning"])

    entries = source.get("entries", [])
    if not isinstance(entries, list):
        entries = []

    for raw_entry in entries:
        if not isinstance(raw_entry, dict):
            continue
        entry_extensions = copy.deepcopy(raw_entry.get("extensions", {}))
        if not isinstance(entry_extensions, dict):
            entry_extensions = {}
        if "probability" in raw_entry:
            entry_extensions["probability"] = raw_entry.get("probability")

        entry = {
            "keys": _string_list(raw_entry.get("keys")),
            "content": str(raw_entry.get("content") or ""),
            "extensions": entry_extensions,
            "enabled": bool(raw_entry.get("enabled", True)),
            "insertion_order": _coerce_int(raw_entry.get("insertion_order", 0)),
            "use_regex": bool(raw_entry.get("use_regex", False)),
        }

        for field in ("case_sensitive", "constant", "selective"):
            if field in raw_entry:
                entry[field] = bool(raw_entry[field])
        for field in ("name", "comment"):
            if field in raw_entry:
                entry[field] = str(raw_entry[field] or "")
        if "priority" in raw_entry:
            entry["priority"] = _coerce_int(raw_entry["priority"])
        if "secondary_keys" in raw_entry:
            entry["secondary_keys"] = _string_list(raw_entry["secondary_keys"])
        if raw_entry.get("position") in {"before_char", "after_char"}:
            entry["position"] = raw_entry["position"]

        entry_id = raw_entry.get("id")
        if isinstance(entry_id, (str, int)) and not isinstance(entry_id, bool):
            entry["id"] = entry_id

        exported["entries"].append(entry)

    return exported


def validate_character_card_v3(card: Any) -> list[str]:
    """Validate the strict subset emitted by AI Tavern before download."""
    errors: list[str] = []
    if not isinstance(card, dict):
        return ["导出结果不是 JSON 对象"]
    if card.get("spec") != "chara_card_v3":
        errors.append("spec 必须为 chara_card_v3")
    if card.get("spec_version") != "3.0":
        errors.append("spec_version 必须为 3.0")

    data = card.get("data")
    if not isinstance(data, dict):
        return errors + ["data 必须为对象"]

    required_types = {
        "name": str,
        "description": str,
        "tags": list,
        "creator": str,
        "character_version": str,
        "mes_example": str,
        "extensions": dict,
        "system_prompt": str,
        "post_history_instructions": str,
        "first_mes": str,
        "alternate_greetings": list,
        "personality": str,
        "scenario": str,
        "creator_notes": str,
        "group_only_greetings": list,
    }
    for field, expected_type in required_types.items():
        if not isinstance(data.get(field), expected_type):
            errors.append(f"data.{field} 类型不正确")

    for forbidden in ("spec", "spec_version", "creatorcomment", "ai_tavern_runtime"):
        if forbidden in data:
            errors.append(f"data 不应包含 {forbidden}")

    character_book = data.get("character_book")
    if character_book is not None:
        if not isinstance(character_book, dict):
            errors.append("data.character_book 必须为对象")
        else:
            if not isinstance(character_book.get("extensions"), dict):
                errors.append("data.character_book.extensions 必须为对象")
            entries = character_book.get("entries")
            if not isinstance(entries, list):
                errors.append("data.character_book.entries 必须为数组")
            else:
                for index, entry in enumerate(entries):
                    prefix = f"data.character_book.entries[{index}]"
                    if not isinstance(entry, dict):
                        errors.append(f"{prefix} 必须为对象")
                        continue
                    for field, expected_type in (
                        ("keys", list),
                        ("content", str),
                        ("extensions", dict),
                        ("enabled", bool),
                        ("insertion_order", int),
                        ("use_regex", bool),
                    ):
                        if not isinstance(entry.get(field), expected_type):
                            errors.append(f"{prefix}.{field} 类型不正确")
                    if entry.get("id", "__missing__") is None:
                        errors.append(f"{prefix}.id 不得为 null")
                    if "probability" in entry:
                        errors.append(f"{prefix}.probability 应保存在 extensions 中")
    return errors


def export_character_v3(normalized: CharacterCardNormalized, raw_json: dict) -> dict:
    """Export a strict Character Card V3 JSON object without losing AI Tavern metadata."""
    base_data = raw_json if isinstance(raw_json, dict) else {}
    raw_data = base_data.get("data") if isinstance(base_data.get("data"), dict) else base_data

    extensions = copy.deepcopy(normalized.extensions) if isinstance(normalized.extensions, dict) else {}
    if normalized.ai_tavern_runtime:
        extensions["ai_tavern_runtime"] = copy.deepcopy(normalized.ai_tavern_runtime)

    creator_notes = normalized.creator_notes or normalized.creatorcomment
    if normalized.creatorcomment and normalized.creator_notes:
        legacy = extensions.setdefault("ai_tavern_legacy", {})
        if not isinstance(legacy, dict):
            legacy = {}
            extensions["ai_tavern_legacy"] = legacy
        legacy["creatorcomment"] = normalized.creatorcomment

    data_section = {
        "name": normalized.name,
        "description": normalized.description,
        "tags": list(normalized.tags or []),
        "creator": normalized.creator,
        "character_version": normalized.character_version,
        "mes_example": normalized.mes_example,
        "extensions": extensions,
        "system_prompt": normalized.system_prompt,
        "post_history_instructions": normalized.post_history_instructions,
        "first_mes": normalized.first_mes,
        "alternate_greetings": list(normalized.alternate_greetings or []),
        "personality": normalized.personality,
        "scenario": normalized.scenario,
        "creator_notes": creator_notes,
        "group_only_greetings": list(normalized.group_only_greetings or []),
    }

    for field in (
        "assets",
        "nickname",
        "creator_notes_multilingual",
        "source",
        "creation_date",
        "modification_date",
    ):
        if isinstance(raw_data, dict) and field in raw_data:
            data_section[field] = copy.deepcopy(raw_data[field])

    character_book = _export_lorebook(normalized.character_book)
    if character_book["entries"] or any(key not in {"entries", "extensions"} for key in character_book):
        data_section["character_book"] = character_book
    elif isinstance(normalized.character_book, dict) and normalized.character_book:
        data_section["character_book"] = character_book

    return {
        "spec": "chara_card_v3",
        "spec_version": "3.0",
        "data": data_section,
    }


def replace_template_vars(text: str, char_name: str, user_name: str) -> str:
    """Resolve identity macros without executing imported card code."""
    from ..tavern_compat.macros import MacroContext, resolve_safe_macros

    return resolve_safe_macros(
        text,
        MacroContext(char_name=char_name, user_name=user_name, runtime_state={}),
    ) if text else text
