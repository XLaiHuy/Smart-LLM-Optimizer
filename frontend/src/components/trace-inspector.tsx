"use client";
import { useQuery } from "@tanstack/react-query";
import { Download, ArrowUpRight } from "lucide-react";
import { useLocale, useTranslations } from "next-intl";
import { api, unwrap } from "@/lib/api";
import { formatCost, formatMetric } from "@/lib/format";
import { Drawer, ErrorNotice, Spinner } from "./ui";
import { DynamicNeuralRoutingCosmos3D } from "./3d";

export function TraceInspector({
  requestId,
  onClose,
}: {
  requestId: string | null;
  onClose: () => void;
}) {
  const t = useTranslations("App");
  const mvp = useTranslations("MVP");
  const locale = useLocale();
  const trace = useQuery({
    queryKey: ["trace", requestId],
    enabled: !!requestId,
    queryFn: async () =>
      unwrap(
        await api.GET("/v1/traces/{request_id}", {
          params: { path: { request_id: requestId! } },
        }),
      ),
  });
  const data = trace.data;
  function download() {
    const url = URL.createObjectURL(
      new Blob([JSON.stringify(data, null, 2)], { type: "application/json" }),
    );
    const link = document.createElement("a");
    link.href = url;
    link.download = `${data?.execution_source || "unknown"}-trace-${requestId}.json`;
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
      {trace.isLoading && <Spinner />}
      {trace.isError && <ErrorNotice error={trace.error} />}
      {data && (
        <div className="trace-content">
          <div className="trace-top">
            <span className="mock-badge">
              {data.execution_source.toUpperCase()}
            </span>
            <button className="button small" onClick={download}>
              <Download size={15} />
              {t("export")}
            </button>
          </div>
          <dl className="trace-details">
            <dt>{t("request")}</dt>
            <dd className="mono">{data.request_id}</dd>
            <dt>{t("model")}</dt>
            <dd>{data.route.model_id}</dd>
            <dt>{t("policy")}</dt>
            <dd className="mono">{data.effective_configuration.policy_id}</dd>
            <dt>{t("latency")}</dt>
            <dd>{formatMetric(data.timing.e2e_ms, locale, " ms")}</dd>
            <dt>{t("cost")}</dt>
            <dd>
              {formatCost(data.cost.serving_usd, locale) ??
                (data.cost.status === "not_billable"
                  ? t("notBillable")
                  : mvp("unknown"))}{" "}
              · {data.cost.status}
            </dd>
            <dt>{t("quality")}</dt>
            <dd>{t("noLive")}</dd>
            <dt>{t("usage")}</dt>
            <dd>
              {mvp("input")}:{" "}
              {formatMetric(data.usage.input_tokens, locale) ?? "—"} /{" "}
              {mvp("output")}:{" "}
              {formatMetric(data.usage.output_tokens, locale) ?? "—"} ·{" "}
              {data.usage.usage_source}
            </dd>
          </dl>
          <div className="trace-3d-section">
            <div className="trace-3d-header">
              <span>Không gian Định tuyến 3D (Router Galaxy)</span>
              <span className="mono text-[11px] font-normal text-slate-500">
                {data.route.model_id}
              </span>
            </div>
            <DynamicNeuralRoutingCosmos3D
              routedModel={data.route.model_id}
              height={260}
              interactive
              compact
            />
          </div>
          <h3 className="section-label">{t("effective")}</h3>
          <div className="module-list">
            {data.optimizations.map((state) => (
              <div key={state.module} className="module-row">
                <div>
                  <strong>{t(state.module)}</strong>
                  <small className="mono">{state.reason}</small>
                </div>
                <span className="status-pill">{t(state.status)}</span>
              </div>
            ))}
          </div>
          <h3 className="section-label">{t("calls")}</h3>
          {data.calls.map((call) => (
            <div className="call-row" key={call.call_id}>
              <ArrowUpRight size={17} />
              <div>
                <strong>{call.model_id}</strong>
                <small>
                  {call.stage} · {formatMetric(call.duration_ms, locale, " ms")}
                </small>
              </div>
              <span className="mock-badge">
                {call.cost?.status ?? "unknown"}
              </span>
            </div>
          ))}
          <dl className="trace-details">
            <dt>Cached input</dt>
            <dd>{data.usage.cached_input_tokens ?? "—"}</dd>
            <dt>Reasoning (output subset)</dt>
            <dd>{data.usage.reasoning_tokens ?? "—"}</dd>
            <dt>Price version</dt>
            <dd>{data.cost.price_catalog_version ?? "—"}</dd>
          </dl>
          {!!data.citations?.length && (
            <section>
              <h3>{mvp("sources")}</h3>
              <p className="muted">{mvp("sourceHint")}</p>
              {data.citations.map((c) => (
                <details className="source-card" key={c.chunk_id}>
                  <summary>
                    {c.filename} · {c.location}
                  </summary>
                  <small className="mono">[{c.chunk_id}]</small>
                  <pre className="document-preview">{c.excerpt}</pre>
                </details>
              ))}
            </section>
          )}
          <details className="json-details">
            <summary>{t("rawTrace")}</summary>
            <pre>{JSON.stringify(data, null, 2)}</pre>
          </details>
        </div>
      )}
    </Drawer>
  );
}
