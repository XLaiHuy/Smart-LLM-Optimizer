"use client";
import { useQuery } from "@tanstack/react-query";
import { useLocale, useTranslations } from "next-intl";
import { api, unwrap } from "@/lib/api";
import { formatCost, formatMetric } from "@/lib/format";

export function MessageMetrics({ requestId }: { requestId: string }) {
  const t = useTranslations("MVP");
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
  });
  const data = query.data;
  if (!data) return null;
  return (
    <div className="message-metrics">
      <span className="mock-badge">{data.execution_source.toUpperCase()}</span>
      <span>{data.route.model_id}</span>
      <span title={data.usage.usage_source}>
        {t("input")}: {formatMetric(data.usage.input_tokens, locale) ?? "—"} ·{" "}
        {t("output")}: {formatMetric(data.usage.output_tokens, locale) ?? "—"}
      </span>
      <span title={data.cost.status}>
        {formatCost(data.cost.serving_usd, locale) ??
          (data.cost.status === "not_billable"
            ? t("notBillable")
            : t("unknown"))}
      </span>
    </div>
  );
}
