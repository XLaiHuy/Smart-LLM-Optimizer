"use client";
import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  Download,
  ArrowUpRight,
  Sparkles,
  Layers,
  Cpu,
  Coins,
  Clock,
  FileCode,
} from "lucide-react";
import { useLocale, useTranslations } from "next-intl";
import { api, unwrap } from "@/lib/api";
import { formatCost, formatMetric } from "@/lib/format";
import { Drawer, Spinner } from "./ui";
import { DynamicNeuralRoutingCosmos3D } from "./3d";

export function TraceInspector({
  requestId,
  userId,
  onClose,
}: {
  requestId: string | null;
  userId: string;
  onClose: () => void;
}) {
  const t = useTranslations("App");
  const mvp = useTranslations("MVP");
  const locale = useLocale();
  const [activeTab, setActiveTab] = useState<"cosmos" | "stages" | "metrics">("cosmos");

  const trace = useQuery({
    queryKey: ["trace", userId, requestId],
    enabled: !!requestId,
    queryFn: async () =>
      unwrap(
        await api.GET("/v1/traces/{request_id}", {
          params: { path: { request_id: requestId! } },
        }),
      ),
  });
  const data = trace.data;

  const isResearch =
    !!data &&
    ((data.route.reason_code || data.route.reason).startsWith("ROUTE_ML_RESEARCH_") ||
      data.route.rules_matched?.includes("operator_accepted_research"));

  function runtimeState(value: boolean | null | undefined) {
    return value == null
      ? t("runtimeUnknown")
      : value
        ? t("runtimeYes")
        : t("runtimeNo");
  }

  function download() {
    if (!data) return;
    const url = URL.createObjectURL(
      new Blob([JSON.stringify(data, null, 2)], { type: "application/json" }),
    );
    const link = document.createElement("a");
    link.href = url;
    link.download = `${data.execution_source || "unknown"}-trace-${requestId}.json`;
    link.click();
    URL.revokeObjectURL(url);
  }

  return (
    <Drawer
      open={!!requestId}
      onOpenChange={(open) => !open && onClose()}
      title={t("trace")}
      description={t("traceHint")}
    >
      {trace.isLoading && (
        <div className="flex h-64 items-center justify-center">
          <Spinner />
        </div>
      )}
      {trace.isError && <p className="muted p-4">{t("traceContentUnavailable")}</p>}

      {data && (
        <div className="trace-content flex flex-col gap-4">
          {/* Top Key Metrics Header */}
          <div className="trace-top flex items-center justify-between border-b border-slate-200 pb-3">
            <div className="flex items-center gap-2">
              <span className="mock-badge font-semibold">
                {data.execution_source.toUpperCase()}
              </span>
              <span className="text-xs text-slate-500 font-mono">
                #{data.request_id.slice(0, 8)}
              </span>
            </div>
            <button className="button small flex items-center gap-1.5" onClick={download}>
              <Download size={14} />
              {t("export")}
            </button>
          </div>

          {/* Quick Summary KPI Cards */}
          <div className="grid grid-cols-3 gap-2.5">
            <div className="rounded-xl border border-sky-100 bg-sky-50/70 p-3 flex flex-col gap-1">
              <div className="flex items-center gap-1 text-[11px] font-medium text-sky-800">
                <Cpu size={13} />
                <span>{locale === "vi" ? "Model Lựa Chọn" : "Target Model"}</span>
              </div>
              <strong className="text-sm font-semibold text-sky-950 truncate" title={data.route.model_id}>
                {data.route.model_id.includes("20b")
                  ? "GPT-OSS 20B"
                  : data.route.model_id.includes("luna")
                    ? "GPT-6 Luna"
                    : "GPT-OSS 120B"}
              </strong>
            </div>

            <div className="rounded-xl border border-emerald-100 bg-emerald-50/70 p-3 flex flex-col gap-1">
              <div className="flex items-center gap-1 text-[11px] font-medium text-emerald-800">
                <Clock size={13} />
                <span>{t("latency")}</span>
              </div>
              <strong className="text-sm font-semibold text-emerald-950">
                {formatMetric(data.timing.e2e_ms, locale, " ms")}
              </strong>
            </div>

            <div className="rounded-xl border border-indigo-100 bg-indigo-50/70 p-3 flex flex-col gap-1">
              <div className="flex items-center gap-1 text-[11px] font-medium text-indigo-800">
                <Coins size={13} />
                <span>{t("cost")}</span>
              </div>
              <strong className="text-sm font-semibold text-indigo-950">
                {formatCost(data.cost.serving_usd, locale) ?? "$0.0000"}
              </strong>
            </div>
          </div>

          {/* Sub Navigation Tabs */}
          <div className="flex border-b border-slate-200 mt-1">
            <button
              type="button"
              onClick={() => setActiveTab("cosmos")}
              className={`pb-2.5 px-3 text-xs font-semibold flex items-center gap-1.5 border-b-2 transition ${
                activeTab === "cosmos"
                  ? "border-[#005696] text-[#005696]"
                  : "border-transparent text-slate-500 hover:text-slate-800"
              }`}
            >
              <Sparkles size={14} />
              {locale === "vi" ? "Thiên Hà Định Tuyến 3D" : "3D Router Cosmos"}
            </button>
            <button
              type="button"
              onClick={() => setActiveTab("stages")}
              className={`pb-2.5 px-3 text-xs font-semibold flex items-center gap-1.5 border-b-2 transition ${
                activeTab === "stages"
                  ? "border-[#005696] text-[#005696]"
                  : "border-transparent text-slate-500 hover:text-slate-800"
              }`}
            >
              <Layers size={14} />
              {locale === "vi" ? "Tiến Trình & Lõi Tối Ưu" : "Pipeline Stages"}
            </button>
            <button
              type="button"
              onClick={() => setActiveTab("metrics")}
              className={`pb-2.5 px-3 text-xs font-semibold flex items-center gap-1.5 border-b-2 transition ${
                activeTab === "metrics"
                  ? "border-[#005696] text-[#005696]"
                  : "border-transparent text-slate-500 hover:text-slate-800"
              }`}
            >
              <FileCode size={14} />
              {locale === "vi" ? "Kiểm Toán Kỹ Thuật" : "Audit Specs"}
            </button>
          </div>

          {/* Tab 1: 3D Cosmos View */}
          {activeTab === "cosmos" && (
            <div className="flex flex-col gap-3">
              <div className="rounded-2xl border border-slate-200 overflow-hidden bg-slate-900 shadow-sm">
                <div className="bg-slate-950/80 px-3.5 py-2 flex items-center justify-between text-xs text-slate-300 border-b border-slate-800">
                  <span className="flex items-center gap-1.5">
                    <span className="h-2 w-2 rounded-full bg-emerald-400 animate-pulse" />
                    {locale === "vi"
                      ? "Không gian 3D Attention & 3 Model"
                      : "3D Attention Constellation & 3 Active Models"}
                  </span>
                  <span className="text-[11px] font-mono text-cyan-300">
                    {data.route.model_id}
                  </span>
                </div>
                <DynamicNeuralRoutingCosmos3D
                  routedModel={data.route.model_id}
                  attention={data.route.attention_features}
                  height={280}
                  interactive
                  compact
                />
              </div>

              <div className="p-3 bg-slate-50 rounded-xl border border-slate-200 text-xs flex flex-col gap-1.5">
                <div className="flex justify-between items-center">
                  <span className="text-slate-600 font-medium">{t("routingReason")}:</span>
                  <span className="font-mono text-slate-800 font-semibold bg-white px-2 py-0.5 rounded border border-slate-200">
                    {data.route.reason_code || data.route.reason}
                  </span>
                </div>
                {isResearch && (
                  <p className="text-[11px] text-sky-700 font-medium">{t("researchRoutingHint")}</p>
                )}
                {(data.route.reason_code || data.route.reason) === "ML_UNREVIEWED_SCOPE_FALLBACK" && (
                  <p className="text-[11px] text-amber-700">{t("unreviewedScope")}</p>
                )}
              </div>
            </div>
          )}

          {/* Tab 2: Pipeline Stages & Calls */}
          {activeTab === "stages" && (
            <div className="flex flex-col gap-4">
              <div>
                <h4 className="text-xs font-bold uppercase tracking-wider text-slate-500 mb-2">
                  {t("effective")}
                </h4>
                <div className="module-list flex flex-col gap-2">
                  {data.optimizations.map((state) => (
                    <div
                      key={state.module}
                      className="module-row p-2.5 rounded-xl border border-slate-200 bg-white shadow-xs flex items-center justify-between"
                    >
                      <div>
                        <strong className="text-xs font-semibold text-slate-800">{t(state.module)}</strong>
                        <p className="text-[11px] text-slate-500 font-mono mt-0.5">{state.reason}</p>
                      </div>
                      <span className="status-pill text-[11px] font-medium">{t(state.status)}</span>
                    </div>
                  ))}
                </div>
              </div>

              <div>
                <h4 className="text-xs font-bold uppercase tracking-wider text-slate-500 mb-2">
                  {t("calls")}
                </h4>
                <div className="flex flex-col gap-2">
                  {data.calls.map((call) => (
                    <div
                      className="call-row p-2.5 rounded-xl border border-slate-200 bg-white flex items-center justify-between shadow-xs"
                      key={call.call_id}
                    >
                      <div className="flex items-center gap-2.5">
                        <ArrowUpRight size={16} className="text-sky-600 shrink-0" />
                        <div>
                          <strong className="text-xs text-slate-900">{call.model_id}</strong>
                          <div className="text-[11px] text-slate-500 flex gap-1.5 mt-0.5">
                            <span>{call.stage}</span>
                            <span>·</span>
                            <span>{formatMetric(call.duration_ms, locale, " ms")}</span>
                            {call.provider_host && (
                              <>
                                <span>·</span>
                                <span>{call.provider_host}</span>
                              </>
                            )}
                          </div>
                          {call.error_code && (
                            <small className="text-[10px] font-mono text-red-600 block mt-0.5">
                              {call.error_code} · HTTP {call.upstream_status ?? "—"} · {call.dispatch_state}
                            </small>
                          )}
                        </div>
                      </div>
                      <span className="mock-badge text-[10px]">
                        {call.cost?.status ?? "settled"}
                      </span>
                    </div>
                  ))}
                </div>
              </div>
            </div>
          )}

          {/* Tab 3: Detailed Technical Audit */}
          {activeTab === "metrics" && (
            <div className="flex flex-col gap-3">
              <dl className="trace-details grid grid-cols-2 gap-x-4 gap-y-2 text-xs bg-slate-50 p-3.5 rounded-xl border border-slate-200">
                <dt className="text-slate-500">{t("request")}</dt>
                <dd className="mono text-right font-medium text-slate-800">{data.request_id.slice(0, 16)}...</dd>

                <dt className="text-slate-500">{t("policy")}</dt>
                <dd className="mono text-right font-medium text-slate-800">{data.effective_configuration.policy_id}</dd>

                <dt className="text-slate-500">{t("mlLoaded")}</dt>
                <dd className="text-right font-medium text-slate-800">{runtimeState(data.route.ml_loaded)}</dd>

                <dt className="text-slate-500">{t("mlExecuted")}</dt>
                <dd className="text-right font-medium text-slate-800">{runtimeState(data.route.ml_executed)}</dd>

                <dt className="text-slate-500">{t("attentionLoaded")}</dt>
                <dd className="text-right font-medium text-slate-800">{runtimeState(data.route.attention_loaded)}</dd>

                <dt className="text-slate-500">{t("attentionExecuted")}</dt>
                <dd className="text-right font-medium text-slate-800">{runtimeState(data.route.attention_executed)}</dd>

                <dt className="text-slate-500">{mvp("input")}</dt>
                <dd className="text-right font-medium text-slate-800">{formatMetric(data.usage.input_tokens, locale)} tokens</dd>

                <dt className="text-slate-500">{mvp("output")}</dt>
                <dd className="text-right font-medium text-slate-800">{formatMetric(data.usage.output_tokens, locale)} tokens</dd>

                <dt className="text-slate-500">Cached Input</dt>
                <dd className="text-right font-medium text-slate-800">{data.usage.cached_input_tokens ?? 0} tokens</dd>

                <dt className="text-slate-500">Reasoning Tokens</dt>
                <dd className="text-right font-medium text-slate-800">{data.usage.reasoning_tokens ?? 0} tokens</dd>

                <dt className="text-slate-500">Price Version</dt>
                <dd className="text-right font-medium text-slate-800">{data.cost.price_catalog_version ?? "v5"}</dd>
              </dl>

              {!!data.citations?.length && (
                <section className="mt-2">
                  <h4 className="text-xs font-bold text-slate-600 mb-1">{mvp("sources")}</h4>
                  <p className="text-[11px] text-slate-500 mb-2">{mvp("sourceHint")}</p>
                  {data.citations.map((c) => (
                    <details className="source-card text-xs p-2.5 rounded-lg border border-slate-200 bg-white mb-2" key={c.chunk_id}>
                      <summary className="font-medium text-slate-800 cursor-pointer">
                        {c.filename} · {c.location}
                      </summary>
                      <small className="font-mono text-slate-400 block mt-1">[{c.chunk_id}]</small>
                      <pre className="document-preview text-[11px] mt-2 bg-slate-50 p-2 rounded border border-slate-100 overflow-x-auto text-slate-700">
                        {c.excerpt}
                      </pre>
                    </details>
                  ))}
                </section>
              )}

              <details className="json-details text-xs mt-2 border border-slate-200 rounded-lg p-2.5 bg-white">
                <summary className="font-semibold text-slate-700 cursor-pointer">{t("rawTrace")}</summary>
                <pre className="mt-2 text-[10px] font-mono bg-slate-900 text-slate-200 p-3 rounded-lg overflow-x-auto max-h-60">
                  {JSON.stringify(data, null, 2)}
                </pre>
              </details>
            </div>
          )}
        </div>
      )}
    </Drawer>
  );
}
