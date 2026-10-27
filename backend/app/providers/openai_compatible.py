import asyncio
import json
import os
from collections.abc import AsyncIterator
from time import perf_counter, time
from typing import Any, Literal, cast
from urllib.parse import urlsplit

import httpx
from openai import APIConnectionError, APIStatusError, APITimeoutError, AsyncOpenAI, omit

from app.config import Settings
from app.contracts.dtos import (
    Message,
    ProviderItem,
    ProviderOptions,
    ProviderResult,
    ToolCall,
    Usage,
)
from app.contracts.errors import AppError
from app.providers.catalog import Catalog, ModelEntry, price
from app.providers.quota import ProviderQuota, retry_seconds

DEFAULT_PROVIDER_BASE_URLS: dict[str, str] = {
    "groq": "https://api.groq.com/openai/v1",
    "huggingface": "https://router.huggingface.co/hf-inference/v1",
    "openrouter": "https://openrouter.ai/api/v1",
}


class OpenAICompatibleProvider:
    """Generic OpenAI-compatible LLM Provider supporting custom base_url (Groq, HF, OpenRouter)."""

    def __init__(
        self,
        default_key: str,
        catalog: Catalog,
        settings: Settings | None = None,
        quota: ProviderQuota | None = None,
    ):
        self.default_key = default_key
        self.catalog = catalog
        self.settings = settings
        self.quota = quota
        self._free_metadata_lock = asyncio.Lock()
        self._free_metadata_checked = 0.0
        self._clients: dict[tuple[str, str], AsyncOpenAI] = {}
        # Pre-seed default client
        self.client = AsyncOpenAI(
            api_key=default_key or "no-key-specified",
            max_retries=0,
            timeout=90,
            http_client=httpx.AsyncClient(event_hooks={"response": [self._observe_response]}),
        )

    async def _observe_response(self, response: httpx.Response) -> None:
        if self.quota is None:
            return
        try:
            model = json.loads(response.request.content).get("model")
        except (ValueError, UnicodeError):
            return
        entry = next((e for e in self.catalog.models if e.model_id == model), None)
        if entry:
            await self.quota.observe(
                entry.model_copy(
                    update={"base_url": str(response.request.url.copy_with(path="/"))}
                ),
                response.headers,
                response.status_code,
            )

    def identity(self, config_id: str) -> str:
        entry = self.catalog.entry(config_id)
        url = entry.base_url
        if entry.api_key_env == "OPENAI_API_KEY":
            url = (
                os.environ.get("OPENAI_BASE_URL")
                or (self.settings.openai_base_url if self.settings else "")
                or url
            )
        return f"{(url or 'https://api.openai.com/v1').rstrip('/')}|{entry.api_key_env or 'default'}|{entry.model_id}"

    def available(self, config_id: str) -> bool:
        try:
            self._resolve_key_and_url(self.catalog.entry(config_id))
            return True
        except AppError:
            return False

    async def close(self) -> None:
        for client in {self.client, *self._clients.values()}:
            await client.close()

    async def _refresh_free_metadata(self, entry: ModelEntry, key: str) -> None:
        if (
            not self.quota
            or urlsplit(entry.base_url or "").hostname != "openrouter.ai"
            or not (entry.model_id.endswith(":free") or entry.model_id == "openrouter/free")
        ):
            return
        if self.settings and self.settings.app_env == "test":
            return
        async with self._free_metadata_lock:
            if time() - self._free_metadata_checked < 300 or not await self.quota.free_metadata_due(
                entry
            ):
                return
            self._free_metadata_checked = time()
            try:
                async with httpx.AsyncClient(timeout=5, follow_redirects=False) as client:
                    response = await client.get(
                        "https://openrouter.ai/api/v1/key",
                        headers={"Authorization": f"Bearer {key}"},
                    )
                if response.status_code == 200:
                    data = response.json().get("data", {})
                    await self.quota.sync_free_metadata(entry, data)
            except (httpx.HTTPError, ValueError):
                # Keep conservative configured limits; metadata failure never
                # authorizes additional inference or increases spending limits.
                pass

    def _resolve_key_and_url(self, entry: ModelEntry) -> tuple[str, str | None]:
        base_url = entry.base_url
        host = urlsplit(base_url or "").hostname
        credential_env = entry.api_key_env or {
            "api.openai.com": "OPENAI_API_KEY",
            "api.groq.com": "GROQ_API_KEY",
            "openrouter.ai": "OPENROUTER_API_KEY",
            "router.huggingface.co": "HUGGINGFACE_API_KEY",
        }.get(host or "")
        key = self.default_key if credential_env is None else ""
        if credential_env:
            key = os.environ.get(credential_env, "")
            if not key and self.settings:
                field = {
                    "OPENAI_API_KEY": self.settings.openai_api_key,
                    "GROQ_API_KEY": self.settings.groq_api_key,
                    "OPENROUTER_API_KEY": self.settings.openrouter_api_key,
                    "HUGGINGFACE_API_KEY": self.settings.huggingface_api_key,
                }.get(credential_env)
                key = field.get_secret_value() if field else ""
            if not key and not self.settings and not entry.api_key_env:
                key = self.default_key
        if not key:
            raise AppError(
                "PROVIDER_CONFIGURATION_ERROR",
                503,
                "Provider credential is not configured",
                dispatch_state="not_dispatched",
            )
        if credential_env == "OPENAI_API_KEY":
            base_url = (
                os.environ.get("OPENAI_BASE_URL")
                or (self.settings.openai_base_url if self.settings else "")
                or base_url
            )
        return key, base_url

    def _get_client(self, base_url: str | None, api_key: str) -> AsyncOpenAI:
        if (base_url is None or base_url == "") and (api_key == self.default_key):
            if hasattr(self, "client"):
                return self.client
        cache_key = (base_url or "", api_key)
        if cache_key not in self._clients:
            self._clients[cache_key] = AsyncOpenAI(
                api_key=api_key or "no-key-specified",
                base_url=base_url,
                max_retries=0,
                timeout=90,
                http_client=httpx.AsyncClient(event_hooks={"response": [self._observe_response]}),
            )
        return self._clients[cache_key]

    def get_client(self, entry: ModelEntry | None = None) -> AsyncOpenAI:
        if entry is None:
            return self.client
        key, base_url = self._resolve_key_and_url(entry)
        return self._get_client(base_url, key)

    @staticmethod
    def _provider_status_error(
        status_code: int, message: str, retry_after: str | None = None
    ) -> AppError:
        """Keep provider failures distinguishable for routing and cooldowns."""
        if status_code in (401, 403):
            code = "PROVIDER_CONFIGURATION_ERROR"
        elif status_code == 404:
            code = "MODEL_NOT_FOUND"
        elif status_code == 429:
            code = "RATE_LIMITED"
        else:
            code = "DEPENDENCY_UNAVAILABLE"

        # Only expose provider statuses that the API contract understands.
        public_status = 429 if status_code == 429 else 503
        return AppError(
            code,
            public_status,
            "Provider request failed",
            upstream_status=status_code,
            retry_after_seconds=retry_seconds(retry_after),
            dispatch_state="rejected"
            if 400 <= status_code < 500 and status_code != 408
            else "unknown",
        )

    async def generate(
        self, messages: tuple[Message, ...], opts: ProviderOptions
    ) -> ProviderResult:
        entry = self.catalog.entry(opts.config_id)
        if entry.kind != "generation" or opts.model_id != entry.model_id:
            raise AppError("NO_COMPATIBLE_MODEL", 422, "Model/configuration mismatch")
        if opts.tools and not entry.function_calling:
            raise AppError("NO_COMPATIBLE_MODEL", 422, "Model does not support tools")

        parameters = {
            key: value
            for key, value in (("temperature", opts.temperature), ("top_p", opts.top_p))
            if value is not None
        }
        if any(key not in entry.supported_parameters for key in parameters):
            raise AppError("VALIDATION_ERROR", 422, "Unsupported generation parameter")

        key, base_url = self._resolve_key_and_url(entry)
        entry = entry.model_copy(update={"base_url": base_url})
        await self._refresh_free_metadata(entry, key)
        ticket = (
            await self.quota.acquire(
                entry, self._input_bound(messages, opts) + entry.max_output_tokens
            )
            if self.quota
            else None
        )
        client = self._get_client(base_url, key)
        started = perf_counter()

        if entry.endpoint == "chat_completions":
            result = await self._generate_chat_completions(client, entry, messages, opts, started)
        else:
            result = await self._generate_responses(client, entry, messages, opts, started)
        if self.quota and ticket:
            usage = result.usage
            await self.quota.reconcile(
                entry,
                ticket,
                usage.input_tokens + usage.output_tokens
                if usage.input_tokens is not None and usage.output_tokens is not None
                else None,
            )
        return result

    @staticmethod
    def _input_bound(messages: tuple[Message, ...], opts: ProviderOptions) -> int:
        return (
            sum(len(m.content.encode("utf-8")) + 64 for m in messages)
            + 128
            + sum(len(t.model_dump_json().encode("utf-8")) + 64 for t in opts.tools)
            + sum(len(i.payload_json.encode("utf-8")) + 64 for i in opts.continuation_items)
        )

    async def _generate_responses(
        self,
        client: AsyncOpenAI,
        entry: ModelEntry,
        messages: tuple[Message, ...],
        opts: ProviderOptions,
        started: float,
    ) -> ProviderResult:
        try:
            result = await client.responses.create(
                model=entry.model_id,
                input=cast(
                    Any,
                    [{"role": m.role, "content": m.content} for m in messages]
                    + [json.loads(i.payload_json) for i in opts.continuation_items],
                ),
                max_output_tokens=entry.max_output_tokens,
                store=False,
                truncation="disabled",
                temperature=opts.temperature if opts.temperature is not None else omit,
                top_p=opts.top_p if opts.top_p is not None else omit,
                reasoning=cast(Any, {"effort": entry.reasoning_effort})
                if entry.reasoning_effort
                else omit,
                tools=cast(
                    Any,
                    [
                        {
                            "type": "function",
                            "name": t.name,
                            "description": t.description,
                            "parameters": json.loads(t.parameters_json),
                            "strict": True,
                        }
                        for t in opts.tools
                    ],
                )
                if opts.tools
                else omit,
                parallel_tool_calls=False if opts.tools else omit,
                include=["reasoning.encrypted_content"] if opts.tools else omit,
                extra_headers=self._request_headers(entry, opts.call_id),
                extra_body=self._provider_preferences(entry),
            )
        except APITimeoutError as exc:
            raise AppError("PROVIDER_TIMEOUT", 504, "Provider timeout; billing unresolved") from exc
        except APIConnectionError as exc:
            raise AppError(
                "DEPENDENCY_UNAVAILABLE", 503, "Provider connection failed; billing unresolved"
            ) from exc
        except APIStatusError as exc:
            raise self._provider_status_error(
                exc.status_code, exc.message, exc.response.headers.get("retry-after")
            ) from exc

        native = result.usage.model_dump() if result.usage else {}
        inputs = native.get("input_tokens_details") or {}
        outputs = native.get("output_tokens_details") or {}
        usage = Usage(
            scope="call",
            usage_source="provider",
            input_tokens=native.get("input_tokens"),
            output_tokens=native.get("output_tokens"),
            # Providers omit cache details when no cached tokens were used.
            # Treat an omitted detail block as zero so ordinary live calls get
            # a deterministic price instead of an unnecessary `unknown`.
            cached_input_tokens=inputs.get("cached_tokens", 0),
            reasoning_tokens=outputs.get("reasoning_tokens"),
        )
        text = result.output_text if result.status == "completed" else ""
        items = tuple(
            ProviderItem(type=item.type, payload_json=item.model_dump_json())
            for item in getattr(result, "output", ())
        )
        tool_calls = tuple(
            ToolCall(call_id=item.call_id, name=item.name, arguments=item.arguments)
            for item in getattr(result, "output", ())
            if item.type == "function_call"
        )
        return ProviderResult(
            text=text,
            execution_source="live",
            provider_response_id=result.id,
            native_usage_json=json.dumps(native),
            usage=usage,
            cost=price(
                entry,
                usage,
                self.catalog.version,
                inputs.get("cache_write_tokens")
                if entry.cache_write_per_million is not None
                or inputs.get("cache_write_tokens") is not None
                else 0,
            ),
            duration_ms=(perf_counter() - started) * 1000,
            status="incomplete"
            if result.status != "completed"
            else "tool_calls"
            if tool_calls
            else "completed",
            tool_calls=tool_calls,
            output_items=items,
        )

    async def _generate_chat_completions(
        self,
        client: AsyncOpenAI,
        entry: ModelEntry,
        messages: tuple[Message, ...],
        opts: ProviderOptions,
        started: float,
    ) -> ProviderResult:
        chat_messages: list[dict[str, Any]] = [
            {"role": m.role, "content": m.content} for m in messages
        ]
        for item in opts.continuation_items:
            try:
                payload = json.loads(item.payload_json)
                if payload.get("type") == "function_call_output":
                    chat_messages.append(
                        {
                            "role": "tool",
                            "tool_call_id": payload.get("call_id"),
                            "content": payload.get("output", ""),
                        }
                    )
            except Exception:
                pass

        tools_arg = omit
        if opts.tools:
            tools_arg = cast(
                Any,
                [
                    {
                        "type": "function",
                        "function": {
                            "name": t.name,
                            "description": t.description,
                            "parameters": json.loads(t.parameters_json),
                        },
                    }
                    for t in opts.tools
                ],
            )

        try:
            result = await client.chat.completions.create(
                model=entry.model_id,
                messages=cast(Any, chat_messages),
                **self._chat_generation_parameters(entry),
                temperature=opts.temperature if opts.temperature is not None else omit,
                top_p=opts.top_p if opts.top_p is not None else omit,
                tools=tools_arg,
                extra_headers=self._request_headers(entry, opts.call_id),
                extra_body=self._provider_preferences(entry),
            )
        except APITimeoutError as exc:
            raise AppError("PROVIDER_TIMEOUT", 504, "Provider timeout; billing unresolved") from exc
        except APIConnectionError as exc:
            raise AppError(
                "DEPENDENCY_UNAVAILABLE", 503, "Provider connection failed; billing unresolved"
            ) from exc
        except APIStatusError as exc:
            raise self._provider_status_error(
                exc.status_code, exc.message, exc.response.headers.get("retry-after")
            ) from exc

        choice = result.choices[0] if result.choices else None
        text = (choice.message.content or "") if choice and choice.message else ""
        if not text and choice and choice.message:
            reasoning = getattr(choice.message, "reasoning", None)
            if reasoning:
                text = str(reasoning)
        tool_calls_list: list[ToolCall] = []
        output_items: list[ProviderItem] = []

        if choice and choice.message and choice.message.tool_calls:
            for tc in choice.message.tool_calls:
                call_id = tc.id or "call_unknown"
                if tc.type != "function":
                    continue
                fn_name = tc.function.name
                fn_args = tc.function.arguments
                tool_calls_list.append(ToolCall(call_id=call_id, name=fn_name, arguments=fn_args))
                output_items.append(
                    ProviderItem(
                        type="function_call",
                        payload_json=json.dumps(
                            {"call_id": call_id, "name": fn_name, "arguments": fn_args}
                        ),
                    )
                )

        native = result.usage.model_dump() if result.usage else {}
        usage = Usage(
            scope="call",
            usage_source="provider",
            input_tokens=native.get("prompt_tokens"),
            output_tokens=native.get("completion_tokens"),
            # Chat-completions providers commonly omit prompt cache details
            # when the value is zero.
            cached_input_tokens=(native.get("prompt_tokens_details") or {}).get("cached_tokens", 0),
            reasoning_tokens=(native.get("completion_tokens_details") or {}).get(
                "reasoning_tokens"
            ),
        )
        finish_reason = choice.finish_reason if choice else "stop"
        status: Literal["incomplete", "tool_calls", "completed"] = (
            "incomplete"
            if finish_reason == "length"
            else ("tool_calls" if tool_calls_list else "completed")
        )

        return ProviderResult(
            text=text,
            execution_source="live",
            provider_response_id=result.id,
            native_usage_json=json.dumps(native),
            usage=usage,
            cost=price(entry, usage, self.catalog.version, 0),
            duration_ms=(perf_counter() - started) * 1000,
            status=status,
            tool_calls=tuple(tool_calls_list),
            output_items=tuple(output_items),
        )

    @staticmethod
    def _provider_preferences(entry: ModelEntry) -> dict[str, Any]:
        if urlsplit(entry.base_url or "").hostname != "openrouter.ai":
            return {}
        # OpenRouter's listed model price may be a floor across endpoints.
        # Refuse more expensive endpoints rather than exceed the ledger profile.
        return {
            "provider": {
                "require_parameters": True,
                "max_price": {
                    "prompt": float(entry.input_per_million),
                    "completion": float(entry.output_per_million),
                    "request": 0,
                },
            }
        }

    @staticmethod
    def _request_headers(entry: ModelEntry, call_id: str) -> dict[str, str]:
        # Correlate a lost native request with its durable local call record.
        # This is diagnostic metadata, not an idempotency/retry guarantee.
        if urlsplit(entry.base_url or "https://api.openai.com/v1").hostname != "api.openai.com":
            return {}
        import hashlib

        value = (
            call_id
            if call_id.isascii()
            and 0 < len(call_id) <= 512
            and all(32 <= ord(c) < 127 for c in call_id)
            else hashlib.sha256(call_id.encode()).hexdigest()
        )
        return {"X-Client-Request-Id": value}

    @staticmethod
    def _chat_generation_parameters(entry: ModelEntry) -> dict[str, Any]:
        # Native OpenAI reasoning models require the current completion limit.
        # Compatible endpoints can retain their documented max_tokens contract.
        native_openai = (
            urlsplit(entry.base_url or "https://api.openai.com/v1").hostname == "api.openai.com"
        )
        parameters: dict[str, Any] = {
            "max_completion_tokens" if native_openai else "max_tokens": entry.max_output_tokens
        }
        if entry.reasoning_effort is not None:
            parameters["reasoning_effort"] = entry.reasoning_effort
        return parameters

    async def stream(
        self, messages: tuple[Message, ...], opts: ProviderOptions
    ) -> AsyncIterator[str]:
        # The metered orchestration path uses generate so final usage is never
        # lost. Direct streaming still reserves quota and retains unknown usage.
        entry = self.catalog.entry(opts.config_id)
        if entry.kind != "generation" or opts.model_id != entry.model_id:
            raise AppError("NO_COMPATIBLE_MODEL", 422, "Model/configuration mismatch")

        key, base_url = self._resolve_key_and_url(entry)
        client = self._get_client(base_url, key)

        if entry.endpoint == "chat_completions":
            if self.quota:
                await self.quota.acquire(
                    entry.model_copy(update={"base_url": base_url}),
                    self._input_bound(messages, opts) + entry.max_output_tokens,
                )
            chat_messages: list[dict[str, Any]] = [
                {"role": m.role, "content": m.content} for m in messages
            ]
            for item in opts.continuation_items:
                try:
                    payload = json.loads(item.payload_json)
                    if payload.get("type") == "function_call_output":
                        chat_messages.append(
                            {
                                "role": "tool",
                                "tool_call_id": payload.get("call_id"),
                                "content": payload.get("output", ""),
                            }
                        )
                except Exception:
                    pass

            reasoning_chunks: list[str] = []
            has_content = False
            try:
                stream_resp = await client.chat.completions.create(
                    model=entry.model_id,
                    messages=cast(Any, chat_messages),
                    **self._chat_generation_parameters(
                        entry.model_copy(update={"base_url": base_url})
                    ),
                    temperature=opts.temperature if opts.temperature is not None else omit,
                    top_p=opts.top_p if opts.top_p is not None else omit,
                    stream=True,
                    extra_headers=self._request_headers(
                        entry.model_copy(update={"base_url": base_url}), opts.call_id
                    ),
                    extra_body=self._provider_preferences(
                        entry.model_copy(update={"base_url": base_url})
                    ),
                )
                async for chunk in stream_resp:
                    if chunk.choices and chunk.choices[0].delta:
                        delta = chunk.choices[0].delta
                        if delta.content:
                            has_content = True
                            yield delta.content
                        elif getattr(delta, "reasoning", None):
                            reasoning_chunks.append(str(getattr(delta, "reasoning")))  # noqa: B009
                if not has_content and reasoning_chunks:
                    for r in reasoning_chunks:
                        yield r
            except APITimeoutError as exc:
                raise AppError("PROVIDER_TIMEOUT", 504, "Provider timeout") from exc
            except APIConnectionError as exc:
                raise AppError("DEPENDENCY_UNAVAILABLE", 503, "Provider connection failed") from exc
            except APIStatusError as exc:
                raise self._provider_status_error(
                    exc.status_code, exc.message, exc.response.headers.get("retry-after")
                ) from exc
        else:
            # Fallback to non-streaming generation if responses endpoint does not support streaming
            result = await self.generate(messages, opts)
            yield result.text
