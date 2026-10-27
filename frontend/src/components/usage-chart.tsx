"use client";
import { useLocale, useTranslations } from "next-intl";
import type { components } from "@/lib/generated/api";
import { formatCost, formatMetric } from "@/lib/format";

type Bucket = components["schemas"]["MetricBucket"];
export function UsageChart({
  title,
  rows,
  metric,
  granularity,
}: {
  title: string;
  rows: Bucket[];
  metric: "tokens" | "usd" | "p50_ms";
  granularity: "hour" | "day" | "month";
}) {
  const t = useTranslations("Insights");
  const locale = useLocale();
  const number = (v: number | null) => formatMetric(v, locale) ?? t("noData");
  const label = (key: string) =>
    new Intl.DateTimeFormat(locale, {
      timeZone: "Asia/Ho_Chi_Minh",
      ...(granularity === "hour"
        ? { hour: "2-digit" }
        : granularity === "month"
          ? { month: "short", year: "2-digit" }
          : { day: "2-digit", month: "short" }),
    }).format(new Date(key.length === 10 ? `${key}T00:00:00+07:00` : key));
  const values = rows.map((r) =>
    metric === "tokens"
      ? r.input_tokens == null || r.output_tokens == null
        ? null
        : r.input_tokens + r.output_tokens
      : metric === "usd"
        ? r.usd == null
          ? null
          : Number(r.usd)
        : r.p50_ms,
  );
  const measured = values.filter((v): v is number => v !== null);
  const max = Math.max(...measured, 1e-9);
  const valueLabel = (r: Bucket, i: number) =>
    metric === "usd"
      ? (formatCost(r.usd, locale) ?? t("noData"))
      : number(values[i]) + (metric === "p50_ms" ? " ms" : "");
  return (
    <article className="chart-card insight-chart">
      <header>
        <h3>{title}</h3>
        <span className="muted">
          {t(granularity === "month" ? "monthBucket" : granularity)}
        </span>
      </header>
      {measured.length ? (
        <>
          <div className="chart-scale">
            {new Intl.NumberFormat(locale, {
              maximumSignificantDigits: 4,
            }).format(max)}
          </div>
          <svg
            viewBox="0 0 520 170"
            role="img"
            aria-label={title}
            className="usage-chart"
          >
            {[0, 0.5, 1].map((v) => (
              <line
                key={v}
                x1="12"
                x2="508"
                y1={150 - v * 130}
                y2={150 - v * 130}
                stroke="var(--line)"
                strokeDasharray="3 5"
              />
            ))}
            {values.map((v, i) => {
              if (v === null) return null;
              const x = 12 + ((i + 0.5) * 496) / Math.max(rows.length, 1);
              const height = (v / max) * 130;
              const width = Math.min(26, 350 / Math.max(rows.length, 1));
              const inputHeight =
                metric === "tokens" && v > 0
                  ? (height * (rows[i].input_tokens ?? 0)) / v
                  : height;
              return (
                <g
                  key={rows[i].key}
                  tabIndex={0}
                  role="img"
                  aria-label={`${label(rows[i].key)}: ${valueLabel(rows[i], i)}`}
                >
                  <title>
                    {label(rows[i].key)}: {valueLabel(rows[i], i)}
                  </title>
                  <rect
                    x={x - width / 2}
                    y={150 - inputHeight}
                    width={width}
                    height={Math.max(inputHeight, v === 0 ? 1 : 0)}
                    rx="2"
                    fill="#034EA2"
                  />
                  {metric === "tokens" && (
                    <rect
                      x={x - width / 2}
                      y={150 - height}
                      width={width}
                      height={height - inputHeight}
                      rx="2"
                      fill="#8AB5DF"
                    />
                  )}
                </g>
              );
            })}
          </svg>
          <div className="chart-dates">
            <span>{rows[0] && label(rows[0].key)}</span>
            <span>{rows.at(-1) && label(rows.at(-1)!.key)}</span>
          </div>
          {metric === "tokens" && (
            <p className="chart-legend">
              <span>{t("input")}</span>
              <span>{t("output")}</span>
            </p>
          )}
          <details className="chart-data">
            <summary>{t("viewTable")}</summary>
            <div className="table-scroll">
              <table>
                <thead>
                  <tr>
                    <th>{t("period")}</th>
                    <th>{title}</th>
                  </tr>
                </thead>
                <tbody>
                  {rows.map((r, i) => (
                    <tr key={r.key}>
                      <td>{label(r.key)}</td>
                      <td>{valueLabel(r, i)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </details>
        </>
      ) : (
        <div className="chart-empty-state">
          <strong>{t("noData")}</strong>
          <p>{t("measuredOnly")}</p>
        </div>
      )}
    </article>
  );
}
