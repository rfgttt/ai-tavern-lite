from abc import ABC, abstractmethod
from typing import List, Dict, Any, AsyncIterator, Optional
import asyncio
import json
from ...core.logging import logger
from ...core.config import settings
from ...core.security import validate_outbound_url


class LLMProvider(ABC):
    """Base interface for LLM providers."""

    @property
    def cancelled(self) -> bool:
        return bool(getattr(self, "_cancelled", False))

    @abstractmethod
    async def chat_completion(
        self,
        messages: List[Dict[str, str]],
        temperature: float = 0.7,
        top_p: float = 0.9,
        max_tokens: int = 1024,
        stream: bool = False,
        custom_headers: Optional[Dict[str, str]] = None
    ) -> AsyncIterator[str]:
        """Stream chat completion response."""
        pass

    @abstractmethod
    async def test_connection(self) -> tuple[bool, str]:
        """Test if the connection works. Returns (success, message)."""
        pass


class MockLLMProvider(LLMProvider):
    """Mock provider for testing without API key."""

    def __init__(self, character_name: str = "角色"):
        self.character_name = character_name
        self._cancelled = False

    def cancel(self):
        self._cancelled = True

    async def chat_completion(
        self,
        messages: List[Dict[str, str]],
        temperature: float = 0.7,
        top_p: float = 0.9,
        max_tokens: int = 1024,
        stream: bool = False,
        custom_headers: Optional[Dict[str, str]] = None
    ) -> AsyncIterator[str]:
        # Providers are single-use per chat request. Preserve an early cancel()
        # that may arrive after the SSE message event but before iteration begins.

        # Get last user message for context
        last_user_msg = ""
        for msg in reversed(messages):
            if msg["role"] == "user":
                last_user_msg = msg["content"]
                break

        response = f"（这是 Mock 模式的测试回复）\n\n你好，我是{self.character_name}。"

        if last_user_msg:
            if len(last_user_msg) > 20:
                preview = last_user_msg[:20] + "..."
            else:
                preview = last_user_msg
            response += f"\n\n我收到了你的消息：「{preview}」"

        response += "\n\nMock 模式运行正常，你可以在设置中配置真实的 API 接口来使用完整功能。"
        runtime_payload = {
            "patch": [
                {"op": "increment", "path": "/relationship/trust", "value": 1},
                {
                    "op": "replace",
                    "path": "/relationship/recent_reason",
                    "value": "你主动与角色展开了交流",
                },
            ],
            "events": ["角色认真回应了你的行动"],
            "choices": ["继续追问当前状况", "观察周围环境", "换一个轻松的话题"],
            "expression": "友善",
        }
        response += "\n<tavern_state>" + json.dumps(runtime_payload, ensure_ascii=False) + "</tavern_state>"

        # Stream character by character
        for char in response:
            if self._cancelled:
                break
            yield char
            await asyncio.sleep(0.02)

    async def test_connection(self) -> tuple[bool, str]:
        return True, "Mock 模式连接正常"


class OpenAICompatibleProvider(LLMProvider):
    """OpenAI-compatible API provider."""

    def __init__(
        self,
        base_url: str,
        api_key: str,
        model: str,
        timeout: int = 60
    ):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model
        self.timeout = timeout
        self._client = None
        self._cancelled = False

    def _get_client(self):
        if self._client is None:
            from openai import AsyncOpenAI
            self._client = AsyncOpenAI(
                base_url=self.base_url,
                api_key=self.api_key,
                timeout=self.timeout
            )
        return self._client

    def cancel(self):
        self._cancelled = True

    async def chat_completion(
        self,
        messages: List[Dict[str, str]],
        temperature: float = 0.7,
        top_p: float = 0.9,
        max_tokens: int = 1024,
        stream: bool = False,
        custom_headers: Optional[Dict[str, str]] = None
    ) -> AsyncIterator[str]:
        # Preserve cancellation requested before the upstream stream is opened.
        if self._cancelled:
            return
        client = self._get_client()

        extra_kwargs = {}
        if custom_headers:
            extra_kwargs["extra_headers"] = custom_headers

        try:
            response = await client.chat.completions.create(
                model=self.model,
                messages=messages,
                temperature=temperature,
                top_p=top_p,
                max_tokens=max_tokens,
                stream=True,
                **extra_kwargs
            )

            async for chunk in response:
                if self._cancelled:
                    break
                if chunk.choices and chunk.choices[0].delta.content:
                    yield chunk.choices[0].delta.content

        except Exception as e:
            error_msg = str(e)
            secrets = [self.api_key]
            if custom_headers:
                secrets.extend(value for value in custom_headers.values() if isinstance(value, str))
            for secret in secrets:
                if secret and secret in error_msg:
                    error_msg = error_msg.replace(secret, "***")
            logger.error(f"LLM request failed: {error_msg}")
            raise RuntimeError(error_msg) from e

    async def test_connection(self) -> tuple[bool, str]:
        """Test connection with a minimal request."""
        client = self._get_client()

        try:
            response = await client.chat.completions.create(
                model=self.model,
                messages=[{"role": "user", "content": "Hi"}],
                max_tokens=5,
                stream=False
            )
            return True, f"连接成功，模型: {self.model}"
        except Exception as e:
            error_msg = str(e)
            # Don't leak API key in error
            if self.api_key and self.api_key in error_msg:
                error_msg = error_msg.replace(self.api_key, "***")
            return False, f"连接失败: {error_msg}"


def get_provider(
    mock_mode: bool,
    base_url: str = "",
    api_key: str = "",
    model: str = "",
    character_name: str = "角色",
    timeout: int = 60
) -> LLMProvider:
    """Factory function to get the appropriate provider."""
    if mock_mode:
        logger.info("Using Mock LLM provider")
        return MockLLMProvider(character_name=character_name)

    missing = [
        name
        for name, value in (("Base URL", base_url), ("API Key", api_key), ("模型名称", model))
        if not str(value or "").strip()
    ]
    if missing:
        raise ValueError(f"真实模型配置不完整：缺少{'、'.join(missing)}。请完善设置或重新开启 Mock 模式。")

    validate_outbound_url(
        base_url,
        allow_private_hosts=settings.allow_private_llm_hosts,
        allowed_hosts=settings.llm_allowed_host_items,
    )

    # Normalize base_url - ensure it ends with /v1 if not present
    if "/v1" not in base_url:
        base_url = base_url.rstrip("/") + "/v1"

    logger.info(f"Using OpenAI-compatible provider: {base_url}, model: {model}")
    return OpenAICompatibleProvider(
        base_url=base_url,
        api_key=api_key,
        model=model,
        timeout=timeout
    )
