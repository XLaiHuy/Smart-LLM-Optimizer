"use client";
import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import {
  ArrowUpRight,
  ArrowRight,
  Activity,
  Clock3,
  CheckCircle2,
  CircleAlert,
  Database,
} from "lucide-react";
import { useLocale, useTranslations } from "next-intl";
import { api, unwrap } from "@/lib/api";
import { formatMetric } from "@/lib/format";
import { ErrorNotice, Spinner } from "./ui";

export function OverviewPanel({
  userId,
  onTrace,
}: {
  userId: string;
  onTrace: (id: string) => void;
}) {
  const t = useTranslations("App");
  const locale = useLocale();
  const query = useQuery({
    queryKey: ["overview", userId],
    queryFn: async () => unwrap(await api.GET("/v1/overview")),
  });
  const data = query.data;
  return (
    <div className="overview-page">
      <header className="page-heading">
        <div>
          <p className="eyebrow">WORKSPACE / OVERVIEW</p>
          <h1>{t("overviewTitle")}</h1>
          <p className="muted">{t("overviewHint")}</p>
        </div>
        <span className="mock-badge">MOCK</span>
      </header>
      {query.isLoading && <Spinner />}
      {query.isError && (
        <>
          <ErrorNotice error={query.error} />
          <button className="button" onClick={() => query.refetch()}>
            {t("retry")}
          </button>
        </>
      )}
      {data && (
        <>
          <div className="stats-grid">
            {[
              {
                label: t("total"),
                value: formatMetric(data.total_requests, locale),
                Icon: Activity,
              },
              {
                label: t("success"),
                value: formatMetric(data.succeeded, locale),
                Icon: CheckCircle2,
              },
              {
                label: t("errors"),
                value: formatMetric(data.failed, locale),
                Icon: CircleAlert,
              },
              {
                label: t("median"),
                value: formatMetric(data.median_latency_ms, locale, " ms"),
                Icon: Clock3,
              },
            ].map(({ label, value, Icon }) => (
              <article className="stat" key={label}>
                <div>
                  <span>{label}</span>
                  <Icon size={17} />
                </div>
                <strong>{value ?? "—"}</strong>
                <small>
                  {t("mockShort")}
                  {label === t("median")
                    ? ` · ${data.latency_sample_count} ${t("samples")}`
                    : " · G0"}
                </small>
              </article>
            ))}
          </div>
          <section className="activity-panel">
            <header>
              <h2>{t("recent")}</h2>
              <span className="muted">
                {data.recent_requests.length} / {data.total_requests}
              </span>
            </header>
            {data.recent_requests.length ? (
              <div className="table-scroll">
                <table>
                  <thead>
                    <tr>
                      <th>{t("request")}</th>
                      <th>{t("status")}</th>
                      <th>{t("time")}</th>
                      <th>{t("latency")}</th>
                      <th>
                        <span className="sr-only">{t("trace")}</span>
                      </th>
                    </tr>
                  </thead>
                  <tbody>
                    {data.recent_requests.map((row) => (
                      <tr key={row.request_id}>
                        <td className="mono">{row.request_id.slice(0, 8)}</td>
                        <td>
                          <span className="status-pill">
                            {t.has(row.status) ? t(row.status) : row.status}
                          </span>
                        </td>
                        <td>
                          {new Intl.DateTimeFormat(locale, {
                            dateStyle: "short",
                            timeStyle: "short",
                          }).format(new Date(row.created_at))}
                        </td>
                        <td>
                          {formatMetric(row.e2e_ms, locale, " ms") ?? "—"}
                        </td>
                        <td>
                          {row.status === "succeeded" && row.session_id && (
                            <button
                              className="icon-button"
                              aria-label={`${t("viewTrace")} ${row.request_id.slice(0, 8)}`}
                              onClick={() => onTrace(row.request_id)}
                            >
                              <ArrowUpRight size={18} />
                            </button>
                          )}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : (
              <div className="activity-empty">
                <Activity size={25} />
                <h3>{t("noActivity")}</h3>
                <p>{t("noActivityHint")}</p>
                <Link className="button" href="/">
                  {t("backToChat")}
                  <ArrowRight size={16} />
                </Link>
              </div>
            )}
          </section>
          <section className="measurement-empty">
            <Database size={23} />
            <div>
              <h2>{t("measurements")}</h2>
              <p>{t("measurementsHint")}</p>
            </div>
            <span className="status-pill">{t("noLive")}</span>
          </section>
        </>
      )}
    </div>
  );
}
