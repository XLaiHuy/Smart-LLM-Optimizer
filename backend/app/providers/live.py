import json
from time import perf_counter
from typing import Any, cast

from openai import APIConnectionError, APIStatusError, APITimeoutError, AsyncOpenAI, omit

from app.contracts.dtos import (
    Message,
    ProviderItem,
    ProviderOptions,
    ProviderResult,
    ToolCall,
    Usage,
)
from app.contracts.errors import AppError
from app.providers.catalog import Catalog, price


class OpenAIProvider:
    def __init__(self, key: str, catalog: Catalog):
        self.client = AsyncOpenAI(api_key=key, max_retries=0, timeout=90)
        self.catalog = catalog

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
        started = perf_counter()
        try:
            result = await self.client.responses.create(
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
                "Provider rejected request",
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
        if result.status != "completed":
            # Return usage for settlement even when output is truncated; validator rejects later.
            text = ""
        else:
            text = result.output_text
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
