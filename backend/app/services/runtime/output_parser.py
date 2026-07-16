from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any

from ..tavern_compat.paths import CANONICAL_ROOT_ALIASES, normalize_card_pointer


@dataclass
class ParsedRuntimeOutput:
    narrative: str
    patch: list[dict] = field(default_factory=list)
    events: list[str] = field(default_factory=list)
    choices: list[str] = field(default_factory=list)
    dice: list[dict] = field(default_factory=list)
    battle_checks: list[dict] = field(default_factory=list)
    battle: dict | None = None
    expression: str = ""
    errors: list[str] = field(default_factory=list)

    def metadata(self) -> dict:
        return {
            "patch": self.patch,
            "events": self.events,
            "choices": self.choices,
            "dice": self.dice,
            "battle_checks": self.battle_checks,
            "battle": self.battle,
            "expression": self.expression,
            "errors": self.errors,
        }


_NATIVE_PATTERN = re.compile(r"<tavern_state\b[^>]*>(.*?)</tavern_state>", re.IGNORECASE | re.DOTALL)
_FENCED_NATIVE_PATTERN = re.compile(r"```(?:tavern-state|tavern_state)\s*(.*?)```", re.IGNORECASE | re.DOTALL)
_VARIABLES_PATTERN = re.compile(r"<(?:variables|status_data|stat_data)\b[^>]*>(.*?)</(?:variables|status_data|stat_data)>", re.IGNORECASE | re.DOTALL)
_UPDATE_PATTERN = re.compile(r"<(?:update_?variable)\b[^>]*>(.*?)</(?:update_?variable)>", re.IGNORECASE | re.DOTALL)
_JSON_PATCH_PATTERN = re.compile(r"<jsonpatch\b[^>]*>(.*?)</jsonpatch>", re.IGNORECASE | re.DOTALL)
_DICE_PATTERN = re.compile(r"<dice\b[^>]*>(.*?)</dice>", re.IGNORECASE | re.DOTALL)
_BATTLE_CHECK_PATTERN = re.compile(r"<battlecheck\b[^>]*>(.*?)</battlecheck>", re.IGNORECASE | re.DOTALL)
_BATTLE_PATTERN = re.compile(r"<battle\b[^>]*>(.*?)</battle>", re.IGNORECASE | re.DOTALL)




def _pointer_part(value: Any) -> str:
    return str(value).replace("~", "~0").replace("/", "~1")


_CANONICAL_ROOT_ALIASES = CANONICAL_ROOT_ALIASES


def _canonical_variable_path(key: Any) -> str:
    text = str(key).strip()
    canonical = _CANONICAL_ROOT_ALIASES.get(text.lower(), _CANONICAL_ROOT_ALIASES.get(text))
    if canonical:
        return f"/{canonical}"
    return f"/custom/{_pointer_part(text)}"


def _normalize_operation(operation: dict) -> dict:
    converted = dict(operation)
    converted["path"] = _convert_legacy_path(str(converted.get("path", "")))
    if "from" in converted:
        converted["from"] = _convert_legacy_path(str(converted.get("from", "")))
    return converted


def _apply_native_payload(parsed: ParsedRuntimeOutput, payload: Any) -> None:
    if not isinstance(payload, dict):
        raise ValueError("状态块必须是对象")
    parsed.patch.extend(_normalize_operation(item) for item in _patches(payload.get("patch", payload.get("state_patch", []))))
    parsed.events.extend(_strings(payload.get("events")))
    parsed.choices.extend(_strings(payload.get("choices"), limit=8))
    dice = payload.get("dice")
    if isinstance(dice, list):
        parsed.dice.extend([item for item in dice if isinstance(item, dict)][:12])
    checks = payload.get("battle_checks")
    if isinstance(checks, list):
        parsed.battle_checks.extend([item for item in checks if isinstance(item, dict)][:12])
    battle = payload.get("battle")
    if isinstance(battle, dict):
        parsed.battle = battle
    parsed.expression = str(payload.get("expression", ""))[:100]


