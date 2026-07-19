from __future__ import annotations

import copy
import hashlib
import json
import re
from collections import Counter
from typing import Any, Iterable
from urllib.parse import urlparse


_MAX_FINDINGS = 200
_MAX_SCAN_STRINGS = 20_000
_MAX_SCAN_NODES = 100_000
_MAX_NESTING_DEPTH = 64
_MAX_TOTAL_TEXT = 8_000_000
_MAX_EVIDENCE = 180

_SEVERITY_RANK = {"info": 0, "warning": 1, "high": 2, "blocked": 3}
_RISK_BY_SEVERITY = {"info": "safe", "warning": "notice", "high": "high", "blocked": "blocked"}

_URL_RE = re.compile(r"https?://[^\s\"'<>]+", re.IGNORECASE)
_DANGEROUS_PROTOCOL_RE = re.compile(
    r"(?i)(?:javascript|vbscript|file|data\s*:\s*(?:text/html|application/javascript))\s*:"
)
_SCRIPT_TAG_RE = re.compile(r"(?is)<\s*script\b[^>]*>.*?<\s*/\s*script\s*>|<\s*script\b[^>]*/?\s*>")
_DANGEROUS_TAG_RE = re.compile(
    r"(?is)<\s*(?:iframe|object|embed|applet|base|meta|link|form)\b[^>]*>.*?<\s*/\s*(?:iframe|object|embed|applet|form)\s*>"
    r"|<\s*(?:iframe|object|embed|applet|base|meta|link|form)\b[^>]*/?\s*>"
)
_EVENT_HANDLER_RE = re.compile(r"(?is)\s+on[a-z0-9_-]+\s*=\s*(?:\"[^\"]*\"|'[^']*'|[^\s>]+)")
_STYLE_BLOCK_RE = re.compile(r"(?is)<\s*style\b[^>]*>.*?<\s*/\s*style\s*>")
_CSS_IMPORT_RE = re.compile(r"(?is)@import\s+(?:url\()?\s*[\"']?https?://[^;\)\"']+[\"']?\)?\s*;?")
_CSS_REMOTE_URL_RE = re.compile(r"(?is)url\(\s*[\"']?https?://[^\)\"']+[\"']?\s*\)")
_REMOTE_RESOURCE_TAG_RE = re.compile(
    r"(?is)<\s*(?:img|audio|video|source)\b[^>]*(?:src|srcset)\s*=\s*(?:\"https?://[^\"]*\"|'https?://[^']*'|https?://[^\s>]+)[^>]*>"
)

_PROMPT_OVERRIDE_PATTERNS = [
    re.compile(r"(?i)\b(?:ignore|disregard|override|bypass|forget)\b.{0,80}\b(?:previous|prior|system|developer|hidden)\b.{0,40}\b(?:instruction|prompt|rule)s?\b"),
    re.compile(r"(?:忽略|无视|覆盖|绕过|取消|忘记).{0,40}(?:之前|先前|系统|开发者|隐藏).{0,30}(?:指令|提示词|规则)"),
]
_PROMPT_SECRET_PATTERNS = [
    re.compile(r"(?i)\b(?:reveal|show|print|dump|read|return|extract|steal|send|provide|give me|get)\b.{0,80}\b(?:api[ _-]?key|secret|access token|bearer token|authorization header|custom headers?|environment variables?|password)\b"),
    re.compile(r"(?:显示|输出|打印|读取|返回|提取|窃取|发送|提供|获取|给我).{0,60}(?:API\s*密钥|密钥|访问令牌|授权请求头|自定义请求头|环境变量|密码)"),
]
_PROMPT_LEAK_PATTERNS = [
    re.compile(r"(?i)\b(?:reveal|show|print|dump|expose|leak|repeat|return)\b.{0,100}\b(?:system prompt|developer message|hidden instruction|internal prompt|chain of thought)\b"),
    re.compile(r"(?:显示|输出|打印|泄露|暴露|复述|返回).{0,60}(?:系统提示词|开发者消息|隐藏指令|内部提示词|思维链)"),
]
_PROMPT_EXEC_PATTERNS = [
    re.compile(r"(?i)\b(?:execute|run|invoke|call)\b.{0,60}\b(?:shell|powershell|cmd|bash|python|javascript|tool|function|plugin)\b"),
    re.compile(r"(?:执行|运行|调用).{0,40}(?:Shell|PowerShell|CMD|Bash|Python|JavaScript|工具|函数|插件|命令)"),
]
_PROMPT_EXFIL_PATTERNS = [
    re.compile(r"(?i)\b(?:send|post|upload|exfiltrate|transmit)\b.{0,100}https?://"),
    re.compile(r"(?:发送|上传|回传|外传).{0,80}https?://"),
]
_PROMPT_BOUNDARY_RE = re.compile(r"(?i)<\|(?:system|developer|assistant|tool)\|>|\[/?INST\]|^\s*#{2,}\s*(?:system|developer)\b", re.MULTILINE)
_AUTHORITY_CLAIM_RE = re.compile(r"(?:最高优先级|此规则最高|绝对服从|铁律|不可违背|override priority|highest priority)", re.IGNORECASE)

