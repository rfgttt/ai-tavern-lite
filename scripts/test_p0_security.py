#!/usr/bin/env python3
"""AI Tavern Lite P0 security acceptance test.

Uses only the Python standard library. It can run repository-level security tests
and black-box checks against a running production deployment.
"""
from __future__ import annotations

import argparse
import base64
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

ROOT = Path(__file__).resolve().parents[1]


@dataclass
class Result:
    name: str
    passed: bool
    detail: str
    skipped: bool = False


def auth_header(username: str, password: str) -> str:
    token = base64.b64encode(f"{username}:{password}".encode("utf-8")).decode("ascii")
    return f"Basic {token}"


def request(
    base_url: str,
    path: str,
    *,
    method: str = "GET",
    username: str | None = None,
    password: str | None = None,
    body: bytes | None = None,
    content_type: str | None = None,
    timeout: float = 10,
) -> tuple[int, dict[str, str], bytes]:
    url = urllib.parse.urljoin(base_url.rstrip("/") + "/", path.lstrip("/"))
    headers = {"Accept": "application/json", "User-Agent": "AI-Tavern-P0-Test/1.0"}
    if username is not None and password is not None:
        headers["Authorization"] = auth_header(username, password)
    if content_type:
        headers["Content-Type"] = content_type
    req = urllib.request.Request(url, data=body, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:
            return response.status, {k.lower(): v for k, v in response.headers.items()}, response.read()
    except urllib.error.HTTPError as error:
        return error.code, {k.lower(): v for k, v in error.headers.items()}, error.read()


def add(results: list[Result], name: str, passed: bool, detail: str) -> None:
    results.append(Result(name, passed, detail))


def run_repository_tests(skip_pytest: bool) -> Result:
    if skip_pytest:
        return Result("代码级 P0 安全测试", True, "已按参数跳过", skipped=True)

    backend = ROOT / "backend"
    command = [sys.executable, "-m", "pytest", "-q", "tests/test_security_p0.py"]
    completed = subprocess.run(
        command,
        cwd=backend,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        env={**os.environ, "PYTHONPATH": str(backend)},
    )
    output = completed.stdout.strip()
    if completed.returncode == 0:
        tail = output.splitlines()[-1] if output else "pytest passed"
        return Result("代码级 P0 安全测试", True, tail)
    return Result("代码级 P0 安全测试", False, output[-1200:] or "pytest 执行失败")


def run_live_tests(args: argparse.Namespace) -> list[Result]:
    results: list[Result] = []
    base = args.base_url

    try:
        status, headers, _ = request(base, "/api/health", timeout=args.timeout)
        add(results, "健康检查无需登录", status == 200, f"HTTP {status}")
    except Exception as error:
        add(results, "连接服务器", False, f"无法连接 {base}: {error}")
        return results

    status, headers, _ = request(base, "/api/settings", timeout=args.timeout)
    add(
        results,
        "私有 API 拒绝未授权访问",
        status == 401 and "basic" in headers.get("www-authenticate", "").lower(),
        f"HTTP {status}, WWW-Authenticate={headers.get('www-authenticate', '<missing>')}",
    )

    status, _, _ = request(
        base,
        "/api/settings",
        username=args.username,
        password=args.password + "-wrong",
        timeout=args.timeout,
    )
    add(results, "错误密码被拒绝", status == 401, f"HTTP {status}")

    status, auth_headers, _ = request(
        base,
        "/api/settings",
        username=args.username,
        password=args.password,
        timeout=args.timeout,
    )
    add(results, "正确凭据可以访问", status == 200, f"HTTP {status}")

    required_headers = {
        "x-content-type-options": "nosniff",
        "x-frame-options": None,
        "referrer-policy": None,
        "content-security-policy": None,
    }
    missing = []
    for key, expected in required_headers.items():
        value = auth_headers.get(key)
        if not value or (expected and expected.lower() not in value.lower()):
            missing.append(key)
    add(
        results,
        "安全响应头已启用",
        not missing,
        "完整" if not missing else "缺少: " + ", ".join(missing),
    )

    for path, label in [
        ("/docs", "Swagger 文档关闭"),
        ("/redoc", "ReDoc 关闭"),
        ("/openapi.json", "OpenAPI 描述关闭"),
        ("/api/diagnostics/health", "诊断接口关闭"),
        ("/api/self-test/runs", "自测接口关闭"),
        ("/api/__p0_missing_route__", "不存在的 API 返回 404"),
    ]:
        status, _, _ = request(
            base, path, username=args.username, password=args.password, timeout=args.timeout
        )
        add(results, label, status == 404, f"HTTP {status}")

    payload = json.dumps(
        {
            "mock_llm": False,
            "base_url": "http://169.254.169.254/latest/meta-data",
            "api_key": "p0-test-placeholder",
            "model": "p0-test",
        }
    ).encode("utf-8")
    status, _, response_body = request(
        base,
        "/api/settings/test-connection",
        method="POST",
        username=args.username,
        password=args.password,
        body=payload,
        content_type="application/json",
        timeout=args.timeout,
    )
    response_text = response_body.decode("utf-8", errors="replace")[:180]
    add(
        results,
        "生产环境禁止提交临时模型地址",
        status == 403,
        f"HTTP {status}: {response_text}",
    )

    oversized = json.dumps({"value": "x" * (args.oversized_bytes + 1024)}).encode("utf-8")
    status, _, _ = request(
        base,
        "/api/settings",
        method="PUT",
        username=args.username,
        password=args.password,
        body=oversized,
        content_type="application/json",
        timeout=max(args.timeout, 20),
    )
    add(results, "超大 JSON 请求被拒绝", status == 413, f"HTTP {status}")

    if args.test_rate_limit:
        got_429 = False
        retry_after = ""
        for _ in range(args.rate_limit_attempts):
            status, headers, _ = request(base, "/api/health", timeout=args.timeout)
            if status == 429:
                got_429 = True
                retry_after = headers.get("retry-after", "<missing>")
                break
        add(
            results,
            "请求限流生效",
            got_429,
            f"检测到 HTTP 429, Retry-After={retry_after}" if got_429 else f"{args.rate_limit_attempts} 次内未出现 429",
        )
    else:
        results.append(Result("请求限流黑盒压测", True, "默认跳过；使用 --test-rate-limit 开启", skipped=True))

    return results


def print_report(results: Iterable[Result]) -> int:
    results = list(results)
    print("\nAI Tavern Lite · P0 安全验收报告")
    print("=" * 58)
    for item in results:
        marker = "SKIP" if item.skipped else ("PASS" if item.passed else "FAIL")
        print(f"[{marker:4}] {item.name}\n       {item.detail}")
    failed = [item for item in results if not item.passed and not item.skipped]
    passed = [item for item in results if item.passed and not item.skipped]
    skipped = [item for item in results if item.skipped]
    print("-" * 58)
    print(f"通过 {len(passed)}，失败 {len(failed)}，跳过 {len(skipped)}")
    if failed:
        print("结论：P0 验收未通过。请先修复 FAIL 项。")
        return 1
    print("结论：已执行项目全部通过。")
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="测试 AI Tavern Lite 的 P0 安全修复")
    parser.add_argument("--base-url", default="https://localhost", help="已启动项目的访问地址")
    parser.add_argument("--username", default=os.getenv("AI_TAVERN_AUTH_USERNAME", "admin"))
    parser.add_argument("--password", default=os.getenv("AI_TAVERN_AUTH_PASSWORD", ""))
    parser.add_argument("--timeout", type=float, default=10)
    parser.add_argument(
        "--oversized-bytes",
        type=int,
        default=int(os.getenv("AI_TAVERN_MAX_JSON_BODY_BYTES", str(2 * 1024 * 1024))),
        help="服务器 JSON 上限；脚本会发送略大于此值的请求",
    )
    parser.add_argument("--skip-pytest", action="store_true", help="跳过仓库代码级测试")
    parser.add_argument("--skip-live", action="store_true", help="只运行代码级测试，不连接服务器")
    parser.add_argument("--test-rate-limit", action="store_true", help="执行限流压测（会暂时触发当前 IP 限流）")
    parser.add_argument("--rate-limit-attempts", type=int, default=200)
    args = parser.parse_args()
    if not args.skip_live and not args.password:
        parser.error("黑盒测试需要 --password，或设置 AI_TAVERN_AUTH_PASSWORD 环境变量")
    return args


def main() -> int:
    args = parse_args()
    results = [run_repository_tests(args.skip_pytest)]
    if not args.skip_live:
        results.extend(run_live_tests(args))
    return print_report(results)


if __name__ == "__main__":
    raise SystemExit(main())
