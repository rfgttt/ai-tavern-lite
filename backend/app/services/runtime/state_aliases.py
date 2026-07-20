from __future__ import annotations

import copy
import hashlib
import json
import re
import unicodedata
from dataclasses import dataclass, field
from typing import Any, Iterable

from .state_schema import resolve_schema_field


ALIAS_REGISTRY_ID = "ai-tavern-card-aliases/1"
_FORBIDDEN_ALIAS_KEYS = {"__proto__", "prototype", "constructor"}

# Candidate aliases are deliberately conservative. They never become active
# until the user confirms them for one specific character card.
_ALIAS_LEXICON: dict[str, tuple[tuple[str, float], ...]] = {
    "relationship.affection": (
        ("好感", 0.99), ("好感度", 1.0), ("affection", 1.0),
        ("favor", 0.96), ("favour", 0.96), ("favorability", 0.98),
        ("affinity", 0.88), ("love", 0.72),
    ),
    "relationship.fear": (
        ("害怕", 0.95), ("害怕值", 1.0), ("恐惧", 0.96), ("恐惧值", 0.99),
        ("fear", 1.0), ("terror", 0.78),
    ),
    "relationship.dependence": (
        ("依赖", 0.95), ("依赖值", 1.0), ("依赖度", 0.99),
        ("dependence", 1.0), ("dependency", 0.98),
    ),
    "relationship.trust": (
        ("信任", 0.98), ("信任值", 0.98), ("信任度", 1.0), ("trust", 1.0),
    ),
    "relationship.intimacy": (
        ("亲密", 0.96), ("亲密值", 0.98), ("亲密度", 1.0), ("intimacy", 1.0),
    ),
    "relationship.tension": (
        ("紧张", 0.88), ("紧张度", 0.98), ("张力", 0.94), ("tension", 1.0),
    ),
    "relationship.stage": (
        ("关系阶段", 0.98), ("阶段", 0.82), ("relationship_stage", 1.0), ("stage", 0.78),
    ),
    "scene.location": (
        ("地点", 1.0), ("位置", 0.92), ("场所", 0.86), ("location", 1.0), ("place", 0.84),
    ),
    "scene.date": (("日期", 1.0), ("date", 1.0), ("day", 0.76)),
    "scene.time": (("时间", 1.0), ("time", 1.0), ("clock", 0.75)),
    "scene.weather": (("天气", 1.0), ("weather", 1.0)),
    "scene.atmosphere": (
        ("氛围", 1.0), ("气氛", 0.98), ("atmosphere", 1.0), ("ambience", 0.95),
    ),
    "character.mood": (("心情", 0.96), ("情绪", 0.98), ("mood", 1.0), ("emotion", 0.86)),
    "character.state": (("状态", 0.82), ("人物状态", 0.98), ("state", 0.80), ("status", 0.76)),
    "character.outfit": (("服装", 0.98), ("穿着", 0.96), ("outfit", 1.0), ("clothing", 0.94)),
    "character.injuries": (("伤势", 0.98), ("伤口", 0.90), ("injuries", 1.0), ("wounds", 0.95)),
    "player.level": (("等级", 1.0), ("level", 1.0), ("lv", 0.90)),
    "player.hp": (("生命值", 0.98), ("当前生命", 0.96), ("hp", 1.0), ("health", 0.88)),
    "player.max_hp": (("最大生命值", 1.0), ("maxhp", 1.0), ("max_hp", 1.0)),
    "player.ac": (("护甲等级", 1.0), ("ac", 1.0), ("armorclass", 0.98), ("armor_class", 0.98)),
}


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def normalize_alias_key(value: Any) -> str:
    text = unicodedata.normalize("NFKC", str(value or "")).strip().casefold()
    text = re.sub(r"[\s_\-]+", "", text)
    return text


def validate_alias_text(value: Any) -> str:
    alias = unicodedata.normalize("NFKC", str(value or "")).strip()
    if not alias:
        raise ValueError("别名不能为空")
    if len(alias) > 80:
        raise ValueError("别名最多 80 个字符")
    if any(ord(char) < 32 for char in alias):
        raise ValueError("别名不能包含控制字符")
    if "/" in alias or "~" in alias:
        raise ValueError("别名只能是字段名，不能包含 JSON Pointer 分隔符")
    key = normalize_alias_key(alias)
    if not key or key in _FORBIDDEN_ALIAS_KEYS or alias.startswith("_"):
        raise ValueError("该别名属于禁止字段")
    return alias


def _decode_pointer(path: str) -> list[str]:
    if not isinstance(path, str) or not path.startswith("/"):
        return []
    return [part.replace("~1", "/").replace("~0", "~") for part in path[1:].split("/")]


def alias_token_from_path(path: str) -> str:
    parts = _decode_pointer(path)
    while parts and (parts[-1] == "-" or parts[-1].isdigit()):
        parts.pop()
    return parts[-1] if parts else ""