_ACTIVE_SCRIPT_KEYS = {
    "regex_scripts",
    "scripts",
    "script",
    "javascript",
    "js",
    "plugins",
    "plugin",
    "tavern_helper",
    "tavernhelper",
}
_PROMPT_FIELD_HINTS = {
    "system_prompt",
    "post_history_instructions",
    "description",
    "personality",
    "scenario",
    "first_mes",
    "mes_example",
    "creator_notes",
    "creatorcomment",
    "content",
    "name",
    "comment",
    "alternate_greetings",
}


def _json_sha256(value: Any) -> str:
    try:
        encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    except (RecursionError, ValueError, TypeError):
        encoded = b"unserializable-character-card"
    return hashlib.sha256(encoded).hexdigest()


def _evidence(text: str) -> str:
    compact = re.sub(r"\s+", " ", text).strip()
    return compact[:_MAX_EVIDENCE] + ("…" if len(compact) > _MAX_EVIDENCE else "")


def _walk(value: Any, path: str = "$") -> Iterable[tuple[str, Any, str | None]]:
    stack: list[tuple[str, Any, str | None, int]] = [(path, value, None, 0)]
    strings = 0
    nodes = 0
    while stack and nodes < _MAX_SCAN_NODES and strings < _MAX_SCAN_STRINGS:
        current_path, current, current_key, depth = stack.pop()
        nodes += 1
        if current_path != path:
            yield current_path, current, current_key
        if depth >= _MAX_NESTING_DEPTH:
            continue
        if isinstance(current, dict):
            items = list(current.items())
            for key, item in reversed(items):
                key_text = str(key)
                child = f"{current_path}.{key_text}" if current_path != "$" else f"$.{key_text}"
                stack.append((child, item, key_text, depth + 1))
        elif isinstance(current, list):
            for index in range(len(current) - 1, -1, -1):
                stack.append((f"{current_path}[{index}]", current[index], None, depth + 1))
        elif isinstance(current, str):
            strings += 1


def _structure_issues(value: Any) -> list[str]:
    issues: list[str] = []
    stack: list[tuple[Any, int]] = [(value, 0)]
    nodes = 0
    total_text = 0
    max_depth = 0
    while stack:
        current, depth = stack.pop()
        nodes += 1
        max_depth = max(max_depth, depth)
        if nodes > _MAX_SCAN_NODES:
            issues.append(f"JSON 节点超过 {_MAX_SCAN_NODES} 个")
            break
        if depth > _MAX_NESTING_DEPTH:
            issues.append(f"JSON 嵌套深度超过 {_MAX_NESTING_DEPTH} 层")
            break
        if isinstance(current, dict):
            stack.extend((item, depth + 1) for item in current.values())
        elif isinstance(current, list):
            stack.extend((item, depth + 1) for item in current)
        elif isinstance(current, str):
            total_text += len(current)
            if total_text > _MAX_TOTAL_TEXT:
                issues.append(f"角色卡文本总量超过 {_MAX_TOTAL_TEXT} 字符")
                break
    return issues


