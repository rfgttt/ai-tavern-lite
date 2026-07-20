from __future__ import annotations

import ast
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


def _split_mvu_args(text: str) -> list[str]:
    parts: list[str] = []
    start = 0
    quote: str | None = None
    escaped = False
    depth = 0
    for index, char in enumerate(text):
        if escaped:
            escaped = False
            continue
        if char == "\\":
            escaped = True
            continue
        if quote:
            if char == quote:
                quote = None
            continue
        if char in {'"', "'"}:
            quote = char
            continue
        if char in "[{(":
            depth += 1
            continue
        if char in "]})":
            depth = max(0, depth - 1)
            continue
        if char == "," and depth == 0:
            parts.append(text[start:index].strip())
            start = index + 1
    tail = text[start:].strip()
    if tail:
        parts.append(tail)
    return parts


def _parse_mvu_literal(text: str) -> Any:
    value = str(text or "").strip()
    if not value:
        return ""
    lowered = value.lower()
    if lowered == "true":
        return True
    if lowered == "false":
        return False
    if lowered in {"null", "undefined"}:
        return None
    try:
        return json.loads(value)
    except (json.JSONDecodeError, TypeError):
        pass
    try:
        return ast.literal_eval(value)
    except (ValueError, SyntaxError):
        if re.fullmatch(r"[-+]?\d+", value):
            return int(value)
        if re.fullmatch(r"[-+]?(?:\d+\.\d*|\d*\.\d+)", value):
            return float(value)
        raise ValueError("MVU 参数必须是字符串、数字、布尔值、数组或对象字面量")


def _mvu_path_to_pointer(raw_path: Any) -> str:
    text = str(raw_path or "").strip().strip(".")
    if not text:
        raise ValueError("MVU 路径不能为空")
    tokens: list[str] = []
    for match in re.finditer(r"([^\.\[\]]+)|\[(\d+)\]", text):
        token = match.group(1) if match.group(1) is not None else match.group(2)
        if token is not None and token != "":
            tokens.append(_pointer_part(token))
    if not tokens:
        raise ValueError("MVU 路径无效")
    return _convert_legacy_path("/" + "/".join(tokens))


def _iter_mvu_commands(content: str):
    text = str(content or "")
    index = 0
    marker = re.compile(r"_\.(set|add|insert|remove)\s*\(", re.IGNORECASE)
    while True:
        match = marker.search(text, index)
        if not match:
            break
        command = match.group(1).lower()
        cursor = match.end()
        start = cursor
        quote: str | None = None
        escaped = False
        depth = 1
        while cursor < len(text) and depth:
            char = text[cursor]
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif quote:
                if char == quote:
                    quote = None
            elif char in {'"', "'"}:
                quote = char
            elif char == "(":
                depth += 1
            elif char == ")":
                depth -= 1
            cursor += 1
        if depth:
            yield command, text[start:], "", "命令缺少右括号"
            break
        args = text[start:cursor - 1]
        line_end = text.find("\n", cursor)
        line_end = len(text) if line_end < 0 else line_end
        suffix = text[cursor:line_end]
        reason_match = re.search(r"//\s*(.*?)\s*$", suffix)
        reason = reason_match.group(1).strip() if reason_match else ""
        yield command, args, reason, ""
        index = cursor


def _parse_mvu_commands(content: str) -> tuple[list[dict], list[str], list[str]]:
    operations: list[dict] = []
    events: list[str] = []
    errors: list[str] = []
    # Analysis is explanatory model text, never an executable command source.
    command_text = re.sub(r"<analysis\b[^>]*>.*?</analysis>", "", str(content or ""), flags=re.IGNORECASE | re.DOTALL)
    for command, raw_args, reason, command_error in _iter_mvu_commands(command_text):
        if command_error:
            errors.append(f"MVU 变量命令解析失败: {command_error}")
            continue
        try:
            args = _split_mvu_args(raw_args)
            if not args:
                raise ValueError("命令缺少参数")
            path = _mvu_path_to_pointer(_parse_mvu_literal(args[0]))
            if command == "add":
                if len(args) != 2:
                    raise ValueError("_.add 需要路径和增量值")
                operations.append({"op": "increment", "path": path, "value": _parse_mvu_literal(args[1])})
            elif command == "set":
                if len(args) not in {2, 3}:
                    raise ValueError("_.set 需要 2 或 3 个参数")
                operations.append({"op": "replace", "path": path, "value": _parse_mvu_literal(args[-1])})
            elif command == "insert":
                if len(args) == 2:
                    operations.append({"op": "append", "path": path, "value": _parse_mvu_literal(args[1])})
                elif len(args) == 3:
                    selector = _parse_mvu_literal(args[1])
                    value = _parse_mvu_literal(args[2])
                    if isinstance(selector, int) and not isinstance(selector, bool):
                        operations.append({"op": "insert_at", "path": path, "index": selector, "value": value})
                    else:
                        operations.append({"op": "add", "path": f"{path}/{_pointer_part(selector)}", "value": value})
                else:
                    raise ValueError("_.insert 需要 2 或 3 个参数")
            elif command == "remove":
                if len(args) == 1:
                    operations.append({"op": "remove", "path": path})
                elif len(args) == 2:
                    selector = _parse_mvu_literal(args[1])
                    if isinstance(selector, int) and not isinstance(selector, bool):
                        operations.append({"op": "remove_at", "path": path, "index": selector})
                    else:
                        operations.append({"op": "remove_value", "path": path, "value": selector})
                else:
                    raise ValueError("_.remove 需要 1 或 2 个参数")
            if reason and reason not in events:
                events.append(reason[:300])
        except (ValueError, TypeError) as error:
            errors.append(f"MVU 变量命令解析失败: {error}")
    return operations, events, errors




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
        if patch_match:
            try:
                operations = json.loads(patch_match.group(1).strip())
                for operation in _patches(operations):
                    parsed.patch.append(_normalize_operation(operation))
            except (json.JSONDecodeError, TypeError) as error:
                parsed.errors.append(f"变量更新解析失败: {error}")
        else:
            operations, events, errors = _parse_mvu_commands(match.group(1))
            parsed.patch.extend(operations)
            parsed.events.extend(events)
            parsed.errors.extend(errors)
            if not operations and not errors:
                parsed.errors.append("变量更新未包含可识别的 JSONPatch 或 MVU 命令")
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
    unique_patch: list[dict] = []
    seen_patch: set[str] = set()
    for operation in parsed.patch:
        marker = json.dumps(operation, ensure_ascii=False, sort_keys=True, default=str)
        if marker in seen_patch:
            continue
        seen_patch.add(marker)
        unique_patch.append(operation)
    parsed.patch = unique_patch[:64]
    return parsed
