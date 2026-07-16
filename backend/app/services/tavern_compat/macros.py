from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class MacroContext:
    char_name: str
    user_name: str
    runtime_state: dict[str, Any] = field(default_factory=dict)
    lorebook_by_name: dict[str, str] = field(default_factory=dict)


_EJS_TAG = re.compile(r"<%[-_=]?\s*(.*?)\s*[-_]?%>", re.DOTALL)
_GETVAR_ASSIGN = re.compile(
    r"(?:(?:let|const|var)\s+)?([A-Za-z_$][\w$]*)\s*=\s*(?:await\s+)?getvar\(\s*['\"]([^'\"]+)['\"]\s*\)",
    re.IGNORECASE,
)
_GETWI = re.compile(
    r"(?:await\s+)?getwi\(\s*(?:null|[^,]+)\s*,\s*['\"]([^'\"]+)['\"]\s*\)",
    re.IGNORECASE,
)
_GETVAR_MACRO = re.compile(r"\{\{\s*getvar::([^{}]+?)\s*\}\}", re.IGNORECASE)
_FORMAT_VAR_MACRO = re.compile(r"\{\{\s*format_message_variable::([^{}]+?)\s*\}\}", re.IGNORECASE)


def _lookup_path(context: MacroContext, raw_path: str) -> Any:
    path = str(raw_path or "").strip().strip(".")
    if not path:
        return ""
    parts = [part for part in path.split(".") if part]
    state: Any = context.runtime_state if isinstance(context.runtime_state, dict) else {}

    if parts and parts[0].lower() in {"stat_data", "variables", "vars"}:
        state = state.get("custom", {}) if isinstance(state, dict) else {}
        parts = parts[1:]
    elif parts and parts[0].lower() == "custom":
        state = state.get("custom", {}) if isinstance(state, dict) else {}
        parts = parts[1:]

    current = state
    for part in parts:
        if isinstance(current, dict):
            if part not in current:
                return ""
            current = current[part]
        elif isinstance(current, list):
            try:
                current = current[int(part)]
            except (ValueError, IndexError, TypeError):
                return ""
        else:
            return ""
    return current


def _display_value(value: Any, *, pretty: bool = False) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False, indent=2 if pretty else None)
    return str(value)


def _parse_literal(text: str, env: dict[str, Any]) -> Any:
    value = text.strip()
    if value in env:
        return env[value]
    if (value.startswith("'") and value.endswith("'")) or (value.startswith('"') and value.endswith('"')):
        return value[1:-1]
    lower = value.lower()
    if lower == "true":
        return True
    if lower == "false":
        return False
    if lower in {"null", "undefined"}:
        return None
    try:
        return float(value) if "." in value else int(value)
    except ValueError:
        return value


def _compare(left: Any, op: str, right: Any) -> bool:
    try:
        if op in {"==", "==="}:
            return left == right
        if op in {"!=", "!=="}:
            return left != right
        if op == "<":
            return left < right
        if op == "<=":
            return left <= right
        if op == ">":
            return left > right
        if op == ">=":
            return left >= right
    except TypeError:
        try:
            lnum, rnum = float(left), float(right)
            return _compare(lnum, op, rnum)
        except (TypeError, ValueError):
            return False
    return False


def _eval_condition(condition: str, env: dict[str, Any]) -> bool:
    def eval_and(group: str) -> bool:
        for raw_term in re.split(r"\s*&&\s*", group):
            term = raw_term.strip().strip("() ")
            negated = term.startswith("!") and not term.startswith("!=")
            if negated:
                term = term[1:].strip()
            match = re.fullmatch(
                r"([A-Za-z_$][\w$]*)\s*(===|!==|==|!=|<=|>=|<|>)\s*(.+)",
                term,
                flags=re.DOTALL,
            )
            if match:
                result = _compare(env.get(match.group(1)), match.group(2), _parse_literal(match.group(3), env))
            else:
                result = bool(env.get(term, False))
            if negated:
                result = not result
            if not result:
                return False
        return True

    return any(eval_and(group) for group in re.split(r"\s*\|\|\s*", condition))


def _resolve_ejs(text: str, context: MacroContext, depth: int = 0) -> str:
    if "<%" not in text:
        return text
    if depth > 4:
        return _EJS_TAG.sub("", text)

    env: dict[str, Any] = {}
    frames: list[dict[str, Any]] = []
    output: list[str] = []
    cursor = 0

    def active() -> bool:
        return all(bool(frame["active"]) for frame in frames)

    for match in _EJS_TAG.finditer(text):
        if active():
            output.append(text[cursor:match.start()])
        code = match.group(1).strip()

        # Read-only getvar assignments can occur amid try/catch boilerplate.
        for assignment in _GETVAR_ASSIGN.finditer(code):
            env[assignment.group(1)] = _lookup_path(context, assignment.group(2))

        close_else_if = re.search(r"}\s*else\s+if\s*\((.*?)\)\s*{\s*$", code, re.DOTALL)
        close_else = re.search(r"}\s*else\s*{\s*$", code, re.DOTALL)
        plain_if_matches = list(re.finditer(r"(?:^|[;}])\s*if\s*\((.*?)\)\s*{\s*$", code, re.DOTALL))
        plain_close = re.fullmatch(r"}\s*;?", code)

        if close_else_if and frames:
            frame = frames[-1]
            branch = bool(frame["parent_active"]) and not bool(frame["taken"]) and _eval_condition(close_else_if.group(1), env)
            frame["active"] = branch
            frame["taken"] = bool(frame["taken"]) or branch
        elif close_else and frames:
            frame = frames[-1]
            branch = bool(frame["parent_active"]) and not bool(frame["taken"])
            frame["active"] = branch
            frame["taken"] = True
        elif plain_close and frames:
            frames.pop()
        elif plain_if_matches:
            condition = plain_if_matches[-1].group(1)
            parent_active = active()
            branch = parent_active and _eval_condition(condition, env)
            frames.append({"parent_active": parent_active, "taken": branch, "active": branch})
        else:
            getwi = _GETWI.search(code)
            if getwi and active():
                included = context.lorebook_by_name.get(getwi.group(1), "")
                if included:
                    output.append(_resolve_ejs(included, context, depth + 1))
            # Every other EJS instruction is deliberately ignored, never executed.

        cursor = match.end()

    if active():
        output.append(text[cursor:])
    return "".join(output)


def resolve_safe_macros(text: str, context: MacroContext) -> str:
    """Resolve a read-only SillyTavern/Tavern Helper compatibility subset.

    No imported code is evaluated. Unsupported EJS tags are removed, while a
    common `getvar` + numeric `if/else` + `getwi` pattern is interpreted with a
    tiny allow-listed evaluator.
    """

    if not text:
        return text
    result = _resolve_ejs(str(text), context)

    replacements = {
        "{{char}}": context.char_name,
        "{{user}}": context.user_name,
        "<char>": context.char_name,
        "<user>": context.user_name,
    }
    for token, value in replacements.items():
        result = re.sub(re.escape(token), lambda _m, v=value: v, result, flags=re.IGNORECASE)

    result = _GETVAR_MACRO.sub(lambda m: _display_value(_lookup_path(context, m.group(1))), result)
    result = _FORMAT_VAR_MACRO.sub(
        lambda m: _display_value(_lookup_path(context, m.group(1)), pretty=True),
        result,
    )
    # Remove any remaining executable EJS tags rather than exposing code to the model or browser.
    result = _EJS_TAG.sub("", result)
    return result