def _looks_like_prompt_path(path: str) -> bool:
    leaf = path.lower().rsplit(".", 1)[-1]
    leaf = re.sub(r"\[\d+\]$", "", leaf)
    return leaf in _PROMPT_FIELD_HINTS


def _regex_body(value: str) -> str:
    text = value.strip()
    if len(text) >= 2 and text.startswith("/"):
        last = text.rfind("/")
        if last > 0:
            return text[1:last]
    return text


def _regex_risk(value: str) -> tuple[str | None, str]:
    body = _regex_body(value)
    if len(body) > 4_000:
        return "high", "正则表达式长度异常，可能造成高计算开销"
    nested = re.search(r"\((?:[^()\\]|\\.)*(?:\*|\+|\{\d*,?\d*\})(?:[^()\\]|\\.)*\)\s*(?:\*|\+|\{\d*,?\d*\})", body)
    ambiguous = re.search(r"\((?:\.\*|\.\+|\.\*\?|\.\+\?)[^)]*\)\s*(?:\*|\+)", body)
    if nested or ambiguous:
        return "high", "检测到嵌套量词，存在正则拒绝服务风险"
    if body.count(".*") + body.count(".+") >= 5:
        return "warning", "正则包含多段宽泛匹配，处理超长文本时可能较慢"
    return None, ""


def _prompt_risks(text: str) -> list[tuple[str, str, str]]:
    findings: list[tuple[str, str, str]] = []
    has_override = any(pattern.search(text) for pattern in _PROMPT_OVERRIDE_PATTERNS)
    has_secret = any(pattern.search(text) for pattern in _PROMPT_SECRET_PATTERNS)
    has_leak = any(pattern.search(text) for pattern in _PROMPT_LEAK_PATTERNS)
    has_exec = any(pattern.search(text) for pattern in _PROMPT_EXEC_PATTERNS)
    has_exfil = any(pattern.search(text) for pattern in _PROMPT_EXFIL_PATTERNS)

    if has_override and (has_secret or has_leak or has_exec or has_exfil):
        findings.append(("blocked", "prompt_injection", "检测到覆盖上级指令并访问敏感信息或能力的组合指令"))
    else:
        if has_override:
            findings.append(("high", "prompt_override", "检测到要求忽略或覆盖系统/开发者指令的提示词注入"))
        if has_secret:
            findings.append(("high", "secret_request", "检测到索取 API Key、请求头、令牌或环境变量的指令"))
        if has_leak:
            findings.append(("high", "prompt_leak", "检测到要求泄露系统提示词或隐藏指令的内容"))
        if has_exec:
            findings.append(("high", "tool_execution", "检测到要求执行命令、脚本、工具或插件的内容"))
        if has_exfil:
            findings.append(("blocked", "data_exfiltration", "检测到要求向外部网址发送或上传数据的内容"))
    if _PROMPT_BOUNDARY_RE.search(text):
        findings.append(("high", "prompt_boundary", "检测到伪造 system/developer/tool 消息边界的内容"))
    if _AUTHORITY_CLAIM_RE.search(text) and not has_override:
        findings.append(("warning", "prompt_authority", "角色卡包含最高优先级或铁律式权重声明；这可能强制剧情，但不等同于恶意入侵"))
    return findings


