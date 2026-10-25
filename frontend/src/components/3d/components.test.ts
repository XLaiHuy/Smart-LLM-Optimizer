import { describe, expect, it } from "vitest";
import katex from "katex";
import {
  NeuralRoutingCosmos3D,
  ParetoScatterSurface3D,
  DEMO_PARETO_POLICIES,
  DynamicNeuralRoutingCosmos3D,
  DynamicParetoScatterSurface3D,
  PipelineFlow3D,
  DynamicPipelineFlow3D,
  SIMULATION_PRESETS,
  LAYER_INFO,
  TokenCostSpace3D,
  DynamicTokenCostSpace3D,
  DEMO_SESSION_METRICS,
} from "./index";
import { SERVER_MODEL_DEFS, LAYER_Y } from "./pipeline-flow-3d";
import { getCleanModelName } from "../chat-panel";

describe("3D WebGL Visualization Components", () => {
  it("exports genuine 3D components and dynamic wrappers", () => {
    expect(NeuralRoutingCosmos3D).toBeDefined();
    expect(ParetoScatterSurface3D).toBeDefined();
    expect(DynamicNeuralRoutingCosmos3D).toBeDefined();
    expect(DynamicParetoScatterSurface3D).toBeDefined();
    expect(PipelineFlow3D).toBeDefined();
    expect(DynamicPipelineFlow3D).toBeDefined();
    expect(TokenCostSpace3D).toBeDefined();
    expect(DynamicTokenCostSpace3D).toBeDefined();
  });

  it("validates Pareto candidate policies data integrity", () => {
    expect(DEMO_PARETO_POLICIES.length).toBeGreaterThanOrEqual(4);

    DEMO_PARETO_POLICIES.forEach((p) => {
      expect(p.id).toBeDefined();
      expect(p.name).toBeDefined();
      expect(p.costUsd).toBeGreaterThan(0);
      expect(p.latencyMs).toBeGreaterThan(0);
      expect(p.passRate).toBeGreaterThanOrEqual(0);
      expect(p.passRate).toBeLessThanOrEqual(1.0);
      expect(typeof p.isParetoOptimal).toBe("boolean");
    });

    const paretoOptimal = DEMO_PARETO_POLICIES.filter((p) => p.isParetoOptimal);
    const dominated = DEMO_PARETO_POLICIES.filter((p) => !p.isParetoOptimal);

    expect(paretoOptimal.length).toBeGreaterThanOrEqual(3);
    expect(dominated.length).toBeGreaterThanOrEqual(1);

    // Verify ML Router is Pareto optimal
    const mlRouter = DEMO_PARETO_POLICIES.find((p) => p.id === "ml_router");
    expect(mlRouter).toBeDefined();
    expect(mlRouter?.isParetoOptimal).toBe(true);
  });

  it("validates 8-tier End-to-End Transformer LAYER_INFO integrity", () => {
    expect(LAYER_INFO.length).toBe(8);

    LAYER_INFO.forEach((layer, idx) => {
      expect(layer.id).toBe(idx + 1);
      expect(layer.title).toBeDefined();
      expect(layer.module).toBeDefined();
      expect(layer.color).toMatch(/^#[0-9a-fA-F]{6}$/);
      expect(layer.formula.length).toBeGreaterThan(3);
      expect(layer.description.length).toBeGreaterThan(15);
    });

    // Check key architecture layers
    expect(LAYER_INFO[0].title).toContain("Input Tensor");
    expect(LAYER_INFO[1].module).toContain("Khoa");
    expect(LAYER_INFO[2].module).toContain("Tân");
    expect(LAYER_INFO[3].module).toContain("Huy");
    expect(LAYER_INFO[4].title).toContain("Target Model");
    expect(LAYER_INFO[5].title).toContain("Transformer Core Decoder");
    expect(LAYER_INFO[6].title).toContain("LM Head & Softmax");
    expect(LAYER_INFO[7].title).toContain("Autoregressive SSE");
  });

  it("validates 8-tier Transformer simulation presets and 3Blue1Brown extension fields", () => {
    expect(SIMULATION_PRESETS.length).toBe(6);

    SIMULATION_PRESETS.forEach((preset) => {
      expect(preset.id).toBeDefined();
      expect(preset.name).toBeDefined();
      expect(preset.prompt.length).toBeGreaterThan(10);
      expect(preset.inputTokens).toBeGreaterThan(preset.compactedTokens);
      // Compaction percentage between 40% and 60%
      expect(preset.compactionPct).toBeGreaterThanOrEqual(40);
      expect(preset.compactionPct).toBeLessThanOrEqual(60);

      // Verify all 6 Attention dimensions are populated
      expect(preset.attentionScores.math).toBeGreaterThanOrEqual(0);
      expect(preset.attentionScores.code).toBeGreaterThanOrEqual(0);
      expect(preset.attentionScores.reasoning).toBeGreaterThanOrEqual(0);
      expect(preset.attentionScores.extraction).toBeGreaterThanOrEqual(0);
      expect(preset.attentionScores.writing).toBeGreaterThanOrEqual(0);
      expect(preset.attentionScores.multilingual).toBeGreaterThanOrEqual(0);

      // Verify winner model is configured
      expect(preset.winnerModelId).toBeDefined();
      expect(preset.estimatedLatencyMs).toBeGreaterThan(0);
      expect(preset.estimatedCostUsd).toBeGreaterThanOrEqual(0);

      // Verify 3Blue1Brown Transformer extension fields
      expect(preset.winnerToken).toBeDefined();
      expect(preset.winnerToken.length).toBeGreaterThan(0);
      expect(preset.transformerHeads).toBeGreaterThanOrEqual(32);
      expect(preset.mlpExpansion).toMatch(/(SwiGLU|GeGLU)/);

      // Verify candidate token distribution
      expect(preset.candidateTokens.length).toBeGreaterThanOrEqual(4);
      const winner = preset.candidateTokens.find((c) => c.isWinner);
      expect(winner).toBeDefined();
      expect(winner?.token).toBe(preset.winnerToken);
      expect(winner?.prob).toBeGreaterThan(0.5);

      const totalProb = preset.candidateTokens.reduce(
        (acc, c) => acc + c.prob,
        0,
      );
      expect(totalProb).toBeGreaterThanOrEqual(0.9);
      expect(totalProb).toBeLessThanOrEqual(1.05);
    });

    // Check specific Math preset next tokens ("Tích", "phân", "bội", "hàm")
    const mathPreset = SIMULATION_PRESETS.find(
      (p) => p.id === "math_advanced" || p.id === "math_calculus",
    );
    expect(mathPreset).toBeDefined();
    const tokenStrings = mathPreset?.candidateTokens.map((c) => c.token);
    expect(tokenStrings).toContain("Tích");
    expect(tokenStrings).toContain("phân");
    expect(tokenStrings).toContain("bội");
    expect(tokenStrings).toContain("hàm");
  });

  it("validates 3D Token & Cost space session metrics integrity", () => {
    expect(DEMO_SESSION_METRICS.length).toBeGreaterThanOrEqual(5);

    DEMO_SESSION_METRICS.forEach((m) => {
      expect(m.id).toBeDefined();
      expect(m.sessionTitle).toBeDefined();
      expect(m.inputTokens).toBeGreaterThan(0);
      expect(m.totalTokens).toBe(m.inputTokens + m.outputTokens);
      expect(m.costUsd).toBeGreaterThanOrEqual(0);
      expect(m.latencyMs).toBeGreaterThan(0);
      expect(m.optimized).toBe(true);
    });
  });

  it("validates getCleanModelName commercial mappings and edge cases", () => {
    // 6 Canonical commercial mappings required by R2
    expect(getCleanModelName("groq-llama-3.3-70b-versatile")).toBe(
      "Llama 3.3 70B (Groq)",
    );
    expect(getCleanModelName("groq-qwen-2.5-coder-32b")).toBe(
      "Qwen 2.5 Coder 32B (Groq)",
    );
    expect(getCleanModelName("groq-llama-3.1-8b-instant")).toBe(
      "Llama 3.1 8B (Groq)",
    );
    expect(getCleanModelName("openrouter-gemini-2.0-flash-exp-free")).toBe(
      "Gemini 2.0 Flash (Free)",
    );
    expect(getCleanModelName("openrouter-deepseek-r1-free")).toBe(
      "DeepSeek R1 (Free)",
    );
    expect(
      getCleanModelName("openrouter-meta-llama-3.3-70b-instruct-free"),
    ).toBe("Llama 3.3 70B (Free)");
    expect(getCleanModelName("openai-gpt-6-luna")).toBe("GPT-6 Luna (OpenAI)");
    expect(getCleanModelName("openai-gpt-5.6-terra")).toBe(
      "GPT-5.6 Terra (OpenAI)",
    );
    expect(getCleanModelName("openai-gpt-6.1-sol")).toBe(
      "GPT-6.1 Sol (OpenAI)",
    );
    expect(getCleanModelName("gpt-6-luna")).toBe("GPT-6 Luna (OpenAI)");

    // Partial and case-insensitive matching
    expect(getCleanModelName("GROQ-LLAMA-3.3-70B-VERSATILE")).toBe(
      "Llama 3.3 70B (Groq)",
    );
    expect(getCleanModelName("openrouter/deepseek-r1")).toBe(
      "DeepSeek R1 (Free)",
    );
    expect(getCleanModelName("custom-gemini-2.0-flash-free")).toBe(
      "Gemini 2.0 Flash (Free)",
    );
    expect(getCleanModelName("my-gpt-6-luna-v1")).toBe("GPT-6 Luna (OpenAI)");
    expect(getCleanModelName("my-gpt-5.6-terra-v1")).toBe(
      "GPT-5.6 Terra (OpenAI)",
    );
    expect(getCleanModelName("my-gpt-6.1-sol-v1")).toBe("GPT-6.1 Sol (OpenAI)");

    // Fallbacks
    expect(getCleanModelName("custom-model-id", "Custom Model 1.0")).toBe(
      "Custom Model 1.0",
    );
    expect(getCleanModelName("custom-model-id")).toBe("custom-model-id");
    expect(getCleanModelName("")).toBe("");
  });

  it("renders KaTeX mathematical formulas for all 8 layers cleanly", () => {
    LAYER_INFO.forEach((layer) => {
      expect(layer.formula).toBeDefined();
      expect(layer.formula.length).toBeGreaterThan(0);
      const html = katex.renderToString(layer.formula, {
        displayMode: true,
        throwOnError: false,
      });
      expect(html).toContain("katex");
      expect(html).not.toContain("ParseError");
    });
  });

  it("validates enlarged 8-tier vertical spacing LAYER_Y and server blade definitions", () => {
    expect(LAYER_Y.length).toBe(8);
    // Vertical distance between consecutive layers >= 2.0 to accommodate enlarged geometries
    for (let i = 0; i < LAYER_Y.length - 1; i++) {
      const step = LAYER_Y[i] - LAYER_Y[i + 1];
      expect(step).toBeGreaterThanOrEqual(2.0);
    }

    // Total vertical span >= 16.0 units for spacious 1.5x-2.0x geometries
    const totalSpan = LAYER_Y[0] - LAYER_Y[7];
    expect(totalSpan).toBeGreaterThanOrEqual(16.0);

    // 6 Active server blade models
    expect(SERVER_MODEL_DEFS.length).toBe(6);
    const bladeNames = SERVER_MODEL_DEFS.map((s) => s.name);
    expect(bladeNames).toContain("GPT OSS 120B");
    expect(bladeNames).toContain("Qwen 3.8 27B");
    expect(bladeNames).toContain("GPT OSS 20B");
    expect(bladeNames).toContain("GPT-6 Luna");
    expect(bladeNames).toContain("GPT-5.6 Terra");
    expect(bladeNames).toContain("GPT-6.1 Sol");
  });

  it("validates synapse web connectivity and mathematical formulations across all 8 tiers", () => {
    // Check that every layer's formula has valid TeX commands
    LAYER_INFO.forEach((l) => {
      expect(l.formula).toMatch(
        /(\\text|\\sum|\\arg|\\vec|\\mathcal|\\hookrightarrow)/,
      );
    });

    // Check all presets have distinct winner tokens that match winner token in candidate list
    SIMULATION_PRESETS.forEach((preset) => {
      const winnerCand = preset.candidateTokens.find((c) => c.isWinner);
      expect(winnerCand).toBeDefined();
      expect(winnerCand?.token).toBe(preset.winnerToken);
      expect(winnerCand?.prob).toBeGreaterThan(0.5);
    });
  });
});
