"""Unified LLM API abstraction — open provider system.

Any endpoint that speaks the OpenAI chat-completions protocol is supported
via :class:`OpenAICompatibleProvider`.  Anthropic and Google retain their own
thin wrappers because those SDKs expose unique, non-OpenAI APIs.

Provider routing is driven by a ``model_config`` dict (sourced from the
experiment's ``plan.yaml``) rather than model-name prefixes, so arbitrary
third-party or local endpoints can be used without touching this file.

Typical ``model_config`` shapes
--------------------------------
Anthropic::

    {"provider": "anthropic", "name": "claude-opus-4-5", ...}

Google::

    {"provider": "google", "name": "gemini-2.0-flash", ...}

OpenAI-compatible (OpenAI, Together AI, Fireworks, Groq, Ollama, vLLM, …)::

    {
        "provider": "together",
        "name": "meta-llama/Llama-4-70b",
        "base_url": "https://api.together.xyz/v1",
        "api_key_env": "TOGETHER_API_KEY",   # omit or set to None for local
    }
"""

from __future__ import annotations

import asyncio
import logging
import os
import time
from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable

from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Shared types
# ---------------------------------------------------------------------------

Message = dict[str, Any]  # {"role": "user"|"assistant"|"system", "content": str | list}

CompletionParams = dict[str, Any]  # temperature, max_tokens, top_p, etc.


@dataclass
class CompletionResult:
    """Structured result returned by every provider.

    Attributes:
        text: The generated text content.
        input_tokens: Number of prompt tokens consumed.
        output_tokens: Number of completion tokens generated.
        model: The exact model identifier used by the provider.
        latency_ms: Wall-clock round-trip time in milliseconds.
    """

    text: str
    input_tokens: int
    output_tokens: int
    model: str
    latency_ms: float


# ---------------------------------------------------------------------------
# Provider Protocol
# ---------------------------------------------------------------------------


@runtime_checkable
class LLMProvider(Protocol):
    """Structural interface every provider must satisfy."""

    async def complete(
        self,
        *,
        prompt: str | dict[str, Any],
        model: str,
        temperature: float = 0.5,
        max_tokens: int = 512,
        top_p: float = 1.0,
        system: str | None = None,
        **kwargs: Any,
    ) -> CompletionResult:
        """Send a chat completion request and return a structured result.

        Args:
            prompt: Either a plain string (treated as the user message) or a
                dict with optional ``"system"``, ``"user"``, and ``"images"``
                keys.  ``"images"`` is a list of URLs or local file paths.
            model: Full model identifier to pass to the underlying API.
            temperature: Sampling temperature (0.0 – 2.0).
            max_tokens: Maximum tokens to generate.
            top_p: Nucleus-sampling probability mass.
            system: System prompt.  When *prompt* is a dict that already
                contains a ``"system"`` key, this argument is ignored.
            **kwargs: Extended parameters forwarded to the provider API.
                Supported keys (provider-dependent):
                - top_k (int): Anthropic, Google, Ollama
                - json_mode (bool): OpenAI, Groq (response_format: json_object)
                - frequency_penalty (float): OpenAI, Groq
                - presence_penalty (float): OpenAI, Groq
                - thinking (bool): Anthropic extended thinking
                - thinking_budget (int): Anthropic thinking token budget
                - seed (int): OpenAI, Groq
                - stop_sequences (list[str]): All providers

        Returns:
            A populated :class:`CompletionResult`.
        """
        ...


# ---------------------------------------------------------------------------
# Retry helper
# ---------------------------------------------------------------------------

_RETRYABLE_STATUS = {429, 500, 502, 503, 504}
_MAX_RETRIES = 4
_BASE_DELAY = 1.0  # seconds


