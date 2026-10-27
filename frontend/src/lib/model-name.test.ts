import { describe, expect, it } from "vitest";
import { getCleanModelName } from "./model-name";

describe("model identity", () => {
  it("uses the actual trace model over a repurposed config alias", () => {
    expect(
      getCleanModelName("groq-llama-3.3-70b-versatile", "openai/gpt-oss-120b"),
    ).toBe("GPT OSS 120B");
  });
  it("preserves unknown model identities and supports old traces", () => {
    expect(getCleanModelName("old-llama", "provider/new-model")).toBe(
      "provider/new-model",
    );
    expect(getCleanModelName("legacy-config")).toBe("legacy-config");
  });
});