def _canonical_targets(schema: dict[str, Any] | None) -> list[dict[str, Any]]:
    semantic_index = _dict(_dict(schema).get("semantic_index"))
    fields = _dict(_dict(schema).get("fields"))
    result: list[dict[str, Any]] = []
    for semantic, item in semantic_index.items():
        if not isinstance(item, dict):
            continue
        canonical_path = str(item.get("canonical_path", "")).strip()
        field = fields.get(canonical_path)
        if not canonical_path or not isinstance(field, dict):
            continue
        result.append({
            "semantic": str(semantic),
            "canonical_path": canonical_path,
            "type": str(field.get("type", "any")),
            "source": str(field.get("source", "")),
            "minimum": field.get("minimum"),
            "maximum": field.get("maximum"),
        })
    return sorted(result, key=lambda item: (item["semantic"], item["canonical_path"]))


def _row_payload(row: Any) -> dict[str, Any]:
    if isinstance(row, dict):
        payload = dict(row)
    else:
        payload = {
            "id": getattr(row, "id", ""),
            "alias": getattr(row, "alias", ""),
            "alias_key": getattr(row, "alias_key", ""),
            "semantic": getattr(row, "semantic", ""),
            "canonical_path": getattr(row, "canonical_path", ""),
            "source": getattr(row, "source", "user_confirmed"),
            "confidence": getattr(row, "confidence", 1.0),
            "created_at": getattr(row, "created_at", None),
            "updated_at": getattr(row, "updated_at", None),
        }
    for key in ("created_at", "updated_at"):
        value = payload.get(key)
        if hasattr(value, "isoformat"):
            payload[key] = value.isoformat()
    payload["alias"] = str(payload.get("alias", ""))
    payload["alias_key"] = str(payload.get("alias_key") or normalize_alias_key(payload["alias"]))
    payload["semantic"] = str(payload.get("semantic", ""))
    payload["canonical_path"] = str(payload.get("canonical_path", ""))
    payload["source"] = str(payload.get("source", "user_confirmed"))
    try:
        payload["confidence"] = float(payload.get("confidence", 1.0))
    except (TypeError, ValueError):
        payload["confidence"] = 1.0
    return payload


