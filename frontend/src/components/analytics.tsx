"use client";
import { useState, useMemo } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useLocale, useTranslations } from "next-intl";
import {
  Download,
  Activity,
  Coins,
  Layers,
  Clock3,
  ArrowLeft,
  ChevronRight,
} from "lucide-react";
import type { components } from "@/lib/generated/api";
import { api, unwrap, type User } from "@/lib/api";
import { formatCost, formatMetric, knownTokenTotal } from "@/lib/format";
import { ErrorNotice, Spinner } from "./ui";
import { UsageChart } from "./usage-chart";
type Bucket = components["schemas"]["MetricBucket"];
function QuotaRow({
  user,
  onView,
}: {
  user: components["schemas"]["AdminUser"];
  onView: () => void;
}) {
  const t = useTranslations("MVP");
  const client = useQueryClient();
  const [quota, setQuota] = useState(user.quota_usd);
  const [reason, setReason] = useState("");
  const [error, setError] = useState<unknown>();
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  async function save() {
    setSaving(true);
    setError(undefined);
    setSaved(false);
    try {
      unwrap(
        await api.PATCH("/v1/admin/users/{user_id}/quota", {
          params: { path: { user_id: user.id } },
          body: { quota_usd: quota, reason },
        }),
      );
      setSaved(true);
      await client.invalidateQueries({ queryKey: ["admin-users"] });
      await client.invalidateQueries({ queryKey: ["usage"] });
    } catch (e) {
      setError(e);
    } finally {
      setSaving(false);
    }
  }
  return (
    <div className="quota-row">
      <div>
        <strong>{user.username}</strong>
        <small>
          {t(user.role)} · {t("reserved")}: ${user.reserved_usd} · {t("spent")}{" "}
          ${user.settled_usd}
        </small>
      </div>
      <button className="button small" onClick={onView}>
        {t("viewUsage")}
      </button>
      <label>
        {t("quota")}
        <input
          type="number"
          min="0.01"
          step="0.01"
          value={quota}
          onChange={(e) => setQuota(e.target.value)}
        />
      </label>
      <label>
        {t("reason")}
        <input
          minLength={3}
          maxLength={300}
          value={reason}
          onChange={(e) => setReason(e.target.value)}
        />
      </label>
      <button
        className="button small"
        disabled={saving || reason.trim().length < 3}
        onClick={() => void save()}
      >
        {saving ? <Spinner /> : t("save")}
      </button>
      {saved && <span role="status">{t("quotaSaved")}</span>}
      {error !== undefined && <ErrorNotice error={error} />}
    </div>
  );
}