def _strings(value: Any, limit: int = 12) -> list[str]:
    if not isinstance(value, list):
        return []
    result: list[str] = []
    for item in value:
        text = str(item).strip()
        if text and text not in result:
            result.append(text[:300])
        if len(result) >= limit:
            break
    return result


def _patches(value: Any) -> list[dict]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)][:64]


def _parse_key_value_block(content: str, mapping: dict[str, str]) -> dict:
    result: dict[str, str] = {}
    for raw_line in content.splitlines():
        line = raw_line.strip()
        if not line or ":" not in line and "：" not in line:
            continue
        parts = re.split(r"[:：]", line, maxsplit=1)
        if len(parts) != 2:
            continue
        key, value = parts[0].strip(), parts[1].strip()
        mapped = mapping.get(key)
        if mapped:
            result[mapped] = value[:1000]
    return result


def _parse_dice(content: str) -> dict | None:
    parsed = _parse_key_value_block(
        content,
        {
            "发动技能": "skill",
            "目标": "target",
            "情境": "context",
            "检定细节": "details",
            "判定结果": "result",
            "结果描述": "description",
        },
    )
    return parsed if parsed else None


def _parse_battle_check(content: str) -> dict | None:
    parsed = _parse_key_value_block(
        content,
        {
            "发动者": "actor",
            "目标": "target",
            "行动": "action",
            "检定类型": "check_type",
            "检定细节": "details",
            "判定结果": "outcome",
            "战果描述": "description",
        },
    )
    return parsed if parsed else None


def _parse_hp(value: str) -> tuple[int, int]:
    match = re.match(r"\s*(-?\d+)(?:\s*/\s*(-?\d+))?", value)
    if not match:
        return 0, 0
    current = max(0, int(match.group(1)))
    maximum = max(1, int(match.group(2) or current or 1))
    return min(current, maximum), maximum


def _parse_position(value: str) -> list[float]:
    numbers = re.findall(r"-?\d+(?:\.\d+)?", value)
    if len(numbers) < 2:
        return [0, 0]
    return [float(numbers[0]), float(numbers[1])]


def _parse_battle(content: str) -> dict | None:
    units: list[dict] = []
    allowed_status = {
        "blinded", "charmed", "deafened", "frightened", "grappled",
        "incapacitated", "invisible", "paralyzed", "petrified", "poisoned",
        "prone", "restrained", "stunned", "unconscious",
    }
    for raw_line in content.splitlines():
        line = raw_line.strip().strip("`")
        if not line or line.startswith("#") or "|" not in line:
            continue
        fields = [field.strip() for field in line.split("|") if field.strip()]
        if not fields:
            continue
        unit = {
            "id": fields[0][:80],
            "initiative": 0,
            "hp": 0,
            "max_hp": 0,
            "position": [0, 0],
            "attitude": 1,
            "status": [],
            "portrait": "",
            "next": False,
        }
        for field_text in fields[1:]:
            lower = field_text.lower()
            if lower == "next":
                unit["next"] = True
            elif lower.startswith("init "):
                numbers = re.findall(r"-?\d+", field_text)
                if numbers:
                    unit["initiative"] = int(numbers[0])
            elif lower.startswith("hp "):
                unit["hp"], unit["max_hp"] = _parse_hp(field_text[3:])
            elif lower.startswith("pos "):
                unit["position"] = _parse_position(field_text[4:])
            elif lower.startswith("attitude ") or lower.startswith("att "):
                numbers = re.findall(r"-?\d+", field_text)
                if numbers:
                    unit["attitude"] = max(0, min(2, int(numbers[0])))
            elif lower.startswith("status "):
                statuses = re.split(r"[,\s]+", field_text[7:].strip().lower())
                unit["status"] = [status for status in statuses if status in allowed_status]
            elif lower.startswith("portrait "):
                portrait = field_text[9:].strip()
                # Keep only safe display references. The browser still applies its own loading policy.
                if portrait.startswith(("https://", "http://", "/", "data:image/")):
                    unit["portrait"] = portrait[:2048]
        units.append(unit)
        if len(units) >= 50:
            break
    if not units:
        return None
    units.sort(key=lambda item: item.get("initiative", 0), reverse=True)
    next_unit = next((unit["id"] for unit in units if unit.get("next")), "")
    return {"active": True, "round": 0, "turn": next_unit, "units": units, "terrain": [], "events": []}


