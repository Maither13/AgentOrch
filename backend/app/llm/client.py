"""DeepSeek 客户端封装（OpenAI 兼容接口）。

设计意图：
- Agent / Workflow 层不直接接触 openai SDK，只依赖这里的数据结构；
  以后接多模型路由（Qwen、GLM、本地 vLLM）时只需替换本文件。
- 统一做三件事：请求构造、错误归一化、用量与延迟统计。
- 支持 mock 模式，便于无网络/无 Key 时跑单测和前端联调。
"""

from __future__ import annotations

import asyncio
import logging
import time
import uuid
from dataclasses import dataclass, field
from typing import AsyncIterator, Sequence

from openai import (
    APIConnectionError,
    APIStatusError,
    APITimeoutError,
    AsyncOpenAI,
    AuthenticationError,
    BadRequestError,
    RateLimitError,
)

from app.core.config import Settings
from app.core.errors import LLMError

logger = logging.getLogger(__name__)

Message = dict[str, str]


# --------------------------------------------------------------------------- #
# 数据结构
# --------------------------------------------------------------------------- #
@dataclass(slots=True)
class Usage:
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0


@dataclass(slots=True)
class ChatResult:
    id: str
    model: str
    content: str
    latency_ms: int
    mode: str
    reasoning_content: str | None = None
    usage: Usage = field(default_factory=Usage)
    finish_reason: str | None = None


@dataclass(slots=True)
class StreamChunk:
    content: str = ""
    reasoning_content: str = ""
    finish_reason: str | None = None
    usage: Usage | None = None


