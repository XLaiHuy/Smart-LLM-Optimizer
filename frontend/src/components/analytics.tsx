"use client";
import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useLocale, useTranslations } from "next-intl";
import { Download, Activity, Coins, Layers, Clock3 } from "lucide-react";
import type { components } from "@/lib/generated/api";
import { api, unwrap, type User } from "@/lib/api";
import { formatCost, formatMetric } from "@/lib/format";
import { ErrorNotice, Spinner } from "./ui";
type Bucket = components["schemas"]["MetricBucket"];

function LineChart({
  title,
  rows,
  field,
  locale,
}: {
  title: string;
  rows: Bucket[];
  field: "input_tokens" | "usd" | "p50_ms";
  locale: string;
}) {
  const values = rows.map((row) =>
    row[field] === null ? null : Number(row[field]),
  );
  const known = values.filter((v): v is number => v !== null);
  const max = Math.max(...known, 1e-9);
  return (
    <article className="chart-card">
      <h3>{title}</h3>
      {known.length ? (
        <>
          <div className="chart-range">
            {new Intl.NumberFormat(locale, {
              maximumSignificantDigits: 4,
            }).format(max)}
          </div>
          <svg
            viewBox="0 0 440 140"
            role="img"
            aria-label={title}
            className="usage-chart"
          >
            <line x1="12" y1="125" x2="428" y2="125" stroke="var(--line)" />
            {[0, 0.5, 1].map((v) => (
              <line
                key={v}
                x1="12"
                y1={125 - v * 110}
                x2="428"
                y2={125 - v * 110}
                stroke="var(--line)"
                strokeDasharray="3 5"
              />
            ))}
            {values.map((v, i) => {
              if (v === null) return null;
              const x = 12 + (i * 416) / Math.max(values.length - 1, 1);
              const y = 125 - (v / max) * 110;
              const previous = values[i - 1];
              return (
                <g key={i}>
                  {previous != null && (
                    <line
                      x1={12 + ((i - 1) * 416) / Math.max(values.length - 1, 1)}
                      y1={125 - (previous / max) * 110}
                      x2={x}
                      y2={y}
                      stroke="#034EA2"
                      strokeWidth="2"
                    />
                  )}
                  <circle cx={x} cy={y} r="3" fill="#034EA2">
                    <title>
                      {rows[i].key}: {v}
                    </title>
                  </circle>
                </g>
              );
            })}
          </svg>
          <div className="chart-dates">
            <span>{rows[0]?.key}</span>
            <span>{rows.at(-1)?.key}</span>
          </div>
        </>
      ) : (
        <p className="chart-empty">?</p>
      )}
    </article>
  );
}
function QuotaRow({ user }: { user: components["schemas"]["AdminUser"] }) {
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
          {user.role} · {t("reserved")}: ${user.reserved_usd} · used $
          {user.settled_usd}
        </small>
      </div>
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
export function AnalyticsPanel({ user }: { user: User }) {
  const t = useTranslations("MVP");
  const locale = useLocale();
  const [project, setProject] = useState(false);
  const [source, setSource] = useState<"mock" | "live" | undefined>();
  const [period, setPeriod] = useState("week");
  const [start, setStart] = useState("");
  const [end, setEnd] = useState("");
  const [offset, setOffset] = useState(0);
  const today = new Intl.DateTimeFormat("en-CA", {
    timeZone: "Asia/Ho_Chi_Minh",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).format(new Date());
  const from =
    period === "custom"
      ? start || today
      : new Date(
          Date.parse(today + "T12:00:00Z") -
            (period === "today" ? 0 : period === "month" ? 29 : 6) * 86400000,
        )
          .toISOString()
          .slice(0, 10);
  const to = period === "custom" ? end || today : today;
  const query = useQuery({
    queryKey: ["usage", user.id, from, to, project, source],
    queryFn: async () =>
      unwrap(
        await api.GET("/v1/usage", {
          params: { query: { start: from, end: to, project, source } },
        }),
      ),
  });
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
  const data = query.data;
  const metric = (value: number | null | undefined, unit = "") =>
    formatMetric(value, locale, unit) ?? "—";
  const money = (value: string | null | undefined) =>
    formatCost(value, locale) ?? "—";
  function table(rows: Bucket[], first: string) {
    return (
      <div className="table-scroll">
        <table>
          <thead>
            <tr>
              <th>{first}</th>
              <th>{t("calls")}</th>
              <th>{t("input")}</th>
              <th>{t("output")}</th>
              <th>{t("cost")}</th>
              <th>{t("unknownCalls")}</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <tr key={row.key}>
                <td className="metric-key">
                  {t.has(row.key) ? t(row.key) : row.key}
                </td>
                <td>{row.calls}</td>
                <td>{metric(row.input_tokens)}</td>
                <td>{metric(row.output_tokens)}</td>
                <td
                  title={`${t("knownSubtotal")}: ${money(row.known_subtotal_usd)}`}
                >
                  {money(row.usd)}
                </td>
                <td>{row.unknown_calls}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    );
  }
  return (
    <div className="analytics-panel">
      <header className="page-heading">
        <div>
          <p className="eyebrow">SMART LLM / ANALYTICS</p>
          <h1>{t("activity")}</h1>
          <p className="muted">{t("activityHint")}</p>
        </div>
        <span className="mock-badge">
          {data?.execution_source.toUpperCase() || "—"}
        </span>
      </header>
      <div className="analytics-filters">
        <select
          aria-label={t("dataSource")}
          value={source ?? "current"}
          onChange={(e) =>
            setSource(
              e.target.value === "current"
                ? undefined
                : (e.target.value as "mock" | "live"),
            )
          }
        >
          <option value="current">{t("currentMode")}</option>
          <option value="mock">MOCK</option>
          <option value="live">LIVE</option>
        </select>
        {user.role === "admin" && (
          <select
            aria-label={t("project")}
            value={project ? "project" : "personal"}
            onChange={(e) => setProject(e.target.value === "project")}
          >
            <option value="personal">{t("personal")}</option>
            <option value="project">{t("project")}</option>
          </select>
        )}
        <select
          aria-label={t("day")}
          value={period}
          onChange={(e) => setPeriod(e.target.value)}
        >
          {["today", "week", "month", "custom"].map((p) => (
            <option key={p} value={p}>
              {t(p)}
            </option>
          ))}
        </select>
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
        <span className="muted">Asia/Ho_Chi_Minh · USD</span>
        {["json", "csv"].map((format) => (
          <a
            key={format}
            className="button small"
            href={`/api/v1/usage/export?start=${from}&end=${to}&project=${project}&source=${source ?? data?.execution_source ?? "mock"}&format=${format}`}
          >
            <Download size={14} />
            {t(format === "json" ? "exportJson" : "exportCsv")}
          </a>
        ))}
      </div>
      {query.isLoading && <Spinner />}
      {query.isError && <ErrorNotice error={query.error} />}
      {data && (
        <>
          <div className="stats-grid">
            {[
              {
                label: t("input"),
                value: metric(data.totals.input_tokens),
                Icon: Layers,
              },
              {
                label: t("output"),
                value: metric(data.totals.output_tokens),
                Icon: Activity,
              },
              { label: t("cost"), value: money(data.totals.usd), Icon: Coins },
              {
                label: t("available"),
                value: money(data.available_usd),
                Icon: Coins,
              },
              {
                label: t("requests"),
                value: metric(data.requests),
                Icon: Activity,
              },
              {
                label: t("unknownCalls"),
                value: metric(data.totals.unknown_calls),
                Icon: Layers,
              },
              {
                label: t("p50"),
                value: metric(data.totals.p50_ms, " ms"),
                Icon: Clock3,
              },
              {
                label: t("p95"),
                value: metric(data.totals.p95_ms, " ms"),
                Icon: Clock3,
              },
            ].map(({ label, value, Icon }) => (
              <article className="stat" key={label}>
                <div>
                  <span>{label}</span>
                  <Icon size={17} />
                </div>
                <strong>{value}</strong>
                <small>
                  {data.execution_source.toUpperCase()} ·{" "}
                  {data.totals.timing_samples ?? 0} {t("measuredCalls")}
                </small>
              </article>
            ))}
          </div>
          <div className="budget-strip">
            <span>
              {t("reserved")}: <strong>{money(data.reserved_usd)}</strong>
            </span>
            <span>
              {t("projectAvailable")}:{" "}
              <strong>{money(data.project_available_usd)}</strong>
            </span>
            <span>
              {t("knownSubtotal")}:{" "}
              <strong>{money(data.totals.known_subtotal_usd)}</strong>
            </span>
          </div>
          {data.totals.input_tokens === null && (
            <p className="muted">{t("noData")}</p>
          )}
          <div className="chart-grid">
            <LineChart
              title={`${t("dailyTokens")} · ${t("input")}`}
              rows={data.daily}
              field="input_tokens"
              locale={locale}
            />
            <LineChart
              title={t("dailyCost")}
              rows={data.daily}
              field="usd"
              locale={locale}
            />
            <LineChart
              title={t("latencyChart")}
              rows={data.daily}
              field="p50_ms"
              locale={locale}
            />
          </div>
          <article className="chart-card model-cost-chart">
            <h3>{t("modelCosts")}</h3>
            {data.models.some((row) => row.usd !== null) ? (
              data.models
                .filter((row) => row.usd !== null)
                .map((row) => (
                  <div className="cost-bar-row" key={row.key}>
                    <span>{row.key}</span>
                    <meter
                      min={0}
                      max={Math.max(
                        ...data.models.map((r) => Number(r.usd ?? 0)),
                        0.000000001,
                      )}
                      value={Number(row.usd)}
                      aria-label={`${row.key} USD`}
                    />
                    <strong>{money(row.usd)}</strong>
                  </div>
                ))
            ) : (
              <p className="muted">{t("noData")}</p>
            )}
          </article>
          <section className="activity-panel">
            <header>
              <h2>{t("modelCosts")}</h2>
            </header>
            {table(data.models, t("model"))}
          </section>
          <details className="activity-panel">
            <summary>{t("day")}</summary>
            {table(data.daily, t("day"))}
          </details>
          <details className="activity-panel">
            <summary>{t("category")}</summary>
            {table(data.categories, t("category"))}
          </details>
          <details className="activity-panel">
            <summary>{t("session")}</summary>
            {table(data.sessions, t("session"))}
          </details>
          <p className="analytics-retention">{t("retention")}</p>
          {!!data.totals.reconciled_calls && (
            <p className="analytics-retention">
              {t("billingCorrections", { count: data.totals.reconciled_calls })}
            </p>
          )}
        </>
      )}
      {user.role === "admin" && project && (
        <section className="activity-panel admin-panel">
          <header>
            <h2>{t("users")}</h2>
          </header>
          {users.isLoading && <Spinner />}
          {users.isError && <ErrorNotice error={users.error} />}{" "}
          {users.data?.map((row) => (
            <QuotaRow user={row} key={row.id} />
          ))}
          <div className="document-actions">
            <button
              className="button small"
              disabled={!offset}
              onClick={() => setOffset(Math.max(0, offset - 20))}
            >
              {t("previous")}
            </button>
            <button
              className="button small"
              disabled={(users.data?.length || 0) < 20}
              onClick={() => setOffset(offset + 20)}
            >
              {t("next")}
            </button>
          </div>
        </section>
      )}
    </div>
  );
}
