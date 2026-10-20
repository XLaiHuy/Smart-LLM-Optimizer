import { describe, expect, it } from "vitest";
import { formatCost, formatMetric } from "./format";
import { requestFlags } from "./api";
import vi from "../messages/vi.json";
import en from "../messages/en.json";

describe("honest metrics and configuration", () => {
  it("keeps unknown metrics distinct from measured zero", () => {
    expect(formatCost(null, "en")).toBeNull();
    expect(formatMetric(undefined, "vi")).toBeNull();
    expect(formatMetric(0, "en", " ms")).toBe("0 ms");
    expect(formatCost("0.000000001", "en")).toContain("0.000000001");
  });
  it("baseline flags cannot leak selected optimized flags", () => {
    const flags = { router: true, rewrite: true, context: true, memory: true };
    expect(Object.values(requestFlags("baseline", flags))).toEqual([
      false,
      false,
      false,
      false,
    ]);
    expect(Object.values(flags)).toEqual([true, true, true, true]);
  });
  it("keeps both translations complete", () => {
    expect(Object.keys(vi.App).sort()).toEqual(Object.keys(en.App).sort());
    expect(Object.keys(vi.Errors).sort()).toEqual(
      Object.keys(en.Errors).sort(),
    );
  });
});
