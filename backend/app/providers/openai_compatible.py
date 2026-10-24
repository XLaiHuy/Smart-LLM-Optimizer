import json
import os
from collections.abc import AsyncIterator
from time import perf_counter
from typing import Any, cast

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
    ):
        self.default_key = default_key
        self.catalog = catalog
        self.settings = settings
        self._clients: dict[tuple[str, str], AsyncOpenAI] = {}
        # Pre-seed default client
        self.client = AsyncOpenAI(
            api_key=default_key or "no-key-specified",
            max_retries=0,
            timeout=90,
        )

    def _resolve_key_and_url(self, entry: ModelEntry) -> tuple[str, str | None]:
        base_url = entry.base_url
        key = self.default_key

        if entry.api_key_env:
            env_val = os.environ.get(entry.api_key_env)
            if env_val:
                key = env_val
            elif self.settings:
                if entry.api_key_env == "GROQ_API_KEY" and self.settings.groq_api_key.get_secret_value():
                    key = self.settings.groq_api_key.get_secret_value()
                elif entry.api_key_env == "HUGGINGFACE_API_KEY" and self.settings.huggingface_api_key.get_secret_value():
                    key = self.settings.huggingface_api_key.get_secret_value()
                elif entry.api_key_env == "OPENROUTER_API_KEY" and self.settings.openrouter_api_key.get_secret_value():
                    key = self.settings.openrouter_api_key.get_secret_value()
                elif entry.api_key_env == "OPENAI_API_KEY" and self.settings.openai_api_key.get_secret_value():
                    key = self.settings.openai_api_key.get_secret_value()

        if entry.api_key_env == "OPENAI_API_KEY":
            custom_url = os.environ.get("OPENAI_BASE_URL") or (
                getattr(self.settings, "openai_base_url", "") if self.settings else ""
            )
            if custom_url:
                base_url = custom_url
            elif not key or key == "no-key-specified" or key == self.default_key:
                or_key = os.environ.get("OPENROUTER_API_KEY") or (
                    self.settings.openrouter_api_key.get_secret_value() if self.settings else ""
                )
                if or_key:
                    key = or_key
                    base_url = "https://openrouter.ai/api/v1"

        return key, base_url

    def _get_client(self, base_url: str | None, api_key: str) -> AsyncOpenAI:
        if (base_url is None or base_url == "") and (
            api_key == self.default_key or not api_key or getattr(self, "client", None) is not None
        ):
            if hasattr(self, "client"):
                return self.client
        cache_key = (base_url or "", api_key)
        if cache_key not in self._clients:
            self._clients[cache_key] = AsyncOpenAI(
                api_key=api_key or "no-key-specified",
                base_url=base_url,
                max_retries=0,
                timeout=90,
            )
        return self._clients[cache_key]

    def get_client(self, entry: ModelEntry | None = None) -> AsyncOpenAI:
        if entry is None:
            return self.client
        key, base_url = self._resolve_key_and_url(entry)
        return self._get_client(base_url, key)

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
        client = self._get_client(base_url, key)
        started = perf_counter()

        if entry.endpoint == "chat_completions":
            return await self._generate_chat_completions(client, entry, messages, opts, started)
        else:
            return await self._generate_responses(client, entry, messages, opts, started)

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
            )
        except APITimeoutError as exc:
            raise AppError("PROVIDER_TIMEOUT", 504, "Provider timeout; billing unresolved") from exc
        except APIConnectionError as exc:
            raise AppError(
                "DEPENDENCY_UNAVAILABLE", 503, "Provider connection failed; billing unresolved"
            ) from exc
        except APIStatusError as exc:
            raise AppError(
                "RATE_LIMITED" if exc.status_code == 429 else "DEPENDENCY_UNAVAILABLE",
                429 if exc.status_code == 429 else 503,
                f"Provider rejected request: {exc.message}",
            ) from exc

        native = result.usage.model_dump() if result.usage else {}
        inputs = native.get("input_tokens_details") or {}
        outputs = native.get("output_tokens_details") or {}
        usage = Usage(
            scope="call",
            usage_source="provider",
            input_tokens=native.get("input_tokens"),
            output_tokens=native.get("output_tokens"),
            cached_input_tokens=inputs.get("cached_tokens"),
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
                max_tokens=entry.max_output_tokens,
                temperature=opts.temperature if opts.temperature is not None else omit,
                top_p=opts.top_p if opts.top_p is not None else omit,
                tools=tools_arg,
            )
        except APITimeoutError as exc:
            raise AppError("PROVIDER_TIMEOUT", 504, "Provider timeout; billing unresolved") from exc
        except APIConnectionError as exc:
            raise AppError(
                "DEPENDENCY_UNAVAILABLE", 503, "Provider connection failed; billing unresolved"
            ) from exc
        except APIStatusError as exc:
            raise AppError(
                "RATE_LIMITED" if exc.status_code == 429 else "DEPENDENCY_UNAVAILABLE",
                429 if exc.status_code == 429 else 503,
                f"Provider rejected request: {exc.message}",
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
                fn_name = tc.function.name if tc.function else ""
                fn_args = tc.function.arguments if tc.function else "{}"
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
            cached_input_tokens=(native.get("prompt_tokens_details") or {}).get("cached_tokens"),
            reasoning_tokens=(native.get("completion_tokens_details") or {}).get("reasoning_tokens"),
        )
        finish_reason = choice.finish_reason if choice else "stop"
        status = "incomplete" if finish_reason == "length" else ("tool_calls" if tool_calls_list else "completed")

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

    async def stream(
        self, messages: tuple[Message, ...], opts: ProviderOptions
    ) -> AsyncIterator[str]:
        entry = self.catalog.entry(opts.config_id)
        if entry.kind != "generation" or opts.model_id != entry.model_id:
            raise AppError("NO_COMPATIBLE_MODEL", 422, "Model/configuration mismatch")

        key, base_url = self._resolve_key_and_url(entry)
        client = self._get_client(base_url, key)

        if entry.endpoint == "chat_completions":
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
                    max_tokens=entry.max_output_tokens,
                    temperature=opts.temperature if opts.temperature is not None else omit,
                    top_p=opts.top_p if opts.top_p is not None else omit,
                    stream=True,
                )
                async for chunk in stream_resp:
                    if chunk.choices and chunk.choices[0].delta:
                        delta = chunk.choices[0].delta
                        if delta.content:
                            has_content = True
                            yield delta.content
                        elif getattr(delta, "reasoning", None):
                            reasoning_chunks.append(str(delta.reasoning))
                if not has_content and reasoning_chunks:
                    for r in reasoning_chunks:
                        yield r
            except APITimeoutError as exc:
                raise AppError("PROVIDER_TIMEOUT", 504, "Provider timeout") from exc
            except APIConnectionError as exc:
                raise AppError("DEPENDENCY_UNAVAILABLE", 503, "Provider connection failed") from exc
            except APIStatusError as exc:
                raise AppError(
                    "RATE_LIMITED" if exc.status_code == 429 else "DEPENDENCY_UNAVAILABLE",
                    429 if exc.status_code == 429 else 503,
                    f"Provider rejected request: {exc.message}",
                ) from exc
        else:
            # Fallback to non-streaming generation if responses endpoint does not support streaming
            result = await self.generate(messages, opts)
            yield result.text
