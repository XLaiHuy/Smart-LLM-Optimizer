"use client";
import { useQuery } from "@tanstack/react-query";
import { Download, ArrowUpRight } from "lucide-react";
import { useLocale, useTranslations } from "next-intl";
import { api, unwrap } from "@/lib/api";
import { formatMetric } from "@/lib/format";
import { Drawer, ErrorNotice, Spinner } from "./ui";

export function TraceInspector({
  requestId,
  onClose,
}: {
  requestId: string | null;
  onClose: () => void;
}) {
  const t = useTranslations("App");
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
    link.download = `mock-trace-${requestId}.json`;
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
            <span className="mock-badge">MOCK · G0</span>
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
            <dd>{t("notBillable")}</dd>
            <dt>{t("quality")}</dt>
            <dd>{t("noLive")}</dd>
            <dt>{t("usage")}</dt>
            <dd>
              {t("unknown")} · {data.usage.usage_source}
            </dd>
          </dl>
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
              <span className="mock-badge">MOCK</span>
            </div>
          ))}
          <details className="json-details">
            <summary>{t("rawTrace")}</summary>
            <pre>{JSON.stringify(data, null, 2)}</pre>
          </details>
        </div>
      )}
    </Drawer>
  );
}
