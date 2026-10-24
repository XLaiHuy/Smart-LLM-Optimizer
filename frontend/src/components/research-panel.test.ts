import { describe, expect, it, vi } from "vitest";
import type { components } from "../lib/generated/api";

vi.mock("@/lib/api", () => ({
  api: {},
  unwrap: <T>(x: T): T => x,
  ApiError: class extends Error {},
}));

vi.mock("./ui", () => ({
  Drawer: () => null,
  ErrorNotice: () => null,
  Spinner: () => null,
}));

vi.mock("next-intl", () => ({
  useTranslations: () => (key: string) => key,
  useLocale: () => "vi",
}));

vi.mock("@tanstack/react-query", () => ({
  useQuery: () => ({ data: undefined, isLoading: false, isError: false }),
  useQueryClient: () => ({ invalidateQueries: vi.fn() }),
}));

import {
  calculateCostSavingsPct,
  calculatePassRate,
  calculateDynamicRoutingAllocation,
  mapPoliciesToParetoCandidates,
  getPolicyLabel,
} from "./research-panel";
import { DEMO_PARETO_POLICIES } from "./3d";

describe("Router Lab 2-Mode Architecture & Calculation Logic", () => {
  describe("Cost Savings and Pass Rate Calculations", () => {
    it("calculates cost savings percentage correctly", () => {
      // Normal saving
      expect(calculateCostSavingsPct(0.001, 0.00075)).toBe(25);
      // Equal cost => 0%
      expect(calculateCostSavingsPct(0.001, 0.001)).toBe(0);
      // Higher cost => 0%
      expect(calculateCostSavingsPct(0.001, 0.0015)).toBe(0);
      // Zero baseline => 0%
      expect(calculateCostSavingsPct(0, 0.0005)).toBe(0);
    });

    it("calculates quality pass rate accurately", () => {
      expect(calculatePassRate(196, 200)).toBeCloseTo(0.98, 4);
      expect(calculatePassRate(0, 100)).toBe(0);
      expect(calculatePassRate(50, 0)).toBe(0);
    });
  });

  describe("Dynamic Routing Allocation & Tau Threshold Monotonicity", () => {
    it("allocates higher shares to Free Tier when cost priority is high (w = 0)", () => {
      const res = calculateDynamicRoutingAllocation(0.0);
      expect(res.llamaPct).toBeGreaterThan(45);
      expect(res.qwenPct).toBeGreaterThan(25);
      expect(res.baselineRefPct).toBeLessThan(10);
      expect(res.tauThreshold).toBe(0.4);

      // Verify total sum equals 100%
      const total =
        res.llamaPct + res.qwenPct + res.geminiPct + res.baselineRefPct;
      expect(total).toBe(100);
    });

    it("allocates balanced shares at default operating point (w = 0.65)", () => {
      const res = calculateDynamicRoutingAllocation(0.65);
      expect(res.llamaPct).toBeGreaterThan(35);
      expect(res.llamaPct).toBeLessThan(50);
      expect(res.tauThreshold).toBeCloseTo(0.69, 2);

      const total =
        res.llamaPct + res.qwenPct + res.geminiPct + res.baselineRefPct;
      expect(total).toBe(100);
    });

    it("allocates higher shares to reference model when quality priority is high (w = 1.0)", () => {
      const res = calculateDynamicRoutingAllocation(1.0);
      expect(res.llamaPct).toBeLessThan(40);
      expect(res.baselineRefPct).toBeGreaterThan(15);
      expect(res.tauThreshold).toBe(0.85);

      const total =
        res.llamaPct + res.qwenPct + res.geminiPct + res.baselineRefPct;
      expect(total).toBe(100);
    });

    it("guarantees 100% sum invariant across arbitrary intermediate trade-off values", () => {
      const weights = [0.0, 0.15, 0.33, 0.5, 0.65, 0.82, 1.0];
      for (const w of weights) {
        const res = calculateDynamicRoutingAllocation(w);
        const sum =
          res.llamaPct + res.qwenPct + res.geminiPct + res.baselineRefPct;
        expect(sum).toBe(100);
        expect(res.tauThreshold).toBeGreaterThanOrEqual(0.4);
        expect(res.tauThreshold).toBeLessThanOrEqual(0.85);
      }
    });
  });

  describe("Pareto Candidate Mapping & Policy Labeling", () => {
    it("falls back gracefully to DEMO_PARETO_POLICIES when summaries are empty", () => {
      expect(mapPoliciesToParetoCandidates(undefined)).toEqual(
        DEMO_PARETO_POLICIES,
      );
      expect(mapPoliciesToParetoCandidates([])).toEqual(DEMO_PARETO_POLICIES);
    });

    it("maps genuine PolicySummary objects to PolicyCandidateMetrics correctly", () => {
      const summaries: components["schemas"]["PolicySummary"][] = [
        {
          policy: "fixed_reference",
          trials: 200,
          calls: 200,
          functional_passes: 198,
          errors: 0,
          fallbacks: 0,
          simulation_upper_usd: "0.00100",
          calculated_usd: "0.00100",
          p50_ms: 180,
          p95_ms: 220,
        },
        {
          policy: "ml_router",
          trials: 200,
          calls: 200,
          functional_passes: 196,
          errors: 0,
          fallbacks: 0,
          simulation_upper_usd: "0.00075",
          calculated_usd: "0.00075",
          p50_ms: 125,
          p95_ms: 170,
        },
      ];

      const mapped = mapPoliciesToParetoCandidates(summaries);
      expect(mapped).toHaveLength(2);

      const ref = mapped.find((p) => p.id === "fixed_reference");
      expect(ref).toBeDefined();
      expect(ref?.passRate).toBe(0.99);
      expect(ref?.savingsPct).toBe(0);

      const ml = mapped.find((p) => p.id === "ml_router");
      expect(ml).toBeDefined();
      expect(ml?.passRate).toBe(0.98);
      expect(ml?.costUsd).toBe(0.00075);
      expect(ml?.savingsPct).toBe(25);
      expect(ml?.isParetoOptimal).toBe(true);
    });

    it("resolves policy labels cleanly with fallback map", () => {
      expect(getPolicyLabel("fixed_reference")).toContain("tham chiếu");
      expect(getPolicyLabel("ml_router")).toContain("ML Router");
      expect(getPolicyLabel("rule_guarded")).toContain("quy tắc");
      expect(getPolicyLabel("fixed_candidate:llama-3-70b")).toContain(
        "llama-3-70b",
      );
      expect(getPolicyLabel("custom_policy")).toBe("custom_policy");
    });
  });
});
