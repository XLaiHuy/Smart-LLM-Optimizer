"use client";
import { useEffect, useRef, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { useLocale, useTranslations } from "next-intl";
import { Cpu } from "lucide-react";
import { api, unwrap } from "@/lib/api";
import { formatCost, formatMetric, knownTokenTotal } from "@/lib/format";
import { ProcessingProgress } from "./processing-progress";

export function MessageMetrics({ requestId }: { requestId: string }) {
  const t = useTranslations("MVP");
  const i = useTranslations("Insights");
  const anchor = useRef<HTMLDivElement>(null);
  const [visible, setVisible] = useState(false);
  useEffect(() => {
    const observer = new IntersectionObserver(
      (entries) => {
        if (entries.some((e) => e.isIntersecting)) {
          setVisible(true);
          observer.disconnect();
        }
      },
      { rootMargin: "120px" },
    );
    if (anchor.current) observer.observe(anchor.current);
    return () => observer.disconnect();
  }, []);
  const locale = useLocale();
  const query = useQuery({
    queryKey: ["trace", requestId],
    queryFn: async () =>
      unwrap(
        await api.GET("/v1/traces/{request_id}", {
          params: { path: { request_id: requestId } },
        }),
      ),
    retry: false,
    enabled: visible,
    staleTime: Infinity,
  });
  const data = query.data;
  if (!data)
    return (
      <div ref={anchor} className="metrics-placeholder">
        {query.isError ? i("noTiming") : null}
      </div>
    );

  const modelName =
    data.execution_source === "mock"
      ? i("simulatedModel")
      : data.route.model_id;
  const totalTokens = knownTokenTotal(
    data.usage.input_tokens,
    data.usage.output_tokens,
  );

  return (
    <div ref={anchor} className="message-metrics">
      <div className="metrics-model-pill">
        <Cpu size={12} className="metrics-icon" />
        <span className="metrics-model-name">{modelName}</span>
        {data.execution_source === "mock" && (
          <span className="mock-badge">{i(data.execution_source)}</span>
        )}
      </div>

      <div className="metrics-data-chips">
        <span className="metrics-time-tag" title={i("serverTiming")}>
          {formatMetric(data.timing.e2e_ms / 1000, locale, " s") ??
            i("noTiming")}
        </span>
        <span className="metrics-token-tag" title={data.usage.usage_source}>
          {totalTokens == null
            ? `${t("input")}: ${formatMetric(data.usage.input_tokens, locale) ?? t("unknown")} · ${t("output")}: ${formatMetric(data.usage.output_tokens, locale) ?? t("unknown")}`
            : `${formatMetric(totalTokens, locale)} tokens`}
        </span>
        <span className="metrics-cost-tag" title={data.cost.status}>
          {formatCost(data.cost.serving_usd, locale) ??
            (data.cost.status === "not_billable"
              ? t("notBillable")
              : t("unknown"))}
        </span>
      </div>

      <ProcessingProgress sessionId={data.session_id} requestId={requestId} />
    </div>
  );
}
