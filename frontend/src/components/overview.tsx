"use client";
import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { ArrowUpRight, ArrowRight, Activity } from "lucide-react";
import { useLocale, useTranslations } from "next-intl";
import { api, unwrap, type User } from "@/lib/api";
import { formatMetric } from "@/lib/format";
import { ErrorNotice, Spinner } from "./ui";
import { useState } from "react";
import { AnalyticsPanel } from "./analytics";
export function OverviewPanel({
  user,
  onTrace,
}: {
  user: User;
  onTrace: (id: string) => void;
}) {
  const t = useTranslations("App");
  const insights = useTranslations("Insights");
  const [personal, setPersonal] = useState(true);
  const locale = useLocale();
  const query = useQuery({
    queryKey: ["overview", user.id],
    enabled: personal,
    queryFn: async () => unwrap(await api.GET("/v1/overview")),
  });
  const data = query.data;
  return (
    <div className="overview-page">
      <AnalyticsPanel user={user} onScopeChange={setPersonal} />
      {personal && query.isLoading && <Spinner />}
      {personal && query.isError && <ErrorNotice error={query.error} />}{" "}
      {personal && data && (
        <>
          {" "}
          <section className="activity-panel recent-activity">
            <header>
              <div>
                <h2>{t("recent")}</h2>
                <small className="muted">{insights("recentAllTime")}</small>
              </div>
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
                      <th>{insights("source")}</th>
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
                        <td>{insights(row.execution_source)}</td>
                        <td>
                          {new Intl.DateTimeFormat(locale, {
                            dateStyle: "short",
                            timeStyle: "short",
                            timeZone: "Asia/Ho_Chi_Minh",
                          }).format(new Date(row.created_at))}
                        </td>
                        <td>
                          {formatMetric(row.e2e_ms, locale, " ms") ??
                            insights("noTiming")}
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
        </>
      )}
    </div>
  );
}