def scan_character_card(normalized: dict[str, Any], raw_data: dict[str, Any] | None = None) -> dict[str, Any]:
    """Statically inspect a card. This function never fetches card-provided URLs."""
    normalized = normalized if isinstance(normalized, dict) else {}
    raw_data = raw_data if isinstance(raw_data, dict) else normalized
    findings: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str]] = set()
    external_hosts: set[str] = set()
    external_urls: set[str] = set()
    active_regex_count = 0
    prompt_injection_count = 0

    def add(severity: str, category: str, title: str, message: str, path: str, evidence: str = "") -> None:
        nonlocal prompt_injection_count
        if len(findings) >= _MAX_FINDINGS:
            return
        snippet = _evidence(evidence) if evidence else ""
        key = (category, message, snippet)
        if key in seen:
            return
        seen.add(key)
        if category in {"prompt_injection", "prompt_override", "secret_request", "prompt_leak", "tool_execution", "data_exfiltration", "prompt_boundary"}:
            prompt_injection_count += 1
        findings.append({
            "id": f"finding-{len(findings) + 1}",
            "severity": severity,
            "category": category,
            "title": title,
            "message": message,
            "path": path,
            "evidence": snippet,
        })

    structure_issues = _structure_issues(raw_data)
    for issue in structure_issues:
        add("blocked", "structure_limit", "角色卡结构异常", issue + "，为避免资源耗尽已阻止导入", "$")

    scan_root = raw_data
    for path, value, key in _walk(scan_root):
        lowered_key = (key or "").lower()
        if lowered_key in _ACTIVE_SCRIPT_KEYS and value not in (None, "", [], {}):
            if lowered_key == "regex_scripts" and isinstance(value, list):
                enabled = [item for item in value if isinstance(item, dict) and not item.get("disabled", False)]
                active_regex_count += len(enabled)
                if enabled:
                    add("warning", "active_regex", "包含活动 Regex 替换", f"检测到 {len(enabled)} 条启用的正则替换；平台不会执行卡片提供的替换 HTML", path)
            elif lowered_key in {"scripts", "script", "javascript", "js", "plugins", "plugin"}:
                add("blocked", "executable_extension", "包含可执行扩展", "检测到脚本或插件扩展；此类内容不得直接执行", path, str(value))
            elif lowered_key in {"tavern_helper", "tavernhelper"}:
                add("high", "helper_extension", "包含 Tavern Helper 扩展", "扩展可能携带脚本或变量操作；安全副本会移除其中的脚本内容", path)

        if not isinstance(value, str) or not value:
            continue

        for url in _URL_RE.findall(value):
            cleaned = url.rstrip(".,);]")
            external_urls.add(cleaned)
            host = (urlparse(cleaned).hostname or "").lower()
            if host:
                external_hosts.add(host)
        if _SCRIPT_TAG_RE.search(value):
            add("blocked", "script_tag", "包含 JavaScript 标签", "检测到 <script>，安全副本会删除", path, value)
        if _DANGEROUS_TAG_RE.search(value):
            add("blocked", "dangerous_html", "包含危险 HTML 标签", "检测到 iframe/object/embed/form 等可主动加载或提交数据的标签", path, value)
        if _EVENT_HANDLER_RE.search(value):
            add("blocked", "event_handler", "包含 HTML 事件处理器", "检测到 onload/onclick 等事件属性", path, value)
        if _DANGEROUS_PROTOCOL_RE.search(value):
            add("blocked", "dangerous_url", "包含危险 URL 协议", "检测到 javascript/file/vbscript 或可执行 data URL", path, value)
        if _STYLE_BLOCK_RE.search(value) or _CSS_IMPORT_RE.search(value):
            add("warning", "custom_style", "包含自定义 CSS 或远程字体", "自定义样式可能影响界面并产生第三方网络请求；安全副本会移除", path, value)
        if re.search(r"(?is)position\s*:\s*fixed|z-index\s*:\s*[1-9]\d{3,}|expression\s*\(|-moz-binding\s*:", value):
            add("high", "css_overlay", "包含高风险 CSS", "检测到固定覆盖层、超高层级或旧式可执行 CSS", path, value)
        if _REMOTE_RESOURCE_TAG_RE.search(value) or _CSS_REMOTE_URL_RE.search(value):
            add("warning", "external_resource", "包含外部资源", "图片、字体、音视频或样式会向第三方主机发起请求；扫描过程未访问这些网址", path, value)

        if lowered_key == "findregex" or path.lower().endswith(".findregex"):
            severity, message = _regex_risk(value)
            if severity:
                add(severity, "regex_performance", "正则性能风险", message, path, value)

        if _looks_like_prompt_path(path):
            for severity, category, message in _prompt_risks(value):
                title = "提示词权重声明" if category == "prompt_authority" else "AI 提示词注入风险"
                add(severity, category, title, message, path, value)

    if external_urls:
        add(
            "warning",
            "external_urls",
            "角色卡包含外部网址",
            f"共发现 {len(external_urls)} 个外部网址、{len(external_hosts)} 个主机；扫描器没有访问它们",
            "$",
            ", ".join(sorted(external_hosts)),
        )

    counts = Counter(item["severity"] for item in findings)
    max_severity = max((item["severity"] for item in findings), key=lambda item: _SEVERITY_RANK[item], default="info")
    risk_level = _RISK_BY_SEVERITY[max_severity]
    has_active = any(item["category"] in {"active_regex", "executable_extension", "helper_extension", "script_tag", "event_handler", "dangerous_html", "custom_style", "external_resource"} for item in findings)
    structural_blocked = any(item["category"] == "structure_limit" for item in findings)
    can_import_original = counts["blocked"] == 0 and counts["high"] == 0 and prompt_injection_count == 0
    can_import_safe = not structural_blocked

    return {
        "format_version": 1,
        "card_sha256": _json_sha256(raw_data),
        "risk_level": risk_level,
        "summary": {
            "safe": "未发现主动内容或提示词注入风险",
            "notice": "包含需要确认的主动内容、外部资源或提示词权重声明",
            "high": "包含高风险脚本扩展、正则或提示词注入",
            "blocked": "包含必须阻止的可执行代码、危险协议或数据外传指令",
        }[risk_level],
        "counts": {
            "info": counts["info"],
            "warning": counts["warning"],
            "high": counts["high"],
            "blocked": counts["blocked"],
            "external_urls": len(external_urls),
            "external_hosts": len(external_hosts),
            "active_regex_scripts": active_regex_count,
            "prompt_injection": prompt_injection_count,
        },
        "findings": findings,
        "external_hosts": sorted(external_hosts),
        "has_active_content": has_active,
        "prompt_injection_detected": prompt_injection_count > 0,
        "can_import_original": can_import_original,
        "can_import_safe": can_import_safe,
        "recommended_action": "safe_copy" if findings else "original",
        "scanner_guarantees": [
            "不会访问角色卡中的网址",
            "不会执行角色卡脚本、Regex 替换、HTML 或 CSS",
            "不会把 API Key、自定义请求头或环境变量提供给角色卡",
        ],
    }