def _convert_legacy_path(path: str) -> str:
    return normalize_card_pointer(path)



def parse_runtime_output(text: str) -> ParsedRuntimeOutput:
    """Extract supported metadata blocks and return clean player-visible narrative."""
    visible = text or ""
    parsed = ParsedRuntimeOutput(narrative="")

    for pattern in (_NATIVE_PATTERN, _FENCED_NATIVE_PATTERN):
        for match in list(pattern.finditer(visible)):
            try:
                _apply_native_payload(parsed, json.loads(match.group(1).strip()))
            except (json.JSONDecodeError, ValueError, TypeError) as error:
                parsed.errors.append(f"状态块解析失败: {error}")
        visible = pattern.sub("", visible)

    for match in list(_VARIABLES_PATTERN.finditer(visible)):
        try:
            payload = json.loads(match.group(1).strip())
            if not isinstance(payload, dict):
                raise ValueError("变量块必须是对象")
            if isinstance(payload.get("patch"), list) or isinstance(payload.get("state_patch"), list):
                parsed.patch.extend(_normalize_operation(item) for item in _patches(payload.get("patch", payload.get("state_patch", []))))
            else:
                variables = payload.get("variables", payload.get("state", payload))
                if not isinstance(variables, dict):
                    raise ValueError("变量数据必须是对象")
                for key, value in list(variables.items())[:64]:
                    parsed.patch.append({
                        "op": "add",
                        "path": _canonical_variable_path(key),
                        "value": value,
                    })
        except (json.JSONDecodeError, ValueError, TypeError) as error:
            parsed.errors.append(f"变量块解析失败: {error}")
    visible = _VARIABLES_PATTERN.sub("", visible)

    for match in list(_UPDATE_PATTERN.finditer(visible)):
        patch_match = _JSON_PATCH_PATTERN.search(match.group(1))
        if not patch_match:
            parsed.errors.append("变量更新缺少 JSONPatch")
            continue
        try:
            operations = json.loads(patch_match.group(1).strip())
            for operation in _patches(operations):
                parsed.patch.append(_normalize_operation(operation))
        except (json.JSONDecodeError, TypeError) as error:
            parsed.errors.append(f"变量更新解析失败: {error}")
    visible = _UPDATE_PATTERN.sub("", visible)

    for match in list(_DICE_PATTERN.finditer(visible)):
        item = _parse_dice(match.group(1))
        if item:
            parsed.dice.append(item)
    visible = _DICE_PATTERN.sub("", visible)

    for match in list(_BATTLE_CHECK_PATTERN.finditer(visible)):
        item = _parse_battle_check(match.group(1))
        if item:
            parsed.battle_checks.append(item)
    visible = _BATTLE_CHECK_PATTERN.sub("", visible)

    for match in list(_BATTLE_PATTERN.finditer(visible)):
        battle = _parse_battle(match.group(1))
        if battle:
            parsed.battle = battle
    visible = _BATTLE_PATTERN.sub("", visible)

    # Never leak an unfinished metadata tail after a stopped stream.
    incomplete = re.search(
        r"<(?:tavern_state|update_?variable|variables|status_data|stat_data|dice|battlecheck|battle)\b|```(?:tavern-state|tavern_state)",
        visible,
        flags=re.IGNORECASE,
    )
    if incomplete:
        parsed.errors.append("检测到未完成的运行时数据块，已从可见正文中移除")
        visible = visible[:incomplete.start()]

    visible = re.sub(r"\n{3,}", "\n\n", visible).strip()
    parsed.narrative = visible
    parsed.events = _strings(parsed.events, limit=20)
    parsed.choices = _strings(parsed.choices, limit=8)
    return parsed
