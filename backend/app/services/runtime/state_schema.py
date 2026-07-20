from __future__ import annotations

import copy
import re
from typing import Any


SCHEMA_ID = "ai-tavern-state-schema/1"
_FORBIDDEN_KEYS = {"__proto__", "prototype", "constructor"}

_CORE_SEMANTICS = {
    "/scene/location": "scene.location",
    "/scene/date": "scene.date",
    "/scene/time": "scene.time",
    "/scene/weather": "scene.weather",
    "/scene/atmosphere": "scene.atmosphere",
    "/scene/objective": "scene.objective",
    "/character/name": "character.name",
    "/character/state": "character.state",
    "/character/mood": "character.mood",
    "/character/expression": "character.expression",
    "/character/outfit": "character.outfit",
    "/character/injuries": "character.injuries",
    "/character/important_memories": "character.important_memories",
    "/relationship/affection": "relationship.affection",
    "/relationship/trust": "relationship.trust",
    "/relationship/tension": "relationship.tension",
    "/relationship/intimacy": "relationship.intimacy",
    "/relationship/fear": "relationship.fear",
    "/relationship/dependence": "relationship.dependence",
    "/relationship/stage": "relationship.stage",
    "/player/name": "player.name",
    "/player/level": "player.level",
    "/player/hp": "player.hp",
    "/player/max_hp": "player.max_hp",
    "/player/ac": "player.ac",
}

_READ_ONLY_PATHS = {"/runtime_version", "/mode", "/character/name", "/player/name"}


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _escape(part: Any) -> str:
    return str(part).replace("~", "~0").replace("/", "~1")


def _join(path: str, part: Any) -> str:
    return f"{path}/{_escape(part)}" if path else f"/{_escape(part)}"


def _decode(path: str) -> list[str]:
    if not isinstance(path, str) or not path.startswith("/"):
        return []
    return [part.replace("~1", "/").replace("~0", "~") for part in path[1:].split("/")]


def _lookup(root: Any, path: str) -> tuple[bool, Any]:
    current = root
    try:
        for part in _decode(path):
            if isinstance(current, dict):
                current = current[part]
            elif isinstance(current, list):
                current = current[int(part)]
            else:
                return False, None
        return True, current
    except (KeyError, IndexError, TypeError, ValueError):
        return False, None


def _value_type(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, int):
        return "integer"
    if isinstance(value, float):
        return "number"
    if isinstance(value, str):
        return "string"
    if isinstance(value, list):
        return "array"
    if isinstance(value, dict):
        return "object"
    return "any"


def _item_type(values: list[Any]) -> str | None:
    types = {
        _value_type(value)
        for value in values
        if value != "$__META_EXTENSIBLE__$"
    }
    if not types:
        return None
    if types <= {"integer", "number"}:
        return "number"
    return next(iter(types)) if len(types) == 1 else "any"


def _parse_bounds(description: str) -> tuple[float | int | None, float | int | None]:
    text = str(description or "")
    match = re.search(
        r"[\[（(]?\s*(-?\d+(?:\.\d+)?)\s*(?:-|~|～|—|至|到)\s*(-?\d+(?:\.\d+)?)\s*[\]）)]?",
        text,
    )
    if not match:
        return None, None
    lower = float(match.group(1))
    upper = float(match.group(2))
    if lower > upper:
        lower, upper = upper, lower
    return (int(lower) if lower.is_integer() else lower, int(upper) if upper.is_integer() else upper)


def _operation_modes(field_type: str, mutable: bool) -> list[str]:
    if not mutable:
        return []
    if field_type in {"integer", "number"}:
        return ["replace", "increment", "delta"]
    if field_type == "array":
        return ["replace", "append", "insert_at", "remove_at", "remove_value"]
    if field_type == "object":
        return ["replace", "add", "remove_value"]
    return ["replace"]


def _semantic_map(policy: dict[str, Any] | None) -> dict[str, str]:
    result = dict(_CORE_SEMANTICS)
    relationship_paths = _dict(_dict(policy).get("relationship_paths"))
    for semantic, paths in relationship_paths.items():
        for path in _list(paths):
            if isinstance(path, str):
                result[path] = f"relationship.{semantic}"
    return result