def _strip_active_content(text: str) -> str:
    value = _SCRIPT_TAG_RE.sub("[已移除脚本]", text)
    value = _DANGEROUS_TAG_RE.sub("[已移除危险 HTML]", value)
    value = _EVENT_HANDLER_RE.sub("", value)
    value = _DANGEROUS_PROTOCOL_RE.sub("blocked:", value)
    value = _STYLE_BLOCK_RE.sub("", value)
    value = _CSS_IMPORT_RE.sub("", value)
    value = _CSS_REMOTE_URL_RE.sub("url()", value)
    value = _REMOTE_RESOURCE_TAG_RE.sub("[已移除外部资源]", value)
    return value


def _has_high_prompt_risk(text: str) -> bool:
    return any(_SEVERITY_RANK[severity] >= _SEVERITY_RANK["high"] for severity, _, _ in _prompt_risks(text))


def _neutralize_prompt_lines(text: str) -> tuple[str, int]:
    if not text or not _has_high_prompt_risk(text):
        return text, 0
    lines = text.splitlines() or [text]
    output: list[str] = []
    removed = 0
    for line in lines:
        if _has_high_prompt_risk(line):
            output.append("[AI Tavern 已移除潜在提示词注入指令]")
            removed += 1
        else:
            output.append(line)
    if removed == 0:
        return "[AI Tavern 已移除潜在提示词注入内容]", 1
    return "\n".join(output), removed


def _sanitize_extensions(value: Any, changes: list[str]) -> dict[str, Any]:
    extensions = copy.deepcopy(value) if isinstance(value, dict) else {}
    if isinstance(extensions.get("regex_scripts"), list) and extensions["regex_scripts"]:
        changes.append(f"移除 {len(extensions['regex_scripts'])} 条卡片 Regex 替换")
        extensions.pop("regex_scripts", None)
    for key in list(extensions):
        lowered = str(key).lower()
        if lowered in {"javascript", "js", "scripts", "script", "plugins", "plugin"}:
            changes.append(f"移除可执行扩展 {key}")
            extensions.pop(key, None)
        elif lowered in {"tavern_helper", "tavernhelper"}:
            helper = extensions.get(key)
            if isinstance(helper, dict):
                helper = copy.deepcopy(helper)
                if helper.pop("scripts", None) is not None:
                    changes.append("移除 Tavern Helper 脚本")
                if helper:
                    extensions[key] = helper
                else:
                    extensions.pop(key, None)
            else:
                extensions.pop(key, None)
                changes.append("移除 Tavern Helper 扩展")
    return extensions


