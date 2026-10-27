import type { components } from "./generated/api";
export type Execution = components["schemas"]["RequestExecution"];
export type RuntimeModel = components["schemas"]["RuntimeModel"];
export const PIPELINE = [
  {
    id: "admission",
    events: ["admission"],
    vi: "Tiếp nhận & bảo vệ",
    en: "Admission & protection",
    detail: "Auth · ownership · dedupe · session lease",
  },
  {
    id: "history",
    events: ["history", "documents"],
    vi: "Lịch sử & tài liệu",
    en: "History & documents",
    detail: "SQLite · raw history · RAG",
  },
  {
    id: "prepare",
    events: ["memory", "context", "compression"],
    vi: "Chuẩn bị ngữ cảnh",
    en: "Context preparation",
    detail: "Memory → context → compression → prompt",
  },
  {
    id: "route",
    events: ["classification", "encoder_attention", "route"],
    vi: "ML + Attention & chọn model",
    en: "ML + Attention & selection",
    detail:
      "Task → ONNX encoder → 6-query Attention → candidate heads → calibration → thresholds",
  },
  {
    id: "reserve",
    events: ["reserve"],
    vi: "Quota & ngân sách",
    en: "Quota & budget",
    detail: "Feasibility · admission · reserve per call",
  },
  {
    id: "generation",
    events: ["generate", "validation", "settlement"],
    vi: "Provider & kiểm định",
    en: "Provider & validation",
    detail: "Generation → validator → eligible escalation · settle each call",
  },
  {
    id: "commit",
    events: ["commit", "memory_update"],
    vi: "Lưu kết quả",
    en: "Commit result",
    detail: "Atomic message pair · memory update · execution trace",
  },
] as const;

export function pipelineState(
  execution: Execution | undefined,
  names: readonly string[],
) {
  if (!execution) return "unknown";
  const events = execution.events.filter((e) => names.includes(e.stage));
  if (!events.length) return "unknown";
  // A later successful retry does not erase the evidence of an earlier failure.
  if (events.some((e) => e.status === "failed")) return "failed";
  const latest = new Map(events.map((e) => [e.stage, e.status]));
  if ([...latest.values()].includes("running"))
    return execution.status === "running" ? "running" : "unknown";
  if ([...latest.values()].includes("interrupted")) return "interrupted";
  if ([...latest.values()].every((s) => s === "skipped")) return "skipped";
  if ([...latest.values()].some((s) => s === "unknown")) return "unknown";
  return "succeeded";
}

export function callPaths(
  execution: Execution | undefined,
  models: RuntimeModel[],
) {
  return (execution?.calls ?? [])
    .filter((c) => c.stage === "provider")
    .map((call, i) => ({
      sequence: i + 1,
      call,
      model: models.find((m) => m.model_id === call.model_id),
      failed:
        !!call.error_code ||
        execution?.events.some(
          (e) =>
            e.stage === "validation" &&
            e.status === "failed" &&
            e.details?.call_id === call.call_id,
        ),
    }));
}
