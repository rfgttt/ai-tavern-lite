from __future__ import annotations

import argparse
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import platform
import shlex
import shutil
import subprocess
import sys
import tempfile
import time
import traceback
from typing import Any, Callable
from urllib.parse import urlencode
import webbrowser
import zipfile

import httpx


PROJECT_ROOT = Path(__file__).resolve().parent.parent
BACKEND_DIR = PROJECT_ROOT / "backend"
OUTPUT_DIR = PROJECT_ROOT / "self-test-results"
HOST = "127.0.0.1"
PORT = 8765
BASE_URL = f"http://{HOST}:{PORT}"


@dataclass
class CaseResult:
    name: str
    status: str
    duration_ms: int
    detail: str = ""
    error: str = ""


class Recorder:
    def __init__(self) -> None:
        self.tests: list[CaseResult] = []
        self.lines: list[str] = []

    def log(self, message: str) -> None:
        line = f"[{datetime.now().strftime('%H:%M:%S')}] {message}"
        self.lines.append(line)
        print(line, flush=True)

    def run(self, name: str, action: Callable[[], Any]) -> Any:
        started = time.perf_counter()
        self.log(f"开始：{name}")
        try:
            value = action()
            if value is None:
                detail = ""
            elif isinstance(value, dict):
                identity = value.get("name") or value.get("title") or value.get("id") or value.get("status")
                detail = f"{identity or '对象'}（字段 {len(value)}）"
            elif isinstance(value, (list, tuple, set)):
                detail = f"{len(value)} 项"
            else:
                detail = str(value)
            result = CaseResult(name, "passed", round((time.perf_counter() - started) * 1000), detail=detail)
            self.tests.append(result)
            self.log(f"通过：{name}{' — ' + detail if detail else ''}")
            return value
        except Exception as error:
            message = f"{error.__class__.__name__}: {error}"
            result = CaseResult(name, "failed", round((time.perf_counter() - started) * 1000), error=message)
            self.tests.append(result)
            self.log(f"失败：{name} — {message}")
            return None

    def report(self) -> dict[str, Any]:
        failed = sum(1 for item in self.tests if item.status == "failed")
        return {
            "status": "failed" if failed else "passed",
            "finished_at": datetime.now(timezone.utc).isoformat(),
            "tests_total": len(self.tests),
            "tests_passed": len(self.tests) - failed,
            "tests_failed": failed,
            "tests": [asdict(item) for item in self.tests],
        }