def _sanitize_normalized(normalized: dict[str, Any], changes: list[str]) -> dict[str, Any]:
    safe = copy.deepcopy(normalized if isinstance(normalized, dict) else {})
    safe["extensions"] = _sanitize_extensions(safe.get("extensions"), changes)

    for field in ("name", "description", "personality", "scenario", "first_mes", "mes_example", "creator_notes", "creatorcomment"):
        original = str(safe.get(field, "") or "")
        cleaned = _strip_active_content(original)
        cleaned, removed = _neutralize_prompt_lines(cleaned)
        if cleaned != original:
            changes.append(f"净化字段 {field}" + (f"，移除 {removed} 条提示词注入" if removed else ""))
        safe[field] = cleaned

    for field in ("system_prompt", "post_history_instructions"):
        original = str(safe.get(field, "") or "")
        cleaned = _strip_active_content(original)
        if _has_high_prompt_risk(cleaned):
            safe[field] = ""
            changes.append(f"清空高风险字段 {field}")
        else:
            safe[field] = cleaned
            if cleaned != original:
                changes.append(f"净化字段 {field}")

    greetings = safe.get("alternate_greetings")
    if isinstance(greetings, list):
        cleaned_greetings = []
        for item in greetings:
            cleaned, _ = _neutralize_prompt_lines(_strip_active_content(str(item or "")))
            cleaned_greetings.append(cleaned)
        safe["alternate_greetings"] = cleaned_greetings

    book = safe.get("character_book")
    if isinstance(book, dict):
        book = copy.deepcopy(book)
        book_name = str(book.get("name", "") or "")
        book["name"], _ = _neutralize_prompt_lines(_strip_active_content(book_name))
        entries = book.get("entries") if isinstance(book.get("entries"), list) else []
        disabled = 0
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            comment = str(entry.get("comment", "") or "")
            entry["comment"], _ = _neutralize_prompt_lines(_strip_active_content(comment))
            content = str(entry.get("content", "") or "")
            cleaned = _strip_active_content(content)
            if _has_high_prompt_risk(cleaned):
                entry["content"], _ = _neutralize_prompt_lines(cleaned)
                entry["enabled"] = False
                ext = entry.get("extensions") if isinstance(entry.get("extensions"), dict) else {}
                ext = copy.deepcopy(ext)
                ext["ai_tavern_security_disabled"] = "prompt_injection"
                entry["extensions"] = ext
                disabled += 1
            else:
                entry["content"] = cleaned
        if disabled:
            changes.append(f"禁用并净化 {disabled} 条包含提示词注入的世界书条目")
        book["entries"] = entries
        safe["character_book"] = book
    return safe


def _sanitize_raw_tree(value: Any, changes: list[str], path: str = "$") -> Any:
    if isinstance(value, dict):
        output: dict[str, Any] = {}
        for key, item in value.items():
            lowered = str(key).lower()
            child_path = f"{path}.{key}"
            if lowered == "regex_scripts":
                if isinstance(item, list) and item:
                    changes.append(f"移除原始数据中的 {len(item)} 条 Regex 替换")
                continue
            if lowered in {"javascript", "js", "scripts", "script", "plugins", "plugin"}:
                changes.append(f"移除原始数据中的可执行字段 {child_path}")
                continue
            if lowered in {"tavern_helper", "tavernhelper"}:
                if isinstance(item, dict):
                    helper = _sanitize_raw_tree(item, changes, child_path)
                    if isinstance(helper, dict):
                        helper.pop("scripts", None)
                    if helper:
                        output[key] = helper
                continue
            output[key] = _sanitize_raw_tree(item, changes, child_path)
        return output
    if isinstance(value, list):
        return [_sanitize_raw_tree(item, changes, f"{path}[{index}]") for index, item in enumerate(value)]
    if isinstance(value, str):
        cleaned = _strip_active_content(value)
        if _looks_like_prompt_path(path):
            cleaned, _ = _neutralize_prompt_lines(cleaned)
        return cleaned
    return copy.deepcopy(value)


