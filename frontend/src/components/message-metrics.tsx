"use client";
import { useEffect, useRef, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { useLocale, useTranslations } from "next-intl";
import Link from "next/link";
import { BarChart2, Cpu, Info } from "lucide-react";
import { api, unwrap } from "@/lib/api";
import { formatCost, formatMetric, knownTokenTotal } from "@/lib/format";
import { ProcessingProgress } from "./processing-progress";

export function MessageMetrics({
  requestId,
  onTrace,
}: {
  requestId: string;
  onTrace?: (requestId: string) => void;
}) {
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

  const isBaseline =
    data.effective_configuration?.policy_id?.startsWith("fixed_candidate:") ||
    data.effective_configuration?.policy_id === "baseline" ||
    (!data.effective_configuration?.flags?.router &&
      !data.effective_configuration?.flags?.rewrite);

  return (
    <div ref={anchor} className="message-metrics">
      <div
        className="metrics-model-pill"
        onClick={() => onTrace?.(requestId)}
        role={onTrace ? "button" : undefined}
        tabIndex={onTrace ? 0 : undefined}
        title={onTrace ? "Xem chi tiết định tuyến và tối ưu" : undefined}
      >
        <Cpu size={12} className="metrics-icon" />
        <span className="metrics-model-name">{modelName}</span>
        {data.execution_source === "mock" && (
          <span className="mock-badge">{i(data.execution_source)}</span>
        )}
        {isBaseline && (
          <span
            className="baseline-tag-pill"
            title="Mô hình tiêu chuẩn (Direct pass-through)"
          >
            Tiêu chuẩn
          </span>
        )}
      </div>

      <div className="metrics-data-chips">
        <span className="metrics-time-tag" title={i("serverTiming")}>
          {formatMetric(data.timing.e2e_ms / 1000, locale, " s") ??
            i("noTiming")}
        </span>
        <span
          className="metrics-token-tag estimated"
          title={`${data.usage.usage_source} - Ước tính số token sử dụng`}
        >
          {totalTokens == null
            ? `~${formatMetric(data.usage.input_tokens, locale) ?? "0"} tok (${locale === "vi" ? "ước tính" : "est"})`
            : `~${formatMetric(totalTokens, locale)} tok (${locale === "vi" ? "ước tính" : "est"})`}
        </span>
        <span
          className="metrics-cost-tag estimated"
          title={`${data.cost.status} - Ước tính chi phí gọi mô hình`}
        >
          {data.cost.status === "not_billable"
            ? t("notBillable")
            : `~${formatCost(data.cost.serving_usd, locale) ?? "$0.00"} (${locale === "vi" ? "ước tính" : "est"})`}
        </span>
        <Link
          href="/dashboard"
          className="metrics-stats-link"
          title={
            locale === "vi"
              ? "Xem số liệu đo đạc thực tế, latency phân vị và sổ cái chi phí tại tab Thống kê"
              : "View measured metrics, latency distribution & ledger in Statistics"
          }
        >
          <BarChart2 size={11} />
          <span>{locale === "vi" ? "Thống kê" : "Stats"}</span>
        </Link>
        {onTrace && (
          <button
            type="button"
            className="metrics-trace-btn"
            onClick={() => onTrace(requestId)}
            title={
              locale === "vi" ? "Xem chi tiết trace" : "View optimization trace"
            }
          >
            <Info size={11} />
            <span>Trace</span>
          </button>
        )}
      </div>

      <ProcessingProgress sessionId={data.session_id} requestId={requestId} />
    </div>
  );
}
