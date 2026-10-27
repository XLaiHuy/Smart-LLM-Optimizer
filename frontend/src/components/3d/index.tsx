"use client";

import dynamic from "next/dynamic";
import React from "react";

// Safe dynamic imports with ssr: false to guarantee zero hydration mismatch in Next.js 16 / React 19
export const DynamicNeuralRoutingCosmos3D = dynamic(
  () => import("./neural-routing-cosmos").then((m) => m.NeuralRoutingCosmos3D),
  {
    ssr: false,
    loading: () => (
      <div className="flex h-[360px] w-full animate-pulse items-center justify-center rounded-2xl border border-slate-200/80 bg-slate-100/70 text-xs font-medium text-slate-400">
        Đang khởi tạo Neural Routing Cosmos 3D...
      </div>
    ),
  },
);

export const DynamicPipelineFlow3D = dynamic(
  () => import("./pipeline-flow-3d").then((m) => m.PipelineFlow3D),
  {
    ssr: false,
    loading: () => (
      <div className="flex h-[480px] w-full animate-pulse items-center justify-center rounded-2xl border border-slate-200/80 bg-slate-100/70 text-xs font-medium text-slate-400">
        Đang khởi tạo Luồng Tối Ưu Hóa 3D (7-Tier End-to-End Pipeline)...
      </div>
    ),
  },
);

export const DynamicParetoScatterSurface3D = dynamic(
  () => import("./pareto-frontier-space").then((m) => m.ParetoScatterSurface3D),
  {
    ssr: false,
    loading: () => (
      <div className="flex h-[420px] w-full animate-pulse items-center justify-center rounded-2xl border border-slate-200/80 bg-slate-100/70 text-xs font-medium text-slate-400">
        Đang tải Không gian 3D Pareto Frontier...
      </div>
    ),
  },
);

export const DynamicTokenCostSpace3D = dynamic(
  () => import("./token-cost-space-3d").then((m) => m.TokenCostSpace3D),
  {
    ssr: false,
    loading: () => (
      <div className="flex h-[420px] w-full animate-pulse items-center justify-center rounded-2xl border border-slate-200/80 bg-slate-100/70 text-xs font-medium text-slate-400">
        Đang tải Không gian Chi phí & Token 3D...
      </div>
    ),
  },
);

export { NeuralRoutingCosmos3D } from "./neural-routing-cosmos";
export type {
  NeuralRoutingCosmos3DProps,
  AttentionWeights,
  DimensionScore,
  ModelNodeDef,
} from "./neural-routing-cosmos";

export {
  PipelineFlow3D,
  SIMULATION_PRESETS,
  LAYER_INFO,
} from "./pipeline-flow-3d";
export type {
  PipelineFlow3DProps,
  PipelineSimulationPreset,
} from "./pipeline-flow-3d";

export {
  ParetoScatterSurface3D,
  DEMO_PARETO_POLICIES,
} from "./pareto-frontier-space";
export type {
  ParetoScatterSurface3DProps,
  PolicyCandidateMetrics,
} from "./pareto-frontier-space";

export { TokenCostSpace3D, DEMO_SESSION_METRICS } from "./token-cost-space-3d";
export type {
  TokenCostSpace3DProps,
  SessionUsageMetric,
} from "./token-cost-space-3d";
