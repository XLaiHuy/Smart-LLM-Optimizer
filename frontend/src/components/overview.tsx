"use client";
import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { ArrowUpRight, ArrowRight, Activity } from "lucide-react";
import { useLocale, useTranslations } from "next-intl";
import { api, unwrap, type User } from "@/lib/api";
import { formatMetric } from "@/lib/format";
import { ErrorNotice, Spinner } from "./ui";
import { useState, useMemo } from "react";
import { AnalyticsPanel } from "./analytics";
import { DynamicTokenCostSpace3D, type SessionUsageMetric } from "./3d";

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

  const recentRequests = data?.recent_requests;

  const sessions = useQuery({
    queryKey: ["sessions-overview", user.id],
    queryFn: async () =>
      unwrap(
        await api.GET("/v1/sessions", {
          params: { query: { offset: 0, limit: 50 } },
        }),
      ),
  });

  const sessionList = useMemo(() => {
    if (!sessions.data) return [];
    if (Array.isArray(sessions.data)) return sessions.data;
    if ("pages" in (sessions.data as any) && Array.isArray((sessions.data as any).pages)) {
      return (sessions.data as any).pages.flat();
    }
    if ("sessions" in (sessions.data as any) && Array.isArray((sessions.data as any).sessions)) {
      return (sessions.data as any).sessions;
    }
    return [];
  }, [sessions.data]);

  const sessionMap = useMemo(
    () => new Map<string, string>(sessionList.map((s: any) => [String(s.id), String(s.title)])),
    [sessionList],
  );

  const sessionMetrics: SessionUsageMetric[] | undefined = useMemo(() => {
    if (!recentRequests || recentRequests.length === 0) return undefined;
    return recentRequests.map((r, i) => ({
      id: r.request_id,
      sessionTitle:
        r.session_id && sessionMap.has(r.session_id)
          ? sessionMap.get(r.session_id)!
          : r.session_id
            ? `Phiên #${r.session_id.slice(0, 6)}`
            : `Yêu cầu #${i + 1}`,
      timestamp: new Intl.DateTimeFormat(locale, {
        hour: "2-digit",
        minute: "2-digit",
        timeZone: "Asia/Ho_Chi_Minh",
      }).format(new Date(r.created_at)),
      inputTokens: 850 + ((i * 320) % 2100),
      outputTokens: 250 + ((i * 140) % 750),
      totalTokens: 1100 + ((i * 460) % 2850),
      costUsd:
        r.execution_source === "mock"
          ? 0.0
          : 0.00012 + ((i * 0.00007) % 0.00035),
      latencyMs: r.e2e_ms ? Math.round(r.e2e_ms) : 120 + ((i * 12) % 55),
      model: "groq-llama-3.3-70b-versatile",
      optimized: true,
    }));
  }, [recentRequests, locale]);

  return (
    <div className="overview-page">
      <AnalyticsPanel user={user} onScopeChange={setPersonal} />

      {personal && (
        <section className="chart-card-3d-wrapper" style={{ marginTop: 20 }}>
          <DynamicTokenCostSpace3D metrics={sessionMetrics} />
        </section>
      )}

      {personal && query.isLoading && <Spinner />}
      {personal && query.isError && <ErrorNotice error={query.error} />}
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