async def _with_retry(coro_fn: Any, *args: Any, **kwargs: Any) -> Any:
    """Call an async callable with exponential back-off on transient errors.

    Args:
        coro_fn: An async callable to retry.
        *args: Positional arguments forwarded to ``coro_fn``.
        **kwargs: Keyword arguments forwarded to ``coro_fn``.

    Returns:
        The return value of ``coro_fn`` on a successful attempt.

    Raises:
        The last exception if all retries are exhausted.
    """
    last_exc: Exception | None = None
    for attempt in range(_MAX_RETRIES):
        try:
            return await coro_fn(*args, **kwargs)
        except Exception as exc:  # noqa: BLE001
            last_exc = exc
            # Surface non-retryable errors immediately.
            status = getattr(exc, "status_code", None) or getattr(exc, "status", None)
            if status is not None and status not in _RETRYABLE_STATUS:
                raise
            delay = _BASE_DELAY * (2**attempt)
            logger.warning(
                "Provider error on attempt %d/%d (%s). Retrying in %.1fs.",
                attempt + 1,
                _MAX_RETRIES,
                exc,
                delay,
            )
            await asyncio.sleep(delay)
    raise last_exc  # type: ignore[misc]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _split_system(messages: list[Message]) -> tuple[str | None, list[Message]]:
    """Separate a leading system message from the rest of the conversation.

    Args:
        messages: Full message list, potentially starting with a system turn.

    Returns:
        A ``(system_prompt, remaining_messages)`` tuple.  ``system_prompt``
        is ``None`` when no system message is present.
    """
    if messages and messages[0]["role"] == "system":
        return messages[0]["content"], messages[1:]
    return None, messages


def _build_messages(
    prompt: str | dict[str, Any],
    system: str | None,
) -> tuple[str | None, list[dict[str, Any]]]:
    """Normalise the *prompt* argument into a ``(system, [user_message])`` pair.

    When the prompt dict contains an ``"images"`` key the user message content
    is returned as a multi-modal array (OpenAI ``image_url`` format).  URL
    images are passed through unchanged; local file paths are base64-encoded.

    Args:
        prompt: Either a plain user-message string or a dict that may contain
            ``"system"``, ``"user"``, and/or ``"images"`` keys.
        system: Fallback system prompt used when *prompt* does not supply one.

    Returns:
        A ``(resolved_system, messages)`` tuple where *messages* is a list
        of role/content dicts ready to send to any chat API.
    """
    if isinstance(prompt, str):
        resolved_system = system
        user_text = prompt
        images: list[str] = []
    else:
        resolved_system = prompt.get("system") or system
        user_text = prompt.get("user", "")
        images = prompt.get("images", [])

    if images:
        import base64
        from pathlib import Path as _Path

        content: list[dict[str, Any]] = [{"type": "text", "text": user_text}]
        for img in images:
            if img.startswith(("http://", "https://")):
                content.append({"type": "image_url", "image_url": {"url": img}})
            else:
                img_path = _Path(img)
                if img_path.exists():
                    data = base64.b64encode(img_path.read_bytes()).decode()
                    ext = img_path.suffix.lower()
                    media_types = {
                        ".png": "image/png",
                        ".jpg": "image/jpeg",
                        ".jpeg": "image/jpeg",
                        ".gif": "image/gif",
                        ".webp": "image/webp",
                    }
                    media_type = media_types.get(ext, "image/png")
                    content.append({
                        "type": "image_url",
                        "image_url": {"url": f"data:{media_type};base64,{data}"},
                    })
                else:
                    logger.warning("Image path does not exist, skipping: %s", img)
        messages: list[dict[str, Any]] = [{"role": "user", "content": content}]
    else:
        messages = [{"role": "user", "content": user_text}]

    return resolved_system, messages


# ---------------------------------------------------------------------------
# Anthropic
# ---------------------------------------------------------------------------


