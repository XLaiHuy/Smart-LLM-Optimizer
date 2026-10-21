import tiktoken
from llmlingua import PromptCompressor
class LLMLinguaCompressor:
    def __init__(self) -> None:
        self.encoding = tiktoken.get_encoding("cl100k_base")
        self.compressor = PromptCompressor(
            model_name=(
                "microsoft/"
                "llmlingua-2-bert-base-multilingual-cased-meetingbank"
            ),
            device_map="cpu",
            use_llmlingua2=True,
        )
    def compress(
        self,
        prompt: str,
        rate: float = 0.7,
    ) -> dict:
        original_tokens = len(self.encoding.encode(prompt))

        result = self.compressor.compress_prompt(
            prompt,
            rate=rate,
            force_tokens=["\n", "?"],
        )

        compressed = result["compressed_prompt"]
        compressed_tokens = len(self.encoding.encode(compressed))

        return {
            "original": prompt,
            "compressed": compressed,
            "original_tokens": original_tokens,
            "compressed_tokens": compressed_tokens,
            "savings": original_tokens - compressed_tokens,
            "ratio": compressed_tokens / original_tokens
            if original_tokens
            else 1.0,
        }