import json
from time import perf_counter

from openai import APIConnectionError, APIStatusError, APITimeoutError, AsyncOpenAI, omit

from app.contracts.dtos import Message, ProviderOptions, ProviderResult, Usage
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
                input=[{"role": m.role, "content": m.content} for m in messages],
                max_output_tokens=entry.max_output_tokens,
                store=False,
                truncation="disabled",
                temperature=opts.temperature if opts.temperature is not None else omit,
                top_p=opts.top_p if opts.top_p is not None else omit,
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
        )
