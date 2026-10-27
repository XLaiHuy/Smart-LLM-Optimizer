const names: Record<string, string> = {
  "gpt-6-luna": "GPT-6 Luna",
  "gpt-5.6-terra": "GPT-5.6 Terra",
  "gpt-6.1-sol": "GPT-6.1 Sol",
  "openai/gpt-oss-120b": "GPT OSS 120B",
  "openai/gpt-oss-20b": "GPT OSS 20B",
  "qwen/qwen3.8-27b": "Qwen 3.8 27B",
  "llama-3.3-70b-versatile": "Llama 3.3 70B",
  "llama-3.1-8b-instant": "Llama 3.1 8B",
};

/** Trace model identity always takes precedence over configuration aliases. */
export function getCleanModelName(configId: string, modelId?: string): string {
  if (modelId) return names[modelId] || modelId;
  return legacyModelName(configId);
}

function legacyModelName(configId: string, modelId?: string): string {
  if (!configId) return modelId || "";
  const map: Record<string, string> = {
    "groq-llama-3.3-70b-versatile": "Llama 3.3 70B (Groq)",
    "groq-qwen-2.5-coder-32b": "Qwen 2.5 Coder 32B (Groq)",
    "groq-llama-3.1-8b-instant": "Llama 3.1 8B (Groq)",
    "groq-gpt-oss-120b": "GPT OSS 120B (Groq)",
    "groq-qwen-3.8-27b": "Qwen 3.8 27B (Groq)",
    "groq-gpt-oss-20b": "GPT OSS 20B (Groq)",
    "openai/gpt-oss-120b": "GPT OSS 120B (Groq)",
    "qwen/qwen3.8-27b": "Qwen 3.8 27B (Groq)",
    "openai/gpt-oss-20b": "GPT OSS 20B (Groq)",
    "openrouter-gemini-2.0-flash-exp-free": "Gemini 2.0 Flash (Free)",
    "openrouter-deepseek-r1-free": "DeepSeek R1 (Free)",
    "openrouter-meta-llama-3.3-70b-instruct-free": "Llama 3.3 70B (Free)",
    "openrouter-llama-3.3-70b-instruct-free": "Llama 3.3 70B (Free)",
    "meta-llama/llama-3.3-70b-instruct:free": "Llama 3.3 70B (Free)",
    "openrouter-qwen-2.5-coder-32b-instruct-free": "Qwen 2.5 Coder 32B (Free)",
    "qwen/qwen-2.5-coder-32b-instruct:free": "Qwen 2.5 Coder 32B (Free)",
    "openrouter/free": "OpenRouter (Free Tier)",
    "openrouter-free-v1": "OpenRouter (Free Tier)",
    "openrouter-lfm-2.5-2.6b-free": "LFM 2.5 2.6B (OpenRouter Free)",
    "openrouter-north-mini-code-free": "North Mini Code (OpenRouter Free)",
    "openrouter-nemotron-3-nano-reasoning-free":
      "Nemotron 3 Nano Reasoning (OpenRouter Free)",
    "openai-gpt-6-luna": "GPT-6 Luna (OpenAI)",
    "openai-gpt-5.6-terra": "GPT-5.6 Terra (OpenAI)",
    "openai-gpt-6.1-sol": "GPT-6.1 Sol (OpenAI)",
    "openai-gpt-6-astra": "GPT-6 Astra (OpenAI)",
    "mock-baseline": "Mock Baseline (Default)",
    "mock-coder-32b": "Mock Coding 32B (Demo)",
    "mock-reasoning-70b": "Mock Reasoning 70B (Demo)",
    "mock-small": "Mock Fast (Small)",
    "mock-quality": "Mock Frontier (Quality)",
    "gpt-6-luna": "GPT-6 Luna (OpenAI)",
    "gpt-5.6-terra": "GPT-5.6 Terra (OpenAI)",
    "gpt-6.1-sol": "GPT-6.1 Sol (OpenAI)",
  };
  if (map[configId]) return map[configId];
  if (modelId && map[modelId]) return map[modelId];
  const lower = configId.toLowerCase();
  if (lower.includes("luna")) return "GPT-6 Luna (OpenAI)";
  if (lower.includes("terra")) return "GPT-5.6 Terra (OpenAI)";
  if (lower.includes("sol")) return "GPT-6.1 Sol (OpenAI)";
  if (lower.includes("120b")) return "GPT OSS 120B (Groq)";
  if (lower.includes("3.8-27b")) return "Qwen 3.8 27B (Groq)";
  if (lower.includes("20b")) return "GPT OSS 20B (Groq)";
  if (lower.includes("llama-3.3-70b") && lower.includes("groq"))
    return "Llama 3.3 70B (Groq)";
  if (lower.includes("llama-3.3-70b-versatile")) return "Llama 3.3 70B (Groq)";
  if (lower.includes("qwen-2.5-coder-32b")) return "Qwen 2.5 Coder 32B (Groq)";
  if (
    lower.includes("llama-3.1-8b-instant") ||
    (lower.includes("llama-3.1-8b") && lower.includes("groq"))
  )
    return "Llama 3.1 8B (Groq)";
  if (lower.includes("gemini-2.0-flash")) return "Gemini 2.0 Flash (Free)";
  if (lower.includes("deepseek-r1")) return "DeepSeek R1 (Free)";
  if (lower.includes("llama-3.3-70b")) return "Llama 3.3 70B (Free)";
  return modelId || configId;
}