class SelfTestRunner:
    def __init__(self, browser_timeout: int = 150, no_browser: bool = False) -> None:
        self.browser_timeout = browser_timeout
        self.no_browser = no_browser
        self.recorder = Recorder()
        self.temp_root = Path(tempfile.mkdtemp(prefix="ai-tavern-selftest-"))
        self.server_log = self.temp_root / "server.log"
        self.server_process: subprocess.Popen[str] | None = None
        self.client = httpx.Client(base_url=BASE_URL, timeout=30.0, follow_redirects=True)
        self.run_id = ""
        self.context: dict[str, Any] = {}
        self.browser_process: subprocess.Popen[str] | None = None

    def environment(self) -> dict[str, str]:
        def command_version(command: list[str]) -> str:
            try:
                completed = subprocess.run(command, capture_output=True, text=True, timeout=10, check=False)
                return (completed.stdout or completed.stderr).strip().splitlines()[0]
            except Exception:
                return "unavailable"

        return {
            "platform": platform.platform(),
            "python": sys.version.split()[0],
            "python_executable": str(Path(sys.executable).resolve()),
            "node": command_version(["node", "--version"]),
            "npm": command_version(["npm", "--version"]),
            "project_root": str(PROJECT_ROOT),
        }

    def _server_env(self) -> dict[str, str]:
        data = self.temp_root / "data"
        env = os.environ.copy()
        overrides = {
            "AI_TAVERN_HOST": HOST,
            "AI_TAVERN_PORT": str(PORT),
            "AI_TAVERN_DATABASE_URL": f"sqlite:///{(data / 'selftest.db').as_posix()}",
            "AI_TAVERN_DATA_DIR": str(data),
            "AI_TAVERN_CHARACTERS_DIR": str(data / "characters"),
            "AI_TAVERN_AVATARS_DIR": str(data / "avatars"),
            "AI_TAVERN_EXPORTS_DIR": str(data / "exports"),
            "AI_TAVERN_BACKUPS_DIR": str(data / "backups"),
            "AI_TAVERN_LOGS_DIR": str(data / "logs"),
            "AI_TAVERN_DIAGNOSTICS_DIR": str(data / "diagnostics"),
            "AI_TAVERN_FRONTEND_DIST_DIR": str(PROJECT_ROOT / "frontend" / "dist"),
        }
        env.update(overrides)
        return env

    def start_server(self) -> str:
        try:
            response = self.client.get("/api/health", timeout=1.0)
            if response.status_code == 200:
                raise RuntimeError(f"端口 {PORT} 已被其他服务占用，请关闭该服务后重试")
        except httpx.ConnectError:
            pass
        except httpx.TimeoutException:
            pass

        self.server_log.parent.mkdir(parents=True, exist_ok=True)
        log_handle = self.server_log.open("w", encoding="utf-8")
        self.server_process = subprocess.Popen(
            [sys.executable, "-m", "uvicorn", "app.main:app", "--host", HOST, "--port", str(PORT)],
            cwd=BACKEND_DIR,
            env=self._server_env(),
            stdout=log_handle,
            stderr=subprocess.STDOUT,
            text=True,
        )
        deadline = time.time() + 45
        last_error = ""
        while time.time() < deadline:
            if self.server_process.poll() is not None:
                raise RuntimeError(f"自检服务提前退出，代码 {self.server_process.returncode}\n{self._tail(self.server_log)}")
            try:
                response = self.client.get("/api/health", timeout=2.0)
                if response.status_code == 200:
                    return f"PID {self.server_process.pid}, {BASE_URL}"
                last_error = f"HTTP {response.status_code}"
            except Exception as error:
                last_error = str(error)
            time.sleep(0.25)
        raise RuntimeError(f"等待自检服务启动超时：{last_error}\n{self._tail(self.server_log)}")

    @staticmethod
    def _tail(path: Path, limit: int = 20000) -> str:
        try:
            text = path.read_text("utf-8", errors="replace")
            return text[-limit:]
        except OSError:
            return ""

    @staticmethod
    def _test_card(name: str, accent: str) -> dict[str, Any]:
        return {
            "spec": "chara_card_v3",
            "spec_version": "3.0",
            "data": {
                "name": name,
                "description": f"用于 AI Tavern 一键自检的临时角色 {name}。",
                "personality": "冷静、友善、说话清晰。",
                "scenario": "一座用于系统检查的虚拟遗迹。",
                "first_mes": f"{name}：“自检会话已经建立。”\n\n<StatusPlaceHolderImpl/>",
                "mes_example": "",
                "alternate_greetings": [f"{name}：“我们继续检查。”"],
                "tags": ["self-test"],
                "extensions": {
                    "tavern_helper": {
                        "variables": {
                            "stat_data": {
                                "world_state": {"location": "Self-Test Atrium", "time": "09:00"},
                                name: {"affection": 12, "mood": "focused", "keepsakes": {"test token": {"note": "isolated"}}},
                            }
                        },
                        "scripts": [{
                            "name": "Isolated remote helper",
                            "enabled": True,
                            "content": "import 'https://example.invalid/self-test-helper.js';",
                        }],
                    },
                    "regex_scripts": [
                        {
                            "scriptName": "变量更新检测",
                            "findRegex": "/<update_variable>[\\s\\S]*?<\\/update_variable>/gi",
                            "replaceString": "",
                            "disabled": False,
                        }
                    ],
                    "ai_tavern_ui": {
                        "schema": "ai-tavern-ui/1",
                        "speakerStyles": {name: {"color": accent}},
                        "panels": [{"id": "state", "component": "key-value", "source": "/custom"}],
                    },
                    "unknown_selftest_extension": {"preserve": True},
                },
                "character_book": {
                    "entries": [
                        {
                            "id": 1,
                            "keys": ["自检", "遗迹"],
                            "comment": "自检世界书",
                            "content": "当前变量：{{format_message_variable::stat_data}}。当用户提到自检或遗迹时，保持当前系统检查场景。可使用 <dice> 和 <battlecheck>。变量更新使用 UpdateVariable / JSONPatch。",
                            "constant": False,
                            "enabled": True,
                            "insertion_order": 100,
                            "position": "before_char",
                        }
                    ]
                },
            },
        }

    def create_run(self) -> str:
        response = self.client.post("/api/self-test/runs")
        response.raise_for_status()
        self.run_id = response.json()["run_id"]
        return self.run_id

    def configure_mock(self) -> str:
        response = self.client.put("/api/settings", json={"mock_llm": True, "max_tokens": 1024, "context_window": 8192})
        response.raise_for_status()
        payload = response.json()
        if not payload.get("mock_llm"):
            raise AssertionError("Mock 模式未启用")
        return "隔离数据库 Mock 模式已启用"

    def import_card(self, name: str, accent: str) -> dict[str, Any]:
        raw = json.dumps(self._test_card(name, accent), ensure_ascii=False).encode("utf-8")
        response = self.client.post(
            "/api/characters/import",
            files={"file": (f"{name}.json", raw, "application/json")},
        )
        response.raise_for_status()
        return response.json()

    def sse_chat(self, session_id: str, message: str) -> dict[str, Any]:
        events: list[dict[str, Any]] = []
        with self.client.stream(
            "POST",
            "/api/chat/stream",
            json={"session_id": session_id, "message": message},
            timeout=90.0,
        ) as response:
            response.raise_for_status()
            for line in response.iter_lines():
                if not line.startswith("data: "):
                    continue
                raw = line[6:]
                if not raw or raw == "[DONE]":
                    continue
                events.append(json.loads(raw))
        done = next((item for item in reversed(events) if item.get("type") == "done"), None)
        if not done:
            raise AssertionError("SSE 没有 done 事件")
        return {"events": events, "done": done}

    def open_browser(self, character_id: str, session_id: str) -> str:
        query = urlencode({"run_id": self.run_id, "character_id": character_id, "session_id": session_id})
        url = f"{BASE_URL}/self-test?{query}"
        if self.no_browser:
            return f"已跳过浏览器：{url}"
        command = os.environ.get("AI_TAVERN_SELFTEST_BROWSER", "").strip()
        if command:
            args = shlex.split(command) + [url]
            self.browser_process = subprocess.Popen(args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return "浏览器命令：" + " ".join(args[:-1])
        opened = webbrowser.open(url, new=2)
        if not opened:
            raise RuntimeError(f"无法自动打开浏览器，请手动打开：{url}")
        return url

    def wait_frontend(self) -> str:
        if self.no_browser:
            report = {
                "status": "failed",
                "finished_at": datetime.now(timezone.utc).isoformat(),
                "tests": [{"name": "浏览器端自检", "status": "failed", "duration_ms": 0, "error": "使用了 --no-browser"}],
            }
            self.client.post(f"/api/self-test/runs/{self.run_id}/frontend", json=report).raise_for_status()
            raise RuntimeError("浏览器测试被跳过")
        deadline = time.time() + self.browser_timeout
        while time.time() < deadline:
            response = self.client.get(f"/api/self-test/runs/{self.run_id}")
            response.raise_for_status()
            frontend = response.json().get("frontend")
            if isinstance(frontend, dict) and frontend.get("status") in {"passed", "failed"}:
                tests = frontend.get("tests") or []
                failed = sum(1 for item in tests if item.get("status") == "failed")
                if frontend.get("status") == "failed" or failed:
                    raise AssertionError(f"浏览器端 {len(tests)} 项测试中有 {failed} 项失败")
                return f"{len(tests)} 项，全部通过"
            if self.browser_process and self.browser_process.poll() is not None:
                raise RuntimeError(f"浏览器进程提前退出，代码 {self.browser_process.returncode}")
            time.sleep(0.5)
        timeout_report = {
            "status": "failed",
            "finished_at": datetime.now(timezone.utc).isoformat(),
            "tests": [{"name": "浏览器端自检", "status": "failed", "duration_ms": self.browser_timeout * 1000, "error": "等待浏览器结果超时"}],
        }
        self.client.post(f"/api/self-test/runs/{self.run_id}/frontend", json=timeout_report).raise_for_status()
        raise TimeoutError(f"等待浏览器自检超时（{self.browser_timeout} 秒）")

    def post_backend_report(self) -> None:
        if not self.run_id:
            return
        payload = {**self.recorder.report(), "environment": self.environment()}
        self.client.post(f"/api/self-test/runs/{self.run_id}/backend", json=payload).raise_for_status()
        self.client.post(f"/api/self-test/runs/{self.run_id}/context", json=self.context).raise_for_status()

    def export(self) -> Path:
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        response = self.client.post(f"/api/self-test/runs/{self.run_id}/export", timeout=30.0)
        response.raise_for_status()
        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        output = OUTPUT_DIR / f"ai-tavern-self-test-{timestamp}.zip"
        output.write_bytes(response.content)
        with zipfile.ZipFile(output, "a", compression=zipfile.ZIP_DEFLATED) as archive:
            archive.writestr("runner.log", "\n".join(self.recorder.lines))
            server_log = self._tail(self.server_log)
            if server_log:
                archive.writestr("isolated-server.log", server_log)
        return output

    def fallback_export(self, reason: str) -> Path:
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        output = OUTPUT_DIR / f"ai-tavern-self-test-failed-{timestamp}.zip"
        payload = {**self.recorder.report(), "fatal_error": reason, "environment": self.environment()}
        with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            archive.writestr("self-test-summary.json", json.dumps(payload, ensure_ascii=False, indent=2))
            archive.writestr("runner.log", "\n".join(self.recorder.lines))
            server_log = self._tail(self.server_log)
            if server_log:
                archive.writestr("isolated-server.log", server_log)
        return output

    def run(self) -> tuple[Path, bool]:
        output: Path | None = None
        fatal = ""
        try:
            self.recorder.run("启动隔离自检服务", self.start_server)
            if not self.server_process or self.server_process.poll() is not None:
                raise RuntimeError("隔离自检服务没有运行")

            self.recorder.run("基础健康检查", lambda: self._expect_json("/api/health", "status", "ok"))
            self.recorder.run("现有 8000 实例只读检查", self._live_instance_health)
            self.recorder.run("诊断健康检查", lambda: self._expect_status("/api/diagnostics/health", {"ok", "degraded"}))
            self.recorder.run("创建自检运行", self.create_run)
            self.recorder.run("启用 Mock 模式", self.configure_mock)
            first = self.recorder.run("导入测试角色 A", lambda: self.import_card("自检角色·艾琳", "#9b8cff"))
            second = self.recorder.run("导入测试角色 B", lambda: self.import_card("自检角色·莉亚", "#e8a64c"))
            if not isinstance(first, dict) or not isinstance(second, dict):
                raise RuntimeError("测试角色导入失败，无法继续")

            char_a = first["id"]
            char_b = second["id"]
            compatibility = self.recorder.run("角色卡兼容报告", lambda: self._compatibility(char_a))
            persona = self.recorder.run("Persona 创建", lambda: self._post_json("/api/personas", {
                "name": "自检旅行者", "pronouns": "他", "description": "用于一键自检的临时 Persona。", "is_default": False,
            }))
            group = self.recorder.run("多角色编组创建", lambda: self._post_json("/api/groups", {
                "name": "自检队伍", "description": "临时测试编组", "character_ids": [char_a, char_b], "metadata": {"self_test": True},
            }))
            if not isinstance(persona, dict) or not isinstance(group, dict):
                raise RuntimeError("Persona 或编组创建失败")

            session = self.recorder.run("群聊会话创建", lambda: self._post_json("/api/sessions", {
                "character_id": char_a,
                "title": "一键自检会话",
                "persona_id": persona["id"],
                "group_id": group["id"],
            }))
            if not isinstance(session, dict):
                raise RuntimeError("测试会话创建失败")
            session_id = session["id"]
            self.recorder.run("会话删除 API", lambda: self._session_delete(char_a))
            self.recorder.run(
                "Tavern 初始变量与状态投影",
                lambda: self._card_runtime_initialization(session_id, first["name"]),
            )

            self.recorder.run("初始消息读取", lambda: self._messages(session_id, minimum=1))
            first_chat = self.recorder.run("Mock SSE 与状态补丁", lambda: self._verify_chat(session_id))
            self.recorder.run("消息持久化", lambda: self._messages(session_id, minimum=3))
            self.recorder.run("运行时状态持久化", lambda: self._runtime(session_id))
            branch = self.recorder.run("剧情分支保存", lambda: self._post_json(f"/api/sessions/{session_id}/branches", {"title": "自检保存点"}))
            self.recorder.run("分支后的第二轮生成", lambda: self._verify_chat(session_id, "继续向前并记录第二轮变化。"))
            if isinstance(branch, dict):
                self.recorder.run("剧情分支恢复", lambda: self._restore_branch(session_id, branch))
                self.recorder.run("分支运行时快照恢复", lambda: self._timeline_snapshot(session_id))
            self.recorder.run("Prompt 预算与历史保留", lambda: self._prompt_preview(session_id))
            self.recorder.run("最近请求诊断", lambda: self._latest_diagnostics(first_chat))
            self.recorder.run("诊断 ZIP 可读", self._diagnostics_zip)
            self.recorder.run("准备前端长会话", lambda: self._seed_frontend_messages(session_id))

            self.context = {
                "isolated": True,
                "base_url": BASE_URL,
                "run_id": self.run_id,
                "character_id": char_a,
                "secondary_character_id": char_b,
                "session_id": session_id,
                "persona_id": persona["id"],
                "group_id": group["id"],
                "compatibility_summary": compatibility,
            }
            self.post_backend_report()
            self.recorder.run("打开浏览器前端自检", lambda: self.open_browser(char_a, session_id))
            self.recorder.run("等待浏览器前端结果", self.wait_frontend)
            self.post_backend_report()
            output = self.recorder.run("导出合并自检包", self.export)
        except Exception as error:
            fatal = f"{error.__class__.__name__}: {error}"
            self.recorder.log(f"致命错误：{fatal}")
            self.recorder.log(traceback.format_exc())
            try:
                self.post_backend_report()
                if self.run_id:
                    output = self.export()
            except Exception as export_error:
                self.recorder.log(f"服务端导出失败：{export_error}")
            if output is None:
                output = self.fallback_export(fatal)
        finally:
            self.close()

        final_report = self.recorder.report()
        success = not fatal and final_report["status"] == "passed"
        return output, success


    def _seed_frontend_messages(self, session_id: str) -> str:
        for index in range(10):
            role = "user" if index % 2 == 0 else "assistant"
            content = f"前端滚动恢复测试消息 {index + 1}。" + ("这是一段用于撑开消息列表高度的安全测试文本。" * 4)
            response = self.client.post(
                f"/api/sessions/{session_id}/messages",
                json={"session_id": session_id, "role": role, "content": content},
            )
            response.raise_for_status()
        return "新增 10 条隔离测试消息"


    def _live_instance_health(self) -> str:
        try:
            response = httpx.get("http://127.0.0.1:8000/api/diagnostics/health", timeout=2.0)
            if response.status_code != 200:
                return f"运行中，但返回 HTTP {response.status_code}"
            payload = response.json()
            return f"version={payload.get('version', 'unknown')}, status={payload.get('status', 'unknown')}"
        except (httpx.ConnectError, httpx.TimeoutException):
            return "未检测到正在运行的 8000 实例（不影响隔离自检）"

    def _expect_json(self, path: str, key: str, expected: Any) -> str:
        response = self.client.get(path)
        response.raise_for_status()
        payload = response.json()
        if payload.get(key) != expected:
            raise AssertionError(f"{key}={payload.get(key)!r}, 期望 {expected!r}")
        return f"{key}={expected}"

    def _expect_status(self, path: str, allowed: set[str]) -> str:
        response = self.client.get(path)
        response.raise_for_status()
        status = response.json().get("status")
        if status not in allowed:
            raise AssertionError(f"status={status}")
        return f"status={status}"

    def _post_json(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        response = self.client.post(path, json=payload)
        response.raise_for_status()
        return response.json()

    def _compatibility(self, character_id: str) -> str:
        response = self.client.get(f"/api/characters/{character_id}/compatibility")
        response.raise_for_status()
        payload = response.json()
        capabilities = payload.get("capabilities") or {}
        required = ["worldbook", "alternate_greetings", "regex", "mvu", "ui_manifest"]
        missing = [key for key in required if not capabilities.get(key)]
        if missing:
            raise AssertionError("未识别能力：" + ", ".join(missing))
        if "unknown_selftest_extension" not in payload.get("unknown_extensions", []):
            raise AssertionError("未知扩展没有被保留")
        details = payload.get("details") or []
        labels = {item.get("label") for item in details if isinstance(item, dict)}
        for label in ("世界书", "Regex 显示规则", "MVU / 变量更新", "角色卡状态栏"):
            if label not in labels:
                raise AssertionError(f"兼容报告缺少人类可读结论：{label}")
        runtime_checks = payload.get("runtime_checks") or {}
        expected_checks = {
            "initial_variables": "supported",
            "patch_paths": "supported",
            "read_only_macros": "supported",
            "status_placeholder": "supported",
            "external_javascript": "isolated",
        }
        for key, expected in expected_checks.items():
            actual = (runtime_checks.get(key) or {}).get("status")
            if actual != expected:
                raise AssertionError(f"运行级兼容检查 {key}={actual!r}，期望 {expected!r}")
        return ", ".join(required) + f"；{len(details)} 条说明；{len(runtime_checks)} 项运行验证"

    def _card_runtime_initialization(self, session_id: str, character_name: str) -> str:
        response = self.client.get(f"/api/sessions/{session_id}/runtime")
        response.raise_for_status()
        state = response.json().get("state") or {}
        custom = state.get("custom") or {}
        character_state = custom.get(character_name) or {}
        scene = state.get("scene") or {}
        relationship = state.get("relationship") or {}
        if character_state.get("affection") != 12:
            raise AssertionError(f"卡片初始好感未加载：{character_state.get('affection')!r}")
        if scene.get("location") != "Self-Test Atrium":
            raise AssertionError(f"卡片初始场景未投影：{scene.get('location')!r}")
        if relationship.get("affection") != 12:
            raise AssertionError(f"卡片关系投影未建立：{relationship.get('affection')!r}")
        return "初始变量、场景与关系投影正常"

    def _session_delete(self, character_id: str) -> str:
        session = self._post_json("/api/sessions", {"character_id": character_id, "title": "待删除自检会话"})
        session_id = session["id"]
        response = self.client.delete(f"/api/sessions/{session_id}")
        response.raise_for_status()
        if not response.json().get("success"):
            raise AssertionError("会话删除没有返回 success")
        missing = self.client.get(f"/api/sessions/{session_id}/messages")
        if missing.status_code != 404:
            raise AssertionError(f"删除后会话仍可读取：HTTP {missing.status_code}")
        return "会话及关联消息已删除"

    def _messages(self, session_id: str, minimum: int) -> str:
        response = self.client.get(f"/api/sessions/{session_id}/messages")
        response.raise_for_status()
        messages = response.json()
        if len(messages) < minimum:
            raise AssertionError(f"消息数 {len(messages)} < {minimum}")
        if any(message.get("generation_status") == "generating" for message in messages):
            raise AssertionError("存在永久 generating 消息")
        return f"{len(messages)} 条"

    def _verify_chat(self, session_id: str, message: str = "执行一轮自检，更新关系状态并给出行动选项。") -> dict[str, Any]:
        result = self.sse_chat(session_id, message)
        done = result["done"]
        if done.get("status") != "complete":
            raise AssertionError(f"完成状态：{done.get('status')}")
        runtime = done.get("runtime") or {}
        if not runtime.get("patch"):
            raise AssertionError("没有状态补丁")
        if not runtime.get("choices"):
            raise AssertionError("没有行动选项")
        if not done.get("segments"):
            raise AssertionError("没有消息 AST")
        if "<tavern_state>" in str(done.get("content", "")):
            raise AssertionError("隐藏状态标签泄漏到正文")
        return done

    def _runtime(self, session_id: str) -> str:
        response = self.client.get(f"/api/sessions/{session_id}/runtime")
        response.raise_for_status()
        payload = response.json()
        if payload.get("revision", 0) < 1:
            raise AssertionError("运行时 revision 未增加")
        trust = ((payload.get("state") or {}).get("relationship") or {}).get("trust")
        if not isinstance(trust, (int, float)) or trust < 1:
            raise AssertionError(f"trust 未更新：{trust}")
        return f"revision={payload['revision']}, trust={trust}"

    def _restore_branch(self, session_id: str, branch: dict[str, Any]) -> str:
        response = self.client.post(f"/api/sessions/{session_id}/branches/{branch['id']}/restore")
        response.raise_for_status()
        payload = response.json()
        if not payload.get("success"):
            raise AssertionError("分支恢复未成功")
        messages = self.client.get(f"/api/sessions/{session_id}/messages").json()
        if len(messages) != branch.get("message_count"):
            raise AssertionError(f"恢复后消息数 {len(messages)} != {branch.get('message_count')}")
        return f"恢复 {len(messages)} 条消息"

    def _timeline_snapshot(self, session_id: str) -> str:
        response = self.client.get(f"/api/sessions/{session_id}/timeline")
        response.raise_for_status()
        timeline = response.json()
        if not timeline:
            raise AssertionError("分支恢复后运行时快照为空")
        dynamic_turns = [
            turn for turn in timeline
            if turn.get("patch") or turn.get("dice") or turn.get("battle_checks") or turn.get("battle")
        ]
        if not dynamic_turns:
            raise AssertionError("分支恢复后的快照不含动态数据")
        return f"{len(timeline)} 个快照，{len(dynamic_turns)} 个含动态数据"

    def _prompt_preview(self, session_id: str) -> str:
        response = self.client.post("/api/chat/prompt-preview", json={"session_id": session_id, "message": "请回忆刚才的自检。"})
        response.raise_for_status()
        payload = response.json()
        if payload.get("total_estimated_tokens", 0) <= 0:
            raise AssertionError("Token 估算为空")
        history = next((item for item in payload.get("sections", []) if item.get("name") == "聊天历史"), None)
        if not history:
            raise AssertionError("Prompt 没有保留聊天历史")
        return f"tokens≈{payload['total_estimated_tokens']}"

    def _latest_diagnostics(self, done: Any) -> str:
        response = self.client.get("/api/diagnostics/latest")
        response.raise_for_status()
        payload = response.json()
        if not payload or payload.get("status") != "complete":
            raise AssertionError("最近请求诊断不完整")
        if payload.get("mock_mode") is not True:
            raise AssertionError("诊断没有记录 Mock 模式")
        if (payload.get("state") or {}).get("parser_errors", 0) != 0:
            raise AssertionError("状态解析存在错误")
        return f"request_id={payload.get('request_id')}"

    def _diagnostics_zip(self) -> str:
        response = self.client.post("/api/diagnostics/export")
        response.raise_for_status()
        temp = self.temp_root / "diagnostics-check.zip"
        temp.write_bytes(response.content)
        with zipfile.ZipFile(temp) as archive:
            required = {"health.json", "system.json", "settings-sanitized.json", "database-summary.json"}
            missing = required.difference(archive.namelist())
            if missing:
                raise AssertionError("诊断包缺少：" + ", ".join(sorted(missing)))
        return f"{len(response.content)} bytes"

    def close(self) -> None:
        try:
            self.client.close()
        except Exception:
            pass
        if self.browser_process and self.browser_process.poll() is None:
            try:
                self.browser_process.terminate()
            except Exception:
                pass
        if self.server_process and self.server_process.poll() is None:
            try:
                self.server_process.terminate()
                self.server_process.wait(timeout=8)
            except Exception:
                try:
                    self.server_process.kill()
                except Exception:
                    pass
        shutil.rmtree(self.temp_root, ignore_errors=True)


def main() -> int:
    parser = argparse.ArgumentParser(description="AI Tavern one-click self-test")
    parser.add_argument("--browser-timeout", type=int, default=150)
    parser.add_argument("--no-browser", action="store_true")
    args = parser.parse_args()

    print("=" * 68)
    print("AI Tavern 2.2 一键自检")
    print("测试使用隔离数据库，不会修改你的角色、聊天记录或 API Key。")
    print("=" * 68)
    runner = SelfTestRunner(browser_timeout=max(30, args.browser_timeout), no_browser=args.no_browser)
    output, success = runner.run()
    print("\n" + "=" * 68)
    print(f"自检报告：{output}")
    print("结果：" + ("通过" if success else "发现问题（请上传该 ZIP）"))
    print("=" * 68)
    if os.name == "nt":
        try:
            os.startfile(output.parent)  # type: ignore[attr-defined]
        except OSError:
            pass
    return 0 if success else 1


if __name__ == "__main__":
    raise SystemExit(main())