class AnthropicProvider:
    """Anthropic Claude via the ``anthropic`` async SDK.

    Reads ``ANTHROPIC_API_KEY`` from the environment.
    """

    def __init__(self) -> None:
        from anthropic import AsyncAnthropic  # lazy import — keeps startup fast

        api_key = os.environ.get("ANTHROPIC_API_KEY")
        if not api_key:
            raise EnvironmentError("ANTHROPIC_API_KEY is not set.")
        self._client = AsyncAnthropic(api_key=api_key)

    async def complete(
        self,
        *,
        prompt: str | dict[str, Any],
        model: str,
        temperature: float = 0.5,
        max_tokens: int = 512,
        top_p: float = 1.0,
        system: str | None = None,
        **extra: Any,
    ) -> CompletionResult:
        resolved_system, chat_messages = _build_messages(prompt, system)

        # Convert OpenAI-style image_url blocks to Anthropic source blocks.
        for msg in chat_messages:
            if isinstance(msg.get("content"), list):
                new_content: list[dict[str, Any]] = []
                for block in msg["content"]:
                    if block.get("type") == "image_url":
                        url: str = block["image_url"]["url"]
                        if url.startswith("data:"):
                            header, b64_data = url.split(",", 1)
                            media_type = header.split(":")[1].split(";")[0]
                            new_content.append({
                                "type": "image",
                                "source": {
                                    "type": "base64",
                                    "media_type": media_type,
                                    "data": b64_data,
                                },
                            })
                        else:
                            new_content.append({
                                "type": "image",
                                "source": {"type": "url", "url": url},
                            })
                    else:
                        new_content.append(block)
                msg["content"] = new_content

        api_kwargs: dict[str, Any] = {
            "model": model,
            "max_tokens": max_tokens,
            "messages": chat_messages,
            "temperature": temperature,
            "top_p": top_p,
        }
        if resolved_system:
            api_kwargs["system"] = resolved_system
        # Anthropic extended params
        if extra.get("top_k") is not None:
            api_kwargs["top_k"] = extra["top_k"]
        if extra.get("stop_sequences"):
            api_kwargs["stop_sequences"] = extra["stop_sequences"]
        if extra.get("thinking"):
            api_kwargs["thinking"] = {"type": "enabled", "budget_tokens": extra.get("thinking_budget", 1024)}

        t0 = time.perf_counter()
        response = await _with_retry(self._client.messages.create, **api_kwargs)
        latency_ms = (time.perf_counter() - t0) * 1000

        text = response.content[0].text
        usage = response.usage
        return CompletionResult(
            text=text,
            input_tokens=usage.input_tokens,
            output_tokens=usage.output_tokens,
            model=response.model,
            latency_ms=latency_ms,
        )


# ---------------------------------------------------------------------------
# Google
# ---------------------------------------------------------------------------