def _registry_revision(confirmed: list[dict[str, Any]]) -> str:
    stable = [
        {
            "alias_key": item.get("alias_key", ""),
            "semantic": item.get("semantic", ""),
            "canonical_path": item.get("canonical_path", ""),
            "source": item.get("source", ""),
        }
        for item in confirmed
    ]
    raw = json.dumps(stable, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def build_alias_registry(
    schema: dict[str, Any] | None,
    *,
    confirmed_rows: Iterable[Any] = (),
    observed_paths: Iterable[str] = (),
    character_id: str = "",
) -> dict[str, Any]:
    targets = _canonical_targets(schema)
    target_by_semantic = {item["semantic"]: item for item in targets}

    confirmed: list[dict[str, Any]] = []
    seen_confirmed: set[str] = set()
    for row in confirmed_rows:
        item = _row_payload(row)
        target = target_by_semantic.get(item["semantic"])
        if not target:
            continue
        item["canonical_path"] = target["canonical_path"]
        if not item["alias_key"] or item["alias_key"] in seen_confirmed:
            continue
        confirmed.append(item)
        seen_confirmed.add(item["alias_key"])
    confirmed.sort(key=lambda item: (item["semantic"], item["alias_key"]))

    observations: dict[str, list[str]] = {}
    for path in observed_paths:
        token = alias_token_from_path(str(path))
        key = normalize_alias_key(token)
        if key:
            observations.setdefault(key, []).append(str(path))

    suggestions: list[dict[str, Any]] = []
    seen_suggestions: set[tuple[str, str]] = set()
    fields = _dict(_dict(schema).get("fields"))
    for semantic, aliases in _ALIAS_LEXICON.items():
        target = target_by_semantic.get(semantic)
        if not target:
            continue
        canonical_token = normalize_alias_key(alias_token_from_path(target["canonical_path"]))
        for alias, confidence in aliases:
            alias_key = normalize_alias_key(alias)
            if not alias_key or alias_key == canonical_token or alias_key in seen_confirmed:
                continue
            marker = (semantic, alias_key)
            if marker in seen_suggestions:
                continue
            seen_suggestions.add(marker)
            examples = sorted(set(observations.get(alias_key, [])))[:5]
            suggestions.append({
                "id": f"{semantic}:{alias_key}",
                "alias": alias,
                "alias_key": alias_key,
                "semantic": semantic,
                "canonical_path": target["canonical_path"],
                "confidence": confidence,
                "observed": bool(examples),
                "observed_paths": examples,
                "status": "suggested",
            })

    # Keep observed candidates first, then high-confidence exact aliases.
    suggestions.sort(
        key=lambda item: (
            0 if item.get("observed") else 1,
            -float(item.get("confidence", 0)),
            str(item.get("semantic", "")),
            str(item.get("alias_key", "")),
        )
    )
    revision = _registry_revision(confirmed)
    return {
        "schema": ALIAS_REGISTRY_ID,
        "version": 1,
        "character_id": character_id,
        "revision": revision,
        "confirmed": confirmed,
        "suggestions": suggestions,
        "targets": targets,
        "summary": {
            "confirmed_count": len(confirmed),
            "suggestion_count": len(suggestions),
            "observed_suggestion_count": sum(bool(item.get("observed")) for item in suggestions),
            "semantic_target_count": len(targets),
        },
    }


def confirmed_alias_map(registry: dict[str, Any] | None) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for item in _list(_dict(registry).get("confirmed")):
        if not isinstance(item, dict):
            continue
        key = str(item.get("alias_key") or normalize_alias_key(item.get("alias")))
        if key:
            result[key] = item
    return result


def suggestion_alias_map(registry: dict[str, Any] | None) -> dict[str, list[dict[str, Any]]]:
    result: dict[str, list[dict[str, Any]]] = {}
    for item in _list(_dict(registry).get("suggestions")):
        if not isinstance(item, dict):
            continue
        key = str(item.get("alias_key") or normalize_alias_key(item.get("alias")))
        if key:
            result.setdefault(key, []).append(item)
    return result


@dataclass
class AliasResolutionResult:
    operations: list[dict[str, Any]] = field(default_factory=list)
    events: list[dict[str, Any]] = field(default_factory=list)


def resolve_alias_operation(
    operation: dict[str, Any],
    schema: dict[str, Any] | None,
    registry: dict[str, Any] | None,
) -> tuple[dict[str, Any], dict[str, Any] | None]:
    normalized = copy.deepcopy(operation if isinstance(operation, dict) else {})
    path = str(normalized.get("path", ""))
    if not path or not isinstance(registry, dict) or registry.get("schema") != ALIAS_REGISTRY_ID:
        return normalized, None

    # Declared and P2.1 projection paths already have an unambiguous Schema
    # meaning and must never be shadowed by a user alias.
    field, _ = resolve_schema_field(schema, path)
    if field:
        return normalized, None

    alias = alias_token_from_path(path)
    alias_key = normalize_alias_key(alias)
    if not alias_key:
        return normalized, None

    confirmed = confirmed_alias_map(registry).get(alias_key)
    if confirmed:
        canonical_path = str(confirmed.get("canonical_path", ""))
        semantic = str(confirmed.get("semantic", ""))
        canonical_field, array_item = resolve_schema_field(schema, canonical_path)
        if not canonical_path or not canonical_field or array_item:
            return normalized, {
                "operation": copy.deepcopy(operation),
                "decision": "invalid",
                "reason_code": "ALIAS_TARGET_INVALID",
                "reason": "已确认别名的目标路径不再存在于当前 Formal State Schema",
                "alias": alias,
                "alias_key": alias_key,
                "semantic": semantic,
                "canonical_path": canonical_path,
                "source": str(confirmed.get("source", "user_confirmed")),
            }
        normalized["path"] = canonical_path
        return normalized, {
            "operation": copy.deepcopy(operation),
            "applied_as": copy.deepcopy(normalized),
            "decision": "confirmed",
            "reason_code": "ALIAS_CONFIRMED",
            "reason": f"当前角色卡已确认别名 {alias}，写入唯一路径 {canonical_path}",
            "alias": alias,
            "alias_key": alias_key,
            "semantic": semantic,
            "canonical_path": canonical_path,
            "source": str(confirmed.get("source", "user_confirmed")),
            "confidence": float(confirmed.get("confidence", 1.0) or 1.0),
        }

    candidates = suggestion_alias_map(registry).get(alias_key, [])
    if candidates:
        return normalized, {
            "operation": copy.deepcopy(operation),
            "decision": "suggested",
            "reason_code": "ALIAS_CONFIRMATION_REQUIRED",
            "reason": f"字段名 {alias} 命中候选别名，但尚未在当前角色卡中确认",
            "alias": alias,
            "alias_key": alias_key,
            "candidates": [
                {
                    "semantic": item.get("semantic"),
                    "canonical_path": item.get("canonical_path"),
                    "confidence": item.get("confidence"),
                    "suggestion_id": item.get("id"),
                }
                for item in candidates[:5]
            ],
        }
    return normalized, None


def normalize_alias_operations(
    operations: list[dict[str, Any]],
    schema: dict[str, Any] | None,
    registry: dict[str, Any] | None,
) -> AliasResolutionResult:
    result = AliasResolutionResult()
    for operation in operations if isinstance(operations, list) else []:
        if not isinstance(operation, dict):
            result.operations.append(copy.deepcopy(operation))
            continue
        normalized, event = resolve_alias_operation(operation, schema, registry)
        result.operations.append(normalized)
        if event:
            result.events.append(event)
    return result


def alias_prompt_contract(registry: dict[str, Any] | None, *, limit: int = 16) -> str:
    confirmed = [item for item in _list(_dict(registry).get("confirmed")) if isinstance(item, dict)]
    if not confirmed:
        return ""
    lines = []
    for item in confirmed[:limit]:
        lines.append(
            f"- {item.get('alias')}: {item.get('semantic')} -> {item.get('canonical_path')}"
        )
    return "【当前角色卡已确认字段别名（仅本卡有效）】\n" + "\n".join(lines)
