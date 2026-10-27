import { describe, expect, it } from "vitest";
import {
  PIPELINE,
  pipelineState,
  callPaths,
  type Execution,
  type RuntimeModel,
} from "@/lib/execution-view";
const execution = (
  events: Execution["events"],
  status = "succeeded",
): Execution => ({
  request_id: "test",
  status,
  events,
  calls: [],
  legacy: false,
});
const step = (
  stage: string,
  status:
    "running" | "succeeded" | "failed" | "skipped" | "unknown" | "interrupted",
  sequence = 1,
) => ({ stage, status, sequence, at: "2026-10-27T00:00:00Z", details: {} });
describe("Observed request architecture", () => {
  it("has seven distinct service layers without provider internals", () => {
    expect(PIPELINE).toHaveLength(7);
    expect(new Set(PIPELINE.map((s) => s.id)).size).toBe(7);
    expect(PIPELINE.flatMap((s) => [...s.events])).toContain("validation");
  });
  it("does not invent successful stages for historical or partial traces", () => {
    expect(pipelineState(undefined, ["route"])).toBe("unknown");
    expect(pipelineState(execution([]), ["route"])).toBe("unknown");
    expect(
      pipelineState(execution([step("route", "running")]), ["route"]),
    ).toBe("unknown");
  });
  it("tracks actual stage completion, interruption and skip", () => {
    expect(
      pipelineState(execution([step("route", "running")], "running"), [
        "route",
      ]),
    ).toBe("running");
    expect(
      pipelineState(
        execution([step("route", "running"), step("route", "succeeded", 2)]),
        ["route"],
      ),
    ).toBe("succeeded");
    expect(
      pipelineState(execution([step("route", "interrupted")]), ["route"]),
    ).toBe("interrupted");
    expect(
      pipelineState(execution([step("compression", "skipped")]), [
        "compression",
      ]),
    ).toBe("skipped");
  });
  it("retains failures even after a successful retry", () => {
    expect(
      pipelineState(
        execution([
          step("validation", "failed"),
          step("validation", "succeeded", 2),
        ]),
        ["validation"],
      ),
    ).toBe("failed");
  });
  it("links calls by exact model identity and preserves historical models", () => {
    const models = [
      {
        model_id: "openai/gpt-oss-20b",
        label: "20B",
        provider: "openrouter",
        available: true,
      },
    ] satisfies RuntimeModel[];
    const e = execution([]);
    e.calls = [
      { call_id: "a", model_id: "old-llama", stage: "provider" },
      { call_id: "b", model_id: "openai/gpt-oss-20b", stage: "provider" },
      { call_id: "c", model_id: "embedding", stage: "embedding" },
    ] as Execution["calls"];
    const paths = callPaths(e, models);
    expect(paths).toHaveLength(2);
    expect(paths[0].model).toBeUndefined();
    expect(paths[1].model?.label).toBe("20B");
    expect(paths.map((p) => p.sequence)).toEqual([1, 2]);
    expect(models).toHaveLength(1);
  });
});