export function AnalyticsPanel({
  user,
  onScopeChange,
}: {
  user: User;
  onScopeChange?: (personal: boolean) => void;
}) {
  const t = useTranslations("Insights");
  const m = useTranslations("MVP");
  const locale = useLocale();
  const [project, setProject] = useState(false);
  const [selectedUser, setSelectedUser] = useState<{
    id: string;
    name: string;
  } | null>(null);
  const [source, setSource] = useState<"mock" | "live" | undefined>();
  const [period, setPeriod] = useState("week");
  const [start, setStart] = useState("");
  const [end, setEnd] = useState("");
  const [model, setModel] = useState("");
  const [session, setSession] = useState("");
  const [offset, setOffset] = useState(0);
  const today = new Intl.DateTimeFormat("en-CA", {
    timeZone: "Asia/Ho_Chi_Minh",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).format(new Date());
  const todayDate = new Date(today + "T12:00:00Z");
  const from =
    period === "custom"
      ? start || today
      : period === "year"
        ? new Date(
            Date.UTC(
              todayDate.getUTCFullYear(),
              todayDate.getUTCMonth() - 11,
              1,
            ),
          )
            .toISOString()
            .slice(0, 10)
        : new Date(
            todayDate.getTime() -
              (period === "today" ? 0 : period === "month" ? 29 : 6) * 86400000,
          )
            .toISOString()
            .slice(0, 10);
  const to = period === "custom" ? end || today : today;
  const rangeInvalid =
    from > to || (Date.parse(to) - Date.parse(from)) / 86400000 > 365;
  async function fetchReport(filtered = false) {
    if (selectedUser)
      return unwrap(
        await api.GET("/v1/admin/users/{user_id}/usage", {
          params: {
            path: { user_id: selectedUser.id },
            query: {
              start: from,
              end: to,
              source,
              model_id: filtered && model ? model : undefined,
            },
          },
        }),
      );
    return unwrap(
      await api.GET("/v1/usage", {
        params: {
          query: {
            start: from,
            end: to,
            project,
            source,
            model_id: filtered && model ? model : undefined,
            session_id: filtered && session ? session : undefined,
          },
        },
      }),
    );
  }
  const options = useQuery({
    queryKey: ["usage", user.id, from, to, project, selectedUser?.id, source],
    queryFn: () => fetchReport(),
    enabled: !rangeInvalid,
  });
  const filtered = !!(model || session);
  const query = useQuery({
    queryKey: [
      "usage-filtered",
      user.id,
      from,
      to,
      project,
      selectedUser?.id,
      source,
      model,
      session,
    ],
    queryFn: () => fetchReport(true),
    enabled: filtered && !rangeInvalid,
  });
  const current = filtered ? query : options;
  const data = rangeInvalid ? undefined : current.data;
  const users = useQuery({
    queryKey: ["admin-users", user.id, offset],
    enabled: user.role === "admin" && project,
    queryFn: async () =>
      unwrap(
        await api.GET("/v1/admin/users", {
          params: { query: { offset, limit: 20 } },
        }),
      ),
  });
  const impact = useQuery({
    queryKey: ["benchmark-impact", user.id, selectedUser?.id, from, to],
    enabled:
      user.role === "admin" &&
      project &&
      !rangeInvalid &&
      options.data?.execution_source === "live",
    queryFn: async () =>
      unwrap(
        await api.GET("/v1/admin/benchmark-impact", {
          params: {
            query: { start: from, end: to, user_id: selectedUser?.id },
          },
        }),
      ),
  });
  const userSessions = useQuery({
    queryKey: ["analytics-sessions", user.id],
    queryFn: async () =>
      unwrap(
        await api.GET("/v1/sessions", {
          params: { query: { offset: 0, limit: 100 } },
        }),
      ),
  });
  const sessionList = useMemo(() => {
    if (!userSessions.data) return [];
    if (Array.isArray(userSessions.data)) return userSessions.data;
    if ("pages" in (userSessions.data as any) && Array.isArray((userSessions.data as any).pages)) {
      return (userSessions.data as any).pages.flat();
    }
    if ("sessions" in (userSessions.data as any) && Array.isArray((userSessions.data as any).sessions)) {
      return (userSessions.data as any).sessions;
    }
    return [];
  }, [userSessions.data]);
  const sessionMap = useMemo(
    () => new Map<string, string>(sessionList.map((s: any) => [String(s.id), String(s.title)])),
    [sessionList],
  );
  const getRowTitle = (key: string, isSession: boolean) => {
    if (isSession) {
      if (key === "research")
        return locale === "vi"
          ? "Đo lường Nghiên cứu (Router Lab)"
          : "Router Lab Research";
      if (sessionMap.has(key)) return sessionMap.get(key);
      return key.length > 10
        ? (locale === "vi" ? `Hội thoại #${key.slice(0, 8)}` : `Chat #${key.slice(0, 8)}`)
        : key;
    }
    return m.has(key) ? m(key) : key;
  };

  const metric = (v: number | null | undefined, unit = "") =>
    formatMetric(v, locale, unit) ?? t("noData");
  const money = (v: string | null | undefined) =>
    formatCost(v, locale) ?? t("noData");
  function scope(value: boolean) {
    setProject(value);
    setSelectedUser(null);
    setModel("");
    setSession("");
    onScopeChange?.(!value);
  }
  const exportParams = new URLSearchParams({
    start: from,
    end: to,
    project: String(project && !selectedUser),
    source: source ?? data?.execution_source ?? "mock",
  });
  if (selectedUser) exportParams.set("user_id", selectedUser.id);
  if (model) exportParams.set("model_id", model);
  if (session) exportParams.set("session_id", session);
  const quotaRatio = data
    ? Math.min(
        100,
        ((Number(data.settled_usd) + Number(data.reserved_usd)) /
          Number(data.quota_usd)) *
          100,
      )
    : 0;
  function rows(items: Bucket[], dimension: string) {
    return (
      <div className="table-scroll">
        <table>
          <thead>
            <tr>
              <th>{dimension}</th>
              <th>{t("calls")}</th>
              <th>{t("input")}</th>
              <th>{t("output")}</th>
              <th>{t("cost")}</th>
            </tr>
          </thead>
          <tbody>
            {items.length ? (
              items.map((row) => (
                <tr key={row.key}>
                  <td className="metric-key">
                    {getRowTitle(row.key, dimension === t("conversation"))}
                  </td>
                  <td>{row.calls}</td>
                  <td>{metric(row.input_tokens)}</td>
                  <td>{metric(row.output_tokens)}</td>
                  <td
                    title={`${t("knownSubtotal")}: ${money(row.known_subtotal_usd)}`}
                  >
                    {money(row.usd)}
                  </td>
                </tr>
              ))
            ) : (
              <tr>
                <td colSpan={5}>{t("empty")}</td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    );
  }
  return (
    <section className="analytics-panel">
      <header className="page-heading insight-heading">
        <div>
          <p className="eyebrow">
            {t(project ? "adminEyebrow" : "personalEyebrow")}
          </p>
          <h1>
            {selectedUser
              ? t("userTitle", { name: selectedUser.name })
              : t(project ? "adminTitle" : "title")}
          </h1>
          <p className="muted">{t(project ? "adminHint" : "hint")}</p>
        </div>
        {user.role === "admin" && (
          <div className="scope-tabs" role="group" aria-label={t("scope")}>
            <button aria-pressed={!project} onClick={() => scope(false)}>
              {t("personal")}
            </button>
            <button aria-pressed={project} onClick={() => scope(true)}>
              {t("project")}
            </button>
          </div>
        )}
      </header>
      {selectedUser && (
        <button
          className="button small"
          onClick={() => {
            setSelectedUser(null);
            setModel("");
          }}
        >
          <ArrowLeft size={15} />
          {t("allUsers")}
        </button>
      )}
      <div className="insight-toolbar">
        <div className="period-tabs" role="group" aria-label={t("period")}>
          {["today", "week", "month", "year", "custom"].map((p) => (
            <button
              key={p}
              aria-pressed={period === p}
              onClick={() => {
                setPeriod(p);
                setModel("");
                setSession("");
              }}
            >
              {t(p)}
            </button>
          ))}
        </div>
        <label>
          {t("source")}
          <select
            value={source ?? "current"}
            onChange={(e) => {
              setSource(
                e.target.value === "current"
                  ? undefined
                  : (e.target.value as "mock" | "live"),
              );
              setModel("");
              setSession("");
            }}
          >
            <option value="current">{t("current")}</option>
            <option value="mock">{t("mock")}</option>
            <option value="live">{t("live")}</option>
          </select>
        </label>
      </div>
      <div className="insight-filters">
        {period === "custom" && (
          <>
            <label>
              {t("from")}
              <input
                type="date"
                value={start}
                onChange={(e) => setStart(e.target.value)}
              />
            </label>
            <label>
              {t("to")}
              <input
                type="date"
                value={end}
                onChange={(e) => setEnd(e.target.value)}
              />
            </label>
          </>
        )}
        <label>
          {t("model")}
          <select value={model} onChange={(e) => setModel(e.target.value)}>
            <option value="">{t("allModels")}</option>
            {options.data?.models.map((r) => (
              <option key={r.key} value={r.key}>
                {r.key}
              </option>
            ))}
          </select>
        </label>
        {!project && (
          <label>
            {t("conversation")}
            <select
              value={session}
              onChange={(e) => setSession(e.target.value)}
            >
              <option value="">{t("allConversations")}</option>
              {options.data?.sessions
                .filter((r) => r.key !== "research")
                .map((r) => (
                  <option key={r.key} value={r.key}>
                    {sessionMap.get(r.key)
                      ? sessionMap.get(r.key)!.length > 32
                        ? `${sessionMap.get(r.key)!.slice(0, 32)}...`
                        : sessionMap.get(r.key)
                      : (locale === "vi" ? `Phiên #${r.key.slice(0, 8)}` : `Session #${r.key.slice(0, 8)}`)}
                  </option>
                ))}
            </select>
          </label>
        )}
        <span className="muted insight-zone">{t("timezone")}</span>
        {data &&
          ["csv", "json"].map((format) => (
            <a
              key={format}
              className="button small"
              href={`/api/v1/usage/export?${exportParams}&format=${format}`}
            >
              <Download size={14} />
              {format.toUpperCase()}
            </a>
          ))}
      </div>
      {rangeInvalid && (
        <p role="alert" className="error-notice">
          {t("dateError")}
        </p>
      )}
      {current.isLoading && !rangeInvalid && (
        <div
          className="metric-skeleton"
          role="status"
          aria-label={t("loading")}
        >
          <Spinner />
          {t("loading")}
        </div>
      )}
      {current.isError && <ErrorNotice error={current.error} />}
      {data && (
        <>
          <p className="insight-source">
            <span className="mock-badge">{t(data.execution_source)}</span>{" "}
            {t("measuredOnly")}
          </p>
          <div className="stats-grid insight-stats">
            {[
              {
                label: t("cost"),
                value: money(data.totals.usd),
                Icon: Coins,
                note:
                  t("knownSubtotal") +
                  ": " +
                  money(data.totals.known_subtotal_usd),
              },
              {
                label: t("tokens"),
                value: metric(
                  knownTokenTotal(
                    data.totals.input_tokens,
                    data.totals.output_tokens,
                  ),
                ),
                Icon: Layers,
                note: `${t("input")}: ${metric(data.totals.input_tokens)} · ${t("output")}: ${metric(data.totals.output_tokens)}`,
              },
              {
                label: t("requests"),
                value: metric(data.requests),
                Icon: Activity,
                note: t("outcomes", {
                  success: data.succeeded,
                  failed: data.failed,
                }),
              },
              {
                label: t("remaining"),
                value: money(data.available_usd),
                Icon: Coins,
                note: t("quota") + ": " + money(data.quota_usd),
              },
              ...(project
                ? [
                    {
                      label: t("p50"),
                      value: metric(data.totals.p50_ms, " ms"),
                      Icon: Clock3,
                      note: t("timingSamples", {
                        count: data.totals.timing_samples,
                      }),
                    },
                    {
                      label: t("p95"),
                      value: metric(data.totals.p95_ms, " ms"),
                      Icon: Clock3,
                      note: t("callTiming"),
                    },
                    {
                      label: t("unknown"),
                      value: metric(data.totals.unknown_calls),
                      Icon: Layers,
                      note: t("unknownHint"),
                    },
                  ]
                : []),
            ].map(({ label, value, Icon, note }) => (
              <article className="stat" key={label}>
                <div>
                  <span>{label}</span>
                  <Icon size={18} />
                </div>
                <strong>{value}</strong>
                <small>{note}</small>
              </article>
            ))}
          </div>
          <section className="budget-card">
            <div>
              <h2>{t("budgetTitle")}</h2>
              <p>{t("lifetime")}</p>
            </div>
            <div className="budget-meter">
              <progress
                max={100}
                value={quotaRatio}
                aria-label={t("budgetTitle")}
              />
              <span>{metric(quotaRatio)}%</span>
            </div>
            <p>
              {t("reserved")}: {money(data.reserved_usd)} · {t("spent")}:{" "}
              {money(data.settled_usd)}
            </p>
            {quotaRatio >= 80 && (
              <p
                role="status"
                className={`budget-warning ${quotaRatio >= 100 ? "exhausted" : ""}`}
              >
                {t(quotaRatio >= 100 ? "budgetEmpty" : "budgetNear")}
              </p>
            )}
          </section>
          <div className="chart-grid insight-charts">
            <UsageChart
              title={t("tokensChart")}
              rows={data.timeseries}
              metric="tokens"
              granularity={data.granularity}
            />
            <UsageChart
              title={t("costChart")}
              rows={data.timeseries}
              metric="usd"
              granularity={data.granularity}
            />
            {project && (
              <UsageChart
                title={t("latencyChart")}
                rows={data.timeseries}
                metric="p50_ms"
                granularity={data.granularity}
              />
            )}
          </div>
          <section className="activity-panel">
            <header>
              <h2>{t("modelsTitle")}</h2>
            </header>
            {rows(data.models, t("model"))}
          </section>
          <details className="activity-panel">
            <summary>{t("categoriesTitle")}</summary>
            {rows(data.categories, t("category"))}
          </details>
          {!project && (
            <details className="activity-panel">
              <summary>{t("conversationsTitle")}</summary>
              {rows(data.sessions, t("conversation"))}
            </details>
          )}
          <p className="analytics-retention">{t("retention")}</p>
        </>
      )}
      {project && user.role === "admin" && (
        <>
          <section className="benchmark-impact activity-panel">
            <header>
              <h2>{t("impactTitle")}</h2>
            </header>
            {impact.isLoading && <Spinner />}
            {impact.isError && <ErrorNotice error={impact.error} />}
            <div className="impact-body">
              {data?.execution_source === "live" &&
              impact.data?.status === "available" ? (
                <>
                  <strong className="impact-amount">
                    {money(impact.data.estimated_savings_usd)}
                  </strong>
                  <p>{t("projectionHint")}</p>
                  <p>
                    {t("coverage", {
                      count: impact.data.matched_calls,
                      percent: metric((impact.data.coverage_ratio ?? 0) * 100),
                    })}
                  </p>
                  <p>
                    {t("benchmarkCost")}:{" "}
                    {money(impact.data.benchmark_baseline_usd)} →{" "}
                    {money(impact.data.benchmark_optimized_usd)}
                  </p>
                  <p>{impact.data.populations.join(" · ")}</p>
                  <p>{impact.data.limitations}</p>
                </>
              ) : (
                <>
                  <strong>{t("impactLocked")}</strong>
                  <p>
                    {t(
                      data?.execution_source === "mock"
                        ? "liveEstimateOnly"
                        : "impactHint",
                    )}
                  </p>
                  <small>
                    {impact.data?.reason && t.has(impact.data.reason)
                      ? t(impact.data.reason)
                      : t("impactLocked")}
                  </small>
                </>
              )}
            </div>
          </section>
          {!selectedUser && (
            <section className="activity-panel admin-panel">
              <header>
                <h2>{t("users")}</h2>
                <span className="muted">{t("privacy")}</span>
              </header>
              {users.isError && <ErrorNotice error={users.error} />}
              <div className="admin-user-list">
                {users.data?.map((row) => (
                  <QuotaRow
                    user={row}
                    key={row.id}
                    onView={() => {
                      setSelectedUser({ id: row.id, name: row.username });
                      setModel("");
                      setSession("");
                    }}
                  />
                ))}
              </div>
              <div className="document-actions">
                <button
                  className="button small"
                  disabled={!offset}
                  onClick={() => setOffset(Math.max(0, offset - 20))}
                >
                  {m("previous")}
                </button>
                <button
                  className="button small"
                  disabled={(users.data?.length ?? 0) < 20}
                  onClick={() => setOffset(offset + 20)}
                >
                  {m("next")}
                  <ChevronRight size={14} />
                </button>
              </div>
            </section>
          )}
        </>
      )}
    </section>
  );
}