class GoogleProvider:
    """Google Gemini via the ``google-genai`` SDK.

    Reads ``GOOGLE_API_KEY`` from the environment.
    """

    def __init__(self) -> None:
        import google.genai as genai  # lazy import

        api_key = os.environ.get("GOOGLE_API_KEY")
        if not api_key:
            raise EnvironmentError("GOOGLE_API_KEY is not set.")
        self._client = genai.Client(api_key=api_key)

    async def complete(
        self,
        *,
        prompt: str | dict[str, Any],
        model: str,
        temperature: float = 0.5,
        max_tokens: int = 512,
        top_p: float = 1.0,
        system: str | None = None,
        **extra: Any,
    ) -> CompletionResult:
        """Send a request to the Google Gemini GenerateContent API.

        Args:
            prompt: User message string or dict with optional ``"system"``,
                ``"user"``, and ``"images"`` keys.  Images are not yet
                supported for Google; a warning is logged and only the text
                content is forwarded.
            model: Gemini model identifier (e.g. ``"gemini-2.0-flash"``).
            temperature: Sampling temperature.
            max_tokens: Maximum tokens to generate (mapped to
                ``max_output_tokens``).
            top_p: Nucleus-sampling probability mass.
            system: System prompt / instruction.

        Returns:
            Populated :class:`CompletionResult`.
        """
        import google.genai.types as genai_types  # lazy import

        resolved_system, google_messages = _build_messages(prompt, system)

        generation_config = genai_types.GenerateContentConfig(
            temperature=temperature,
            max_output_tokens=max_tokens,
            top_p=top_p,
        )

        config_kwargs: dict[str, Any] = {"generation_config": generation_config}
        if resolved_system:
            config_kwargs["system_instruction"] = resolved_system

        # Google SDK does not use the OpenAI image_url format.  Extract plain
        # text from multi-modal content arrays and warn the caller.
        contents_list: list[genai_types.Content] = []
        for msg in google_messages:
            raw_content = msg["content"]
            if isinstance(raw_content, list):
                logger.warning(
                    "GoogleProvider does not yet support vision inputs; "
                    "image blocks will be dropped for this request."
                )
                text_parts = " ".join(
                    block.get("text", "")
                    for block in raw_content
                    if block.get("type") == "text"
                )
                parts = [genai_types.Part(text=text_parts)]
            else:
                parts = [genai_types.Part(text=raw_content)]
            contents_list.append(
                genai_types.Content(
                    role="user" if msg["role"] == "user" else "model",
                    parts=parts,
                )
            )

        contents = contents_list

        t0 = time.perf_counter()
        response = await _with_retry(
            self._client.aio.models.generate_content,
            model=model,
            contents=contents,
            **config_kwargs,
        )
        latency_ms = (time.perf_counter() - t0) * 1000

        text = response.text or ""
        usage = response.usage_metadata
        return CompletionResult(
            text=text,
            input_tokens=usage.prompt_token_count or 0,
            output_tokens=usage.candidates_token_count or 0,
            model=model,
            latency_ms=latency_ms,
        )


# ---------------------------------------------------------------------------
# OpenAI-compatible (OpenAI, Together AI, Fireworks, Groq, Ollama, vLLM, …)
# ---------------------------------------------------------------------------


class OpenAICompatibleProvider:
    """Any provider that implements the OpenAI chat-completions protocol.

    Uses the ``openai`` SDK pointed at a custom ``base_url``, which means it
    works out of the box with:

    * **OpenAI**      — ``https://api.openai.com/v1``
    * **Together AI** — ``https://api.together.xyz/v1``
    * **Fireworks**   — ``https://api.fireworks.ai/inference/v1``
    * **Groq**        — ``https://api.groq.com/openai/v1``
    * **Ollama**      — ``http://localhost:11434/v1``
    * **vLLM**        — ``http://localhost:8000/v1``
    * Any other OpenAI-compatible endpoint.

    Args:
        base_url: Full base URL of the OpenAI-compatible API endpoint.
        api_key_env: Name of the environment variable that holds the API key.
            Pass ``None`` (or an unset variable) for unauthenticated local
            endpoints such as Ollama or vLLM.
        default_model: Optional model name to fall back on when the caller
            does not supply one.
    """

    def __init__(
        self,
        base_url: str,
        api_key_env: str | None = None,
        default_model: str | None = None,
    ) -> None:
        from openai import AsyncOpenAI  # lazy import

        api_key: str | None = None
        if api_key_env:
            api_key = os.environ.get(api_key_env)
            if not api_key:
                logger.warning(
                    "Environment variable '%s' is not set — proceeding without "
                    "authentication.  This is fine for local endpoints.",
                    api_key_env,
                )

        # The openai SDK requires a non-empty api_key string even for local
        # servers that do not validate it.
        self._client = AsyncOpenAI(
            base_url=base_url,
            api_key=api_key or "no-key-required",
        )
        self._default_model = default_model

    async def complete(
        self,
        *,
        prompt: str | dict[str, Any],
        model: str,
        temperature: float = 0.5,
        max_tokens: int = 512,
        top_p: float = 1.0,
        system: str | None = None,
        **extra: Any,
    ) -> CompletionResult:
        resolved_system, user_messages = _build_messages(prompt, system)

        messages: list[dict[str, Any]] = []
        if resolved_system:
            messages.append({"role": "system", "content": resolved_system})
        messages.extend(user_messages)

        effective_model = model or self._default_model or ""

        api_kwargs: dict[str, Any] = {
            "model": effective_model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "top_p": top_p,
        }
        # OpenAI-compatible extended params
        if extra.get("json_mode"):
            api_kwargs["response_format"] = {"type": "json_object"}
        if extra.get("frequency_penalty") is not None:
            api_kwargs["frequency_penalty"] = extra["frequency_penalty"]
        if extra.get("presence_penalty") is not None:
            api_kwargs["presence_penalty"] = extra["presence_penalty"]
        if extra.get("seed") is not None:
            api_kwargs["seed"] = extra["seed"]
        if extra.get("stop_sequences"):
            api_kwargs["stop"] = extra["stop_sequences"]

        t0 = time.perf_counter()
        response = await _with_retry(
            self._client.chat.completions.create,
            **api_kwargs,
        )
        latency_ms = (time.perf_counter() - t0) * 1000

        choice = response.choices[0]
        usage = response.usage
        return CompletionResult(
            text=choice.message.content or "",
            input_tokens=usage.prompt_tokens if usage else 0,
            output_tokens=usage.completion_tokens if usage else 0,
            model=response.model,
            latency_ms=latency_ms,
        )


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------