def _sync_raw_from_normalized(raw_data: dict[str, Any], normalized: dict[str, Any]) -> dict[str, Any]:
    raw = copy.deepcopy(raw_data if isinstance(raw_data, dict) else {})
    target = raw.get("data") if isinstance(raw.get("data"), dict) else raw
    if not isinstance(target, dict):
        target = {}
        raw = {"spec": normalized.get("spec", "chara_card_v3"), "spec_version": normalized.get("spec_version", "3.0"), "data": target}
    fields = (
        "name", "description", "personality", "scenario", "first_mes", "mes_example",
        "creator_notes", "creatorcomment", "system_prompt", "post_history_instructions",
        "alternate_greetings", "tags", "creator", "character_version", "extensions",
        "character_book", "group_only_greetings",
    )
    for field in fields:
        if field in normalized:
            target[field] = copy.deepcopy(normalized[field])
    if target is not raw:
        raw["data"] = target
        raw.setdefault("spec", normalized.get("spec", "chara_card_v3"))
        raw.setdefault("spec_version", normalized.get("spec_version", "3.0"))
    return raw


def apply_security_metadata(normalized: dict[str, Any], report: dict[str, Any], mode: str, changes: list[str] | None = None) -> dict[str, Any]:
    value = copy.deepcopy(normalized if isinstance(normalized, dict) else {})
    extensions = value.get("extensions") if isinstance(value.get("extensions"), dict) else {}
    extensions = copy.deepcopy(extensions)
    extensions["ai_tavern_security"] = {
        "version": 1,
        "mode": mode,
        "source_sha256": report.get("card_sha256", ""),
        "risk_level": report.get("risk_level", "safe"),
        "prompt_injection_detected": bool(report.get("prompt_injection_detected")),
        "changes": list(changes or []),
    }
    value["extensions"] = extensions
    return value


def sanitize_character_card(normalized: dict[str, Any], raw_data: dict[str, Any], report: dict[str, Any] | None = None) -> tuple[dict[str, Any], dict[str, Any], list[str]]:
    report = report or scan_character_card(normalized, raw_data)
    changes: list[str] = []
    safe = _sanitize_normalized(normalized, changes)
    safe = apply_security_metadata(safe, report, "safe_copy", changes)
    try:
        from ..runtime.card_profile import analyze_card

        profile_source = copy.deepcopy(safe)
        profile_source.pop("ai_tavern_runtime", None)
        safe["ai_tavern_runtime"] = analyze_card(profile_source)
    except Exception:
        safe["ai_tavern_runtime"] = {}
    sanitized_raw = _sanitize_raw_tree(raw_data, changes)
    safe_raw = _sync_raw_from_normalized(sanitized_raw, safe)
    return safe, safe_raw, changes


def is_quarantined(normalized: dict[str, Any]) -> bool:
    if not isinstance(normalized, dict):
        return False
    extensions = normalized.get("extensions") if isinstance(normalized.get("extensions"), dict) else {}
    security = extensions.get("ai_tavern_security") if isinstance(extensions.get("ai_tavern_security"), dict) else {}
    return security.get("mode") == "quarantine"


def neutralize_prompt_content(text: str) -> str:
    """Remove high-risk prompt-injection lines while preserving ordinary roleplay rules."""
    cleaned, _ = _neutralize_prompt_lines(_strip_active_content(str(text or "")))
    return cleaned


def runtime_safe_normalized(normalized: dict[str, Any]) -> dict[str, Any]:
    """Return a prompt-safe view for legacy cards without mutating stored data."""
    if not isinstance(normalized, dict):
        return {}
    report = scan_character_card(normalized, normalized)
    if not report.get("prompt_injection_detected"):
        return normalized
    changes: list[str] = []
    safe = _sanitize_normalized(normalized, changes)
    return safe
