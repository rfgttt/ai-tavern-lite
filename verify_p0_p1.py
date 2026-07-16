#!/usr/bin/env python3
"""
AI-Tavern-Lite P0/P1 一键验收脚本（Windows/macOS/Linux）

放置位置：
- 项目根目录：AI-Tavern-Lite/verify_p0_p1.py
- 或 tools/verify_p0_p1.py

运行：
    python verify_p0_p1.py
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Sequence


def find_project_root() -> Path:
    """从脚本所在目录向上查找同时包含 backend 和 frontend 的项目根目录。"""
    start = Path(__file__).resolve().parent

    for candidate in (start, *start.parents):
        if (candidate / "backend").is_dir() and (candidate / "frontend").is_dir():
            return candidate

    raise FileNotFoundError(
        "无法找到项目根目录：脚本所在目录及其上级目录中，"
        "没有同时包含 backend 和 frontend 的目录。"
    )


def find_backend_python(root: Path) -> str:
    """优先使用项目虚拟环境，否则使用当前 Python。"""
    candidates = [
        root / "backend" / ".venv" / "Scripts" / "python.exe",
        root / "backend" / "venv" / "Scripts" / "python.exe",
        root / ".venv" / "Scripts" / "python.exe",
        root / "venv" / "Scripts" / "python.exe",
        root / "backend" / ".venv" / "bin" / "python",
        root / "backend" / "venv" / "bin" / "python",
        root / ".venv" / "bin" / "python",
        root / "venv" / "bin" / "python",
    ]

    for candidate in candidates:
        if candidate.is_file():
            return str(candidate)

    return sys.executable


def find_npm() -> str | None:
    """Windows 上优先查找 npm.cmd。"""
    names = ["npm.cmd", "npm"] if os.name == "nt" else ["npm", "npm.cmd"]
    for name in names:
        resolved = shutil.which(name)
        if resolved:
            return resolved
    return None


def run_check(title: str, command: Sequence[str], cwd: Path) -> bool:
    print("\n" + "=" * 72)
    print(f"[运行] {title}")
    print(f"[目录] {cwd}")
    print(f"[命令] {' '.join(command)}")
    print("=" * 72)

    try:
        result = subprocess.run(
            list(command),
            cwd=str(cwd),
            check=False,
        )
    except FileNotFoundError as exc:
        print(f"\n[失败] 找不到命令或文件：{exc}")
        return False
    except OSError as exc:
        print(f"\n[失败] 无法启动命令：{exc}")
        return False

    if result.returncode == 0:
        print(f"\n[通过] {title}")
        return True

    print(f"\n[失败] {title}，退出码：{result.returncode}")
    return False


def main() -> int:
    print("AI-Tavern-Lite P0/P1 一键验收")
    print(f"脚本位置：{Path(__file__).resolve()}")

    try:
        root = find_project_root()
    except FileNotFoundError as exc:
        print(f"\n[错误] {exc}")
        print(
            "\n请把本脚本放到项目根目录，确保目录结构类似：\n"
            "AI-Tavern-Lite/\n"
            "  backend/\n"
            "  frontend/\n"
            "  verify_p0_p1.py"
        )
        return 2

    backend = root / "backend"
    frontend = root / "frontend"

    print(f"项目根目录：{root}")

    backend_python = find_backend_python(root)
    print(f"后端 Python：{backend_python}")

    results: list[tuple[str, bool]] = []

    # 后端完整回归测试
    results.append(
        (
            "P0/P1 后端回归测试",
            run_check(
                "P0/P1 后端回归测试",
                [backend_python, "-m", "pytest", "-q"],
                backend,
            ),
        )
    )

    # 前端生产构建
    npm = find_npm()
    if npm is None:
        print("\n[失败] 未找到 npm。请先安装 Node.js，并确认 npm 可在命令行中使用。")
        results.append(("前端生产构建", False))
    elif not (frontend / "package.json").is_file():
        print("\n[失败] frontend/package.json 不存在。")
        results.append(("前端生产构建", False))
    else:
        results.append(
            (
                "前端生产构建",
                run_check(
                    "前端生产构建",
                    [npm, "run", "build"],
                    frontend,
                ),
            )
        )

    print("\n" + "=" * 72)
    print("验收汇总")
    print("=" * 72)

    for name, passed in results:
        print(f"{'PASS' if passed else 'FAIL'}  {name}")

    passed_count = sum(1 for _, passed in results if passed)
    total = len(results)
    print(f"\n总计：{passed_count}/{total} 项通过")

    if all(passed for _, passed in results):
        print("\n✅ P0/P1 验收通过")
        return 0

    print("\n❌ P0/P1 验收未通过，请查看上方具体错误。")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