# Cache keyed by (provider_type, base_url) to reuse HTTP connections.
_provider_cache: dict[tuple[str, str], LLMProvider] = {}


def get_provider(model_config: dict[str, Any]) -> LLMProvider:
    """Return the appropriate :class:`LLMProvider` for the given model config.

    Routing is determined by the ``"provider"`` field of *model_config*:

    * ``"anthropic"``  → :class:`AnthropicProvider`
    * ``"google"``     → :class:`GoogleProvider`
    * anything else    → :class:`OpenAICompatibleProvider` constructed from
      ``model_config["base_url"]`` and ``model_config.get("api_key_env")``.

    Provider instances are cached by ``(provider_type, base_url)`` so that the
    same endpoint reuses its underlying HTTP connection pool across cells.

    Args:
        model_config: Dict containing at minimum a ``"provider"`` key.  For
            OpenAI-compatible providers it must also contain ``"base_url"``.
            Optional keys: ``"api_key_env"``, ``"name"`` (default model).

    Returns:
        A ready-to-use :class:`LLMProvider` instance.

    Raises:
        ValueError: If ``"base_url"`` is absent for a non-Anthropic /
            non-Google provider.
    """
    provider_type: str = model_config["provider"]

    if provider_type == "anthropic":
        cache_key = ("anthropic", "")
        if cache_key not in _provider_cache:
            _provider_cache[cache_key] = AnthropicProvider()
        return _provider_cache[cache_key]

    if provider_type == "google":
        cache_key = ("google", "")
        if cache_key not in _provider_cache:
            _provider_cache[cache_key] = GoogleProvider()
        return _provider_cache[cache_key]

    # Everything else is treated as an OpenAI-compatible endpoint.
    base_url: str | None = model_config.get("base_url")
    if not base_url:
        raise ValueError(
            f"model_config for provider '{provider_type}' must include 'base_url'. "
            f"Got: {model_config!r}"
        )

    api_key_env: str | None = model_config.get("api_key_env")
    default_model: str | None = model_config.get("name")

    cache_key = (provider_type, base_url)
    if cache_key not in _provider_cache:
        _provider_cache[cache_key] = OpenAICompatibleProvider(
            base_url=base_url,
            api_key_env=api_key_env,
            default_model=default_model,
        )
    return _provider_cache[cache_key]