# --------------------------------------------------------------------------- #
# 客户端
# --------------------------------------------------------------------------- #
class DeepSeekClient:
    provider = "deepseek"

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._mode = settings.llm_mode
        self._client: AsyncOpenAI | None = None

        if self._mode == "live":
            self._client = AsyncOpenAI(
                api_key=settings.deepseek_api_key,
                base_url=settings.deepseek_base_url,
                timeout=settings.llm_timeout,
                max_retries=settings.llm_max_retries,
            )
            logger.info(
                "DeepSeek 客户端就绪 base_url=%s model=%s",
                settings.deepseek_base_url,
                settings.deepseek_model,
            )
        elif self._mode == "mock":
            logger.warning("LLM_MOCK 已开启：模型调用走本地模拟，不会产生真实请求")
        else:
            logger.warning("未配置 DEEPSEEK_API_KEY：/chat 将返回 503（可设 LLM_MOCK=true 离线演示）")

    # ---------------- 属性 ----------------
    @property
    def mode(self) -> str:
        return self._mode

    @property
    def available(self) -> bool:
        return self._mode != "unconfigured"

    @property
    def default_model(self) -> str:
        return self._settings.deepseek_model

    @property
    def base_url(self) -> str:
        return self._settings.deepseek_base_url

    # ---------------- 生命周期 ----------------
    async def aclose(self) -> None:
        if self._client is not None:
            await self._client.close()

    # ---------------- 对外 API ----------------
    async def chat(
        self,
        messages: Sequence[Message],
        *,
        model: str | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
        json_mode: bool = False,
    ) -> ChatResult:
        """一次性返回完整回答。"""
        model = model or self.default_model
        if self._mode == "mock":
            return await self._mock_chat(messages, model)

        client = self._require_client()
        payload = self._payload(messages, model, temperature, max_tokens, json_mode)

        started = time.perf_counter()
        try:
            response = await client.chat.completions.create(**payload)
        except Exception as exc:  # noqa: BLE001 —— 统一归一化
            raise self._translate(exc) from exc

        latency_ms = int((time.perf_counter() - started) * 1000)
        choice = response.choices[0] if response.choices else None
        message = choice.message if choice else None

        return ChatResult(
            id=response.id or f"chatcmpl-{uuid.uuid4().hex[:12]}",
            model=response.model or model,
            content=(message.content if message else "") or "",
            reasoning_content=getattr(message, "reasoning_content", None) if message else None,
            usage=self._usage_of(response.usage),
            latency_ms=latency_ms,
            mode=self._mode,
            finish_reason=choice.finish_reason if choice else None,
        )

    async def stream(
        self,
        messages: Sequence[Message],
        *,
        model: str | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
        json_mode: bool = False,
    ) -> AsyncIterator[StreamChunk]:
        """逐块返回，供 SSE 转发。"""
        model = model or self.default_model

        if self._mode == "mock":
            async for chunk in self._mock_stream(messages, model):
                yield chunk
            return

        client = self._require_client()
        payload = self._payload(messages, model, temperature, max_tokens, json_mode)
        payload["stream"] = True
        payload["stream_options"] = {"include_usage": True}

        try:
            stream = await client.chat.completions.create(**payload)
            async for chunk in stream:
                usage = self._usage_of(chunk.usage) if chunk.usage else None
                if not chunk.choices:
                    if usage:
                        yield StreamChunk(usage=usage)
                    continue
                choice = chunk.choices[0]
                delta = choice.delta
                yield StreamChunk(
                    content=delta.content or "",
                    reasoning_content=getattr(delta, "reasoning_content", "") or "",
                    finish_reason=choice.finish_reason,
                    usage=usage,
                )
        except Exception as exc:  # noqa: BLE001
            raise self._translate(exc) from exc

    async def ping(self) -> ChatResult:
        """连通性探针：最小 token 的真实调用，用于验证 Key / 网络 / 模型。"""
        return await self.chat(
            [
                {"role": "system", "content": "You are a connectivity probe. Reply with exactly one word: pong"},
                {"role": "user", "content": "ping"},
            ],
            temperature=0.0,
            max_tokens=8,
        )

    # ---------------- 内部 ----------------
    def _require_client(self) -> AsyncOpenAI:
        if self._client is None:
            raise LLMError(
                "未配置 DEEPSEEK_API_KEY，请在 backend/.env 中填写后重启服务",
                status_code=503,
                code="llm_not_configured",
            )
        return self._client

    def _payload(
        self,
        messages: Sequence[Message],
        model: str,
        temperature: float | None,
        max_tokens: int | None,
        json_mode: bool,
    ) -> dict:
        payload: dict = {
            "model": model,
            "messages": [{"role": m["role"], "content": m["content"]} for m in messages],
            "stream": False,
        }
        # deepseek-reasoner 不接受 temperature 等采样参数
        if "reasoner" not in model:
            payload["temperature"] = (
                self._settings.llm_temperature if temperature is None else temperature
            )
        limit = max_tokens or self._settings.llm_max_tokens
        if limit:
            payload["max_tokens"] = limit
        if json_mode:
            payload["response_format"] = {"type": "json_object"}
        return payload

    @staticmethod
    def _usage_of(raw: object) -> Usage:
        if raw is None:
            return Usage()
        return Usage(
            prompt_tokens=getattr(raw, "prompt_tokens", 0) or 0,
            completion_tokens=getattr(raw, "completion_tokens", 0) or 0,
            total_tokens=getattr(raw, "total_tokens", 0) or 0,
        )

    @staticmethod
    def _translate(exc: Exception) -> LLMError:
        if isinstance(exc, AuthenticationError):
            return LLMError("DeepSeek 鉴权失败，请检查 DEEPSEEK_API_KEY 是否有效", status_code=502, code="llm_auth_failed")
        if isinstance(exc, RateLimitError):
            return LLMError("DeepSeek 触发限流，请稍后重试", status_code=429, code="llm_rate_limited")
        if isinstance(exc, APITimeoutError):
            return LLMError("DeepSeek 请求超时", status_code=504, code="llm_timeout")
        if isinstance(exc, APIConnectionError):
            return LLMError("无法连接 DeepSeek，请检查网络或 BASE_URL", status_code=502, code="llm_unreachable")
        if isinstance(exc, BadRequestError):
            return LLMError(f"DeepSeek 拒绝了请求参数：{exc}", status_code=400, code="llm_bad_request")
        if isinstance(exc, APIStatusError):
            return LLMError(f"DeepSeek 返回错误（HTTP {exc.status_code}）", status_code=502, code="llm_upstream_error")
        return LLMError(f"模型调用失败：{exc}", status_code=502, code="llm_error")

    # ---------------- mock ----------------
    @staticmethod
    def _mock_reply(messages: Sequence[Message]) -> str:
        last_user = next((m["content"] for m in reversed(messages) if m["role"] == "user"), "")
        if last_user.strip().lower().startswith("ping"):
            return "pong"
        return (
            "【MOCK 模式】这是本地模拟回复，未调用真实模型。\n\n"
            f"收到 {len(messages)} 条消息，最后一条用户输入：{last_user[:120]}"
        )

    async def _mock_chat(self, messages: Sequence[Message], model: str) -> ChatResult:
        await asyncio.sleep(0.15)
        text = self._mock_reply(messages)
        return ChatResult(
            id=f"mock-{uuid.uuid4().hex[:12]}",
            model=f"{model}(mock)",
            content=text,
            latency_ms=150,
            mode="mock",
            usage=Usage(prompt_tokens=12, completion_tokens=len(text), total_tokens=12 + len(text)),
            finish_reason="stop",
        )

    async def _mock_stream(self, messages: Sequence[Message], model: str) -> AsyncIterator[StreamChunk]:
        text = self._mock_reply(messages)
        for index in range(0, len(text), 4):
            await asyncio.sleep(0.02)
            yield StreamChunk(content=text[index : index + 4])
        yield StreamChunk(
            finish_reason="stop",
            usage=Usage(prompt_tokens=12, completion_tokens=len(text), total_tokens=12 + len(text)),
        )