def _field(
    *,
    path: str,
    value: Any,
    source: str,
    declared: bool,
    description: str = "",
    required: bool = False,
    semantic: str = "",
    mutable: bool | None = None,
) -> dict[str, Any]:
    field_type = _value_type(value)
    if mutable is None:
        mutable = path not in _READ_ONLY_PATHS
    minimum, maximum = _parse_bounds(description)
    if semantic.startswith("relationship.") and field_type in {"integer", "number"}:
        minimum = 0 if minimum is None else minimum
        maximum = 100 if maximum is None else maximum
    update_modes = _operation_modes(field_type, bool(mutable))
    if mutable and not required and "remove" not in update_modes:
        update_modes.append("remove")
    result: dict[str, Any] = {
        "path": path,
        "type": field_type,
        "declared": declared,
        "source": source,
        "mutable": bool(mutable),
        "required": bool(required),
        "update_modes": update_modes,
    }
    if description:
        result["description"] = description.strip()
    if semantic:
        result["semantic"] = semantic
    if minimum is not None:
        result["minimum"] = minimum
    if maximum is not None:
        result["maximum"] = maximum
    if isinstance(value, list):
        item_type = _item_type(value)
        if item_type:
            result["items_type"] = item_type
    return result


def _container_meta(value: dict[str, Any], *, source: str, declared: bool) -> dict[str, Any]:
    meta = _dict(value.get("$meta"))
    strict_set = bool(meta.get("strictSet", meta.get("strict_set", False)))
    extensible = meta.get("extensible")
    if not isinstance(extensible, bool):
        extensible = not strict_set
    required = [str(item) for item in _list(meta.get("required")) if str(item).strip()]
    return {
        "kind": "object",
        "source": source,
        "declared": declared,
        "extensible": bool(extensible),
        "strict_set": strict_set,
        "required": required,
        "mutable": True,
    }


def _walk(
    value: Any,
    *,
    path: str,
    source: str,
    declared: bool,
    fields: dict[str, dict[str, Any]],
    containers: dict[str, dict[str, Any]],
    semantics: dict[str, str],
    required: bool = False,
    preserve_existing: bool = False,
) -> None:
    if isinstance(value, dict):
        container = _container_meta(value, source=source, declared=declared)
        if path in {"", "/scene", "/character", "/relationship", "/player", "/combat"}:
            container["extensible"] = True
        if path in {"/runtime_version", "/mode"}:
            container["mutable"] = False
        if preserve_existing:
            containers.setdefault(path or "/", container)
        else:
            containers[path or "/"] = container
        required_names = set(container.get("required", []))
        for key, child in value.items():
            if str(key) == "$meta" or str(key) in _FORBIDDEN_KEYS:
                continue
            child_path = _join(path, key)
            child_required = str(key) in required_names
            if isinstance(child, list) and len(child) == 2 and isinstance(child[1], str):
                actual = child[0]
                actual_path = _join(child_path, 0)
                fields.setdefault(
                    actual_path,
                    _field(
                        path=actual_path,
                        value=actual,
                        source=source,
                        declared=declared,
                        description=child[1],
                        required=child_required,
                        semantic=semantics.get(actual_path, ""),
                    ),
                )
                if isinstance(actual, dict):
                    _walk(
                        actual,
                        path=actual_path,
                        source=source,
                        declared=declared,
                        fields=fields,
                        containers=containers,
                        semantics=semantics,
                        required=child_required,
                        preserve_existing=preserve_existing,
                    )
                continue
            if isinstance(child, dict):
                _walk(
                    child,
                    path=child_path,
                    source=source,
                    declared=declared,
                    fields=fields,
                    containers=containers,
                    semantics=semantics,
                    required=child_required,
                    preserve_existing=preserve_existing,
                )
            else:
                fields.setdefault(
                    child_path,
                    _field(
                        path=child_path,
                        value=child,
                        source=source,
                        declared=declared,
                        required=child_required,
                        semantic=semantics.get(child_path, ""),
                    ),
                )
        return

    fields.setdefault(
        path,
        _field(
            path=path,
            value=value,
            source=source,
            declared=declared,
            required=required,
            semantic=semantics.get(path, ""),
        ),
    )


def _semantic_priority(field: dict[str, Any]) -> tuple[int, int, int, str]:
    path = str(field.get("path", ""))
    source = str(field.get("source", ""))
    return (
        0 if source == "card_initial_variables" else 1 if source == "runtime_dynamic" else 2,
        0 if path.startswith("/custom/") else 1,
        0 if bool(field.get("declared")) else 1,
        path,
    )


def _annotate_semantic_paths(fields: dict[str, dict[str, Any]]) -> dict[str, dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for field in fields.values():
        if not isinstance(field, dict):
            continue
        field.pop("canonical_path", None)
        field.pop("semantic_role", None)
        field.pop("derived", None)
        semantic = str(field.get("semantic", "")).strip()
        if semantic:
            grouped.setdefault(semantic, []).append(field)

    index: dict[str, dict[str, Any]] = {}
    for semantic, candidates in grouped.items():
        ordered = sorted(candidates, key=_semantic_priority)
        canonical = ordered[0]
        canonical_path = str(canonical.get("path", ""))
        paths = [str(item.get("path", "")) for item in ordered if str(item.get("path", ""))]
        for field in ordered:
            field_path = str(field.get("path", ""))
            field["canonical_path"] = canonical_path
            field["semantic_role"] = "source" if field_path == canonical_path else "projection"
            if field_path != canonical_path:
                field["derived"] = True
        index[semantic] = {
            "canonical_path": canonical_path,
            "paths": paths,
            "source": str(canonical.get("source", "")),
        }
    return index


def _summary(fields: dict[str, dict[str, Any]], containers: dict[str, dict[str, Any]]) -> dict[str, int]:
    values = list(fields.values())
    semantic_sources = {
        str(item.get("canonical_path"))
        for item in values
        if item.get("semantic") and item.get("canonical_path")
    }
    return {
        "field_count": len(values),
        "declared_count": sum(bool(item.get("declared")) for item in values),
        "numeric_count": sum(item.get("type") in {"integer", "number"} for item in values),
        "constrained_count": sum("minimum" in item or "maximum" in item for item in values),
        "semantic_count": sum(bool(item.get("semantic")) for item in values),
        "canonical_semantic_count": len(semantic_sources),
        "strict_container_count": sum(not bool(item.get("extensible", True)) for item in containers.values()),
    }


def build_state_schema(
    state: dict[str, Any],
    *,
    policy: dict[str, Any] | None = None,
    source: str = "runtime_and_card",
) -> dict[str, Any]:
    """Build a declarative field registry from the actual initial runtime state.

    MVU ``[value, description]`` wrappers are represented by their writable
    value path (``.../0``). Card ``$meta`` declarations become container rules;
    no card-provided code is executed.
    """

    state = state if isinstance(state, dict) else {}
    fields: dict[str, dict[str, Any]] = {}
    containers: dict[str, dict[str, Any]] = {}
    semantics = _semantic_map(policy)

    for key, value in state.items():
        path = _join("", key)
        field_source = "card_initial_variables" if key == "custom" else "runtime_core"
        if isinstance(value, dict):
            _walk(
                value,
                path=path,
                source=field_source,
                declared=True,
                fields=fields,
                containers=containers,
                semantics=semantics,
            )
        else:
            fields[path] = _field(
                path=path,
                value=value,
                source=field_source,
                declared=True,
                semantic=semantics.get(path, ""),
                mutable=path not in _READ_ONLY_PATHS,
            )

    semantic_index = _annotate_semantic_paths(fields)
    return {
        "schema": SCHEMA_ID,
        "version": 1,
        "source": source,
        "fields": fields,
        "containers": containers,
        "semantic_index": semantic_index,
        "summary": _summary(fields, containers),
    }


def reconcile_state_schema(schema: dict[str, Any] | None, state: dict[str, Any]) -> dict[str, Any]:
    """Add already-existing runtime fields as non-declared diagnostics.

    This preserves compatibility with dynamic fields created before P2 while
    keeping future creation governed by the nearest container declaration.
    """

    base = copy.deepcopy(schema if isinstance(schema, dict) else {})
    if base.get("schema") != SCHEMA_ID:
        return build_state_schema(state, source="runtime_reconstructed")
    fields = _dict(base.setdefault("fields", {}))
    containers = _dict(base.setdefault("containers", {}))
    semantics = {path: str(item.get("semantic", "")) for path, item in fields.items() if isinstance(item, dict)}
    _walk(
        state if isinstance(state, dict) else {},
        path="",
        source="runtime_dynamic",
        declared=False,
        fields=fields,
        containers=containers,
        semantics=semantics,
        preserve_existing=True,
    )
    base["fields"] = fields
    base["containers"] = containers
    base["semantic_index"] = _annotate_semantic_paths(fields)
    base["summary"] = _summary(fields, containers)
    return base


def resolve_schema_field(schema: dict[str, Any] | None, path: str) -> tuple[dict[str, Any] | None, bool]:
    fields = _dict(_dict(schema).get("fields"))
    field = fields.get(path)
    if isinstance(field, dict):
        return field, False
    parts = _decode(path)
    if parts and (parts[-1] == "-" or parts[-1].isdigit()):
        parent_path = "/" + "/".join(_escape(part) for part in parts[:-1])
        parent = fields.get(parent_path)
        if isinstance(parent, dict) and parent.get("type") == "array":
            return parent, True
    return None, False


def canonicalize_patch_operation(
    operation: dict[str, Any],
    schema: dict[str, Any] | None,
) -> tuple[dict[str, Any], dict[str, Any] | None]:
    """Redirect writes from a projected semantic alias to its card-owned source path."""

    normalized = copy.deepcopy(operation if isinstance(operation, dict) else {})
    if not isinstance(schema, dict) or schema.get("schema") != SCHEMA_ID:
        return normalized, None
    path = str(normalized.get("path", ""))
    field, array_item = resolve_schema_field(schema, path)
    if not field or array_item:
        return normalized, None
    semantic = str(field.get("semantic", "")).strip()
    canonical_path = str(field.get("canonical_path", "")).strip()
    if not semantic or not canonical_path or canonical_path == path:
        return normalized, None
    canonical_field, canonical_array_item = resolve_schema_field(schema, canonical_path)
    if not canonical_field or canonical_array_item:
        return normalized, None
    normalized["path"] = canonical_path
    return normalized, {
        "operation": copy.deepcopy(operation),
        "applied_as": copy.deepcopy(normalized),
        "reason_code": "SCHEMA_PATH_CANONICALIZED",
        "reason": f"按 Formal State Schema 将投影路径规范化到唯一可写路径 {canonical_path}",
        "semantic": semantic,
        "from_path": path,
        "to_path": canonical_path,
    }


def _nearest_container(schema: dict[str, Any] | None, path: str) -> dict[str, Any] | None:
    containers = _dict(_dict(schema).get("containers"))
    parts = _decode(path)
    while parts:
        parts.pop()
        candidate = "/" + "/".join(_escape(part) for part in parts) if parts else "/"
        container = containers.get(candidate)
        if isinstance(container, dict):
            return container
    return containers.get("/") if isinstance(containers.get("/"), dict) else None


def _matches_type(value: Any, expected: str) -> bool:
    if expected in {"", "any"}:
        return True
    if expected == "number":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    if expected == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if expected == "boolean":
        return isinstance(value, bool)
    if expected == "string":
        return isinstance(value, str)
    if expected == "array":
        return isinstance(value, list)
    if expected == "object":
        return isinstance(value, dict)
    if expected == "null":
        return value is None
    return True


def validate_patch_operation(
    state: dict[str, Any],
    operation: dict[str, Any],
    schema: dict[str, Any] | None,
) -> None:
    if not isinstance(schema, dict) or schema.get("schema") != SCHEMA_ID:
        return
    path = str(operation.get("path", ""))
    op = str(operation.get("op", "")).lower()
    if "$meta" in _decode(path):
        raise ValueError("状态 Schema 禁止修改声明元数据")

    field, array_item = resolve_schema_field(schema, path)
    exists, _ = _lookup(state, path)
    if field is None:
        if exists:
            return
        if op in {"add", "insert", "increment", "delta"}:
            container = _nearest_container(schema, path)
            if container and not bool(container.get("extensible", True)):
                raise ValueError("状态 Schema 未声明该字段，且父容器不允许扩展")
        return

    if not bool(field.get("mutable", True)):
        raise ValueError("状态 Schema 将该字段声明为只读")
    if op == "remove" and bool(field.get("required")):
        raise ValueError("状态 Schema 要求该字段必须存在")

    allowed = [str(item) for item in _list(field.get("update_modes"))]
    normalized_op = "add" if array_item and op in {"add", "insert"} else op
    if not array_item and allowed and normalized_op not in allowed and op not in {"add", "insert"}:
        raise ValueError(f"状态 Schema 不允许对该字段执行 {op or '空'} 操作")

    if op in {"increment", "delta"}:
        delta = operation.get("value")
        expected = str(field.get("type", "any"))
        if not isinstance(delta, (int, float)) or isinstance(delta, bool):
            raise ValueError("状态 Schema 类型不匹配：增量必须是 number")
        if expected == "integer" and not (isinstance(delta, int) or float(delta).is_integer()):
            raise ValueError("状态 Schema 类型不匹配：integer 字段不接受小数增量")
    elif op in {"replace", "add", "insert"} and "value" in operation:
        expected = str(field.get("items_type" if array_item else "type", "any"))
        if not _matches_type(operation.get("value"), expected):
            raise ValueError(f"状态 Schema 类型不匹配：期望 {expected}")
    elif op in {"append", "insert_at"} and "value" in operation:
        expected = str(field.get("items_type", "any"))
        if expected and not _matches_type(operation.get("value"), expected):
            raise ValueError(f"状态 Schema 数组元素类型不匹配：期望 {expected}")


def clamp_schema_number(path: str, value: float | int, schema: dict[str, Any] | None) -> float | int:
    field, _ = resolve_schema_field(schema, path)
    if not field or field.get("type") not in {"integer", "number"}:
        return value
    result = float(value)
    minimum = field.get("minimum")
    maximum = field.get("maximum")
    if isinstance(minimum, (int, float)) and not isinstance(minimum, bool):
        result = max(float(minimum), result)
    if isinstance(maximum, (int, float)) and not isinstance(maximum, bool):
        result = min(float(maximum), result)
    if field.get("type") == "integer" or result.is_integer():
        return int(result)
    return result


def validate_state_against_schema(state: dict[str, Any], schema: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(schema, dict) or schema.get("schema") != SCHEMA_ID:
        schema = build_state_schema(state, source="runtime_reconstructed")
    errors: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []
    schema_fields = _dict(schema.get("fields"))
    for path, field in schema_fields.items():
        if not isinstance(field, dict):
            continue
        exists, value = _lookup(state, path)
        if not exists:
            if field.get("required"):
                errors.append({"path": path, "code": "REQUIRED_FIELD_MISSING", "message": "Schema 要求字段必须存在"})
            continue
        expected = str(field.get("type", "any"))
        if not _matches_type(value, expected):
            errors.append({"path": path, "code": "TYPE_MISMATCH", "message": f"期望 {expected}，实际 {_value_type(value)}"})
            continue
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            minimum = field.get("minimum")
            maximum = field.get("maximum")
            if isinstance(minimum, (int, float)) and value < minimum:
                errors.append({"path": path, "code": "VALUE_BELOW_MINIMUM", "message": f"值 {value} 小于最小值 {minimum}"})
            if isinstance(maximum, (int, float)) and value > maximum:
                errors.append({"path": path, "code": "VALUE_ABOVE_MAXIMUM", "message": f"值 {value} 大于最大值 {maximum}"})
        if not field.get("declared"):
            warnings.append({"path": path, "code": "RUNTIME_DYNAMIC_FIELD", "message": "该字段来自既有运行时状态，未在角色卡初始 Schema 中声明"})

    observed = build_state_schema(state, source="validation_observation")
    for path in _dict(observed.get("fields")):
        if path in schema_fields:
            continue
        container = _nearest_container(schema, path)
        if container and not bool(container.get("extensible", True)):
            errors.append({
                "path": path,
                "code": "UNDECLARED_FIELD",
                "message": "字段未在 Schema 中声明，且父容器不允许扩展",
            })
        else:
            warnings.append({
                "path": path,
                "code": "UNDECLARED_EXTENSIBLE_FIELD",
                "message": "字段未预先声明，但父容器允许扩展",
            })
    return {
        "valid": not errors,
        "errors": errors,
        "warnings": warnings,
        "error_count": len(errors),
        "warning_count": len(warnings),
    }


def schema_prompt_contract(schema: dict[str, Any] | None, *, limit: int = 32) -> str:
    fields = [item for item in _dict(_dict(schema).get("fields")).values() if isinstance(item, dict)]
    preferred = sorted(
        fields,
        key=lambda item: (
            0 if item.get("source") == "card_initial_variables" else 1,
            0 if item.get("semantic") else 1,
            str(item.get("path", "")),
        ),
    )
    lines: list[str] = []
    emitted = 0
    for field in preferred:
        if emitted >= limit:
            break
        path = str(field.get("path", ""))
        if not path or not field.get("mutable", True) or field.get("semantic_role") == "projection":
            continue
        type_name = str(field.get("type", "any"))
        bounds = ""
        if "minimum" in field or "maximum" in field:
            bounds = f" range={field.get('minimum', '-∞')}..{field.get('maximum', '+∞')}"
        modes = ",".join(str(item) for item in _list(field.get("update_modes")))
        lines.append(f"- {path}: {type_name}{bounds}; ops={modes or 'none'}")
        emitted += 1
    if not lines:
        return ""
    return "【Formal State Schema（仅可使用已声明类型与操作）】\n" + "\n".join(lines)
