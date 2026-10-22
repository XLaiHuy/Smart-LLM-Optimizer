"use client";
import { useRef, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useLocale, useTranslations } from "next-intl";
import { Download, X, Zap, SlidersHorizontal, ChevronDown } from "lucide-react";
import { api, unwrap, type User } from "@/lib/api";
import type { components } from "@/lib/generated/api";
import { formatMetric } from "@/lib/format";
import { Drawer, ErrorNotice, Spinner } from "./ui";

type Request = components["schemas"]["ResearchRequest-Input"];
type Preflight = components["schemas"]["ResearchPreflight"];
type Trial = components["schemas"]["TrialResult"];
type Strategy = NonNullable<Request["policies"]>[number];
const policies: Strategy[] = [
  "fixed_reference",
  "fixed_candidate",
  "cheapest_feasible",
  "random_feasible",
  "rule_guarded",
  "ml_router",
  "ml_multi_model",
];

function getPolicyLabel(
  policy: string,
  t: ReturnType<typeof useTranslations<"Research">>,
): string {
  if (policy.startsWith("fixed_candidate:")) {
    const candidateId = policy.slice("fixed_candidate:".length);
    const base = t.has("policyNames.fixed_candidate")
      ? t("policyNames.fixed_candidate")
      : "Fixed candidate";
    return `${base} (${candidateId})`;
  }
  return t.has(`policyNames.${policy}`) ? t(`policyNames.${policy}`) : policy;
}

export function ResearchPanel({
  user,
  routerEnabled = true,
  onToggleRouter,
  modules,
}: {
  user: User;
  routerEnabled?: boolean;
  onToggleRouter?: (enabled: boolean) => void;
  modules?: Array<{
    id: string;
    implemented: boolean;
    status: string;
  }>;
}) {
  const t = useTranslations("Research");
  const tLab = useTranslations("OptimizerLab");
  const locale = useLocale();
  const client = useQueryClient();
  const allowed = user.role === "admin";
  const [sampleSize, setSampleSize] = useState<"50" | "200" | "600">("200");
  const [suite, setSuite] = useState<NonNullable<Request["suite_id"]>>(
    "huy-router-fixtures-v2",
  );
  const [configs, setConfigs] = useState([
    "fixture-reference",
    "fixture-small",
    "fixture-medium",
  ]);
  const [strategies, setStrategies] = useState<Strategy[]>(
    policies.filter((p) => p !== "ml_router" && p !== "ml_multi_model"),
  );
  const [seed, setSeed] = useState(42);
  const [repeats, setRepeats] = useState(1);
  const [budget, setBudget] = useState("1");
  const [source, setSource] = useState<"simulation" | "live">("simulation");
  const [checked, setChecked] = useState<{
    request: Request;
    result: Preflight;
  } | null>(null);
  const [selected, setSelected] = useState<string | null>(null);
  const [offset, setOffset] = useState(0);
  const [runsOffset, setRunsOffset] = useState(0);
  const [trace, setTrace] = useState<
    Trial | components["schemas"]["UncommittedCall"] | null
  >(null);
  const [busy, setBusy] = useState(false);
  const submitting = useRef(false);
  const pendingRequest = useRef<Request | null>(null);
  const [error, setError] = useState<unknown>();
  const options = useQuery({
    queryKey: ["research-configs", user.id, suite],
    enabled: allowed,
    queryFn: async () =>
      unwrap(
        await api.GET("/v1/research/configs", {
          params: { query: { suite_id: suite } },
        }),
      ),
  });
  const runs = useQuery({
    queryKey: ["research-runs", user.id, runsOffset],
    enabled: allowed,
    refetchInterval: (query) =>
      query.state.data?.some((r) => ["pending", "running"].includes(r.status))
        ? 1500
        : false,
    queryFn: async () =>
      unwrap(
        await api.GET("/v1/research/runs", {
          params: { query: { offset: runsOffset, limit: 10 } },
        }),
      ),
  });
  const activeSelected = selected;
  const run = useQuery({
    queryKey: ["research-run", user.id, activeSelected],
    enabled: allowed && !!activeSelected,
    refetchInterval: (query) =>
      ["pending", "running"].includes(query.state.data?.status ?? "")
        ? 1000
        : false,
    queryFn: async () =>
      unwrap(
        await api.GET("/v1/research/runs/{run_id}", {
          params: { path: { run_id: activeSelected! } },
        }),
      ),
  });
  const trials = useQuery({
    queryKey: ["research-trials", user.id, activeSelected, offset],
    enabled: allowed && !!activeSelected,
    placeholderData: (previousData) => previousData,
    refetchInterval:
      run.data && ["pending", "running"].includes(run.data.status)
        ? 1500
        : false,
    queryFn: async () =>
      unwrap(
        await api.GET("/v1/research/runs/{run_id}/trials", {
          params: {
            path: { run_id: activeSelected! },
            query: { offset, limit: 50 },
          },
        }),
      ),
  });
  const summary = useQuery({
    queryKey: ["research-summary", user.id, activeSelected],
    enabled: allowed && !!activeSelected,
    placeholderData: (previousData) => previousData,
    refetchInterval:
      run.data && ["pending", "running"].includes(run.data.status)
        ? 1500
        : false,
    queryFn: async () =>
      unwrap(
        await api.GET("/v1/research/runs/{run_id}/summary", {
          params: { path: { run_id: activeSelected! } },
        }),
      ),
  });
  const active = runs.data?.some((r) =>
    ["pending", "running"].includes(r.status),
  );

  const baselinePolicy = summary.data?.policies.find(
    (p) => p.policy === "fixed_reference",
  );
  const optimizedPolicy =
    summary.data?.policies.find((p) => p.policy === "ml_router") ??
    summary.data?.policies.find((p) => p.policy === "rule_guarded") ??
    summary.data?.policies.find((p) => p.policy !== "fixed_reference");

  const baselineCost = parseFloat(
    baselinePolicy?.calculated_usd ||
      baselinePolicy?.simulation_upper_usd ||
      "0",
  );
  const optCost = parseFloat(
    optimizedPolicy?.calculated_usd ||
      optimizedPolicy?.simulation_upper_usd ||
      "0",
  );
  const maxCost = Math.max(baselineCost, optCost, 0.0001);

  const costSavingsPct =
    baselineCost > 0 && optCost < baselineCost
      ? Math.round(((baselineCost - optCost) / baselineCost) * 100)
      : 0;

  const baselineLat = baselinePolicy?.p50_ms ?? 0;
  const optLat = optimizedPolicy?.p50_ms ?? 0;
  const maxLat = Math.max(baselineLat, optLat, 1);

  const latSavingsPct =
    baselineLat > 0 && optLat < baselineLat
      ? Math.round(((baselineLat - optLat) / baselineLat) * 100)
      : 0;

  function reset() {
    setChecked(null);
    setSelected(null);
    pendingRequest.current = null;
    setError(undefined);
  }
  async function preflight() {
    if (submitting.current) return;
    submitting.current = true;
    setBusy(true);
    setError(undefined);
    try {
      const request: Request = pendingRequest.current ?? {
        client_request_id: crypto.randomUUID(),
        suite_id: suite,
        config_ids: configs,
        policies: routerEnabled ? strategies : ["fixed_reference"],
        seed,
        repeats,
        budget_usd: budget,
        execution_source: source,
      };
      pendingRequest.current = request;
      const result = unwrap(
        await api.POST("/v1/research/preflight", { body: request }),
      );
      setChecked({ request, result });
      const created = unwrap(
        await api.POST("/v1/research/runs", { body: request }),
      );
      setSelected(created.id);
      setOffset(0);
      pendingRequest.current = null;
      await client.invalidateQueries({ queryKey: ["research-runs", user.id] });
    } catch (e) {
      setError(e);
    } finally {
      submitting.current = false;
      setBusy(false);
    }
  }
  async function cancel() {
    if (!activeSelected) return;
    setBusy(true);
    setError(undefined);
    try {
      unwrap(
        await api.POST("/v1/research/runs/{run_id}/cancel", {
          params: { path: { run_id: activeSelected } },
        }),
      );
      await client.invalidateQueries({ queryKey: ["research-run", user.id] });
    } catch (e) {
      setError(e);
    } finally {
      setBusy(false);
    }
  }
  if (!allowed)
    return (
      <section className="overview-page">
        <h1>{t("forbidden")}</h1>
        <p>{t("adminOnly")}</p>
      </section>
    );
  return (
    <section className="research-page unified-research">
      <div className="research-notice">
        <strong>
          {t(source === "simulation" ? "simulation" : "livePilot")}
        </strong>
        <p>{t("honest")}</p>
      </div>
      {(error ||
        options.error ||
        runs.error ||
        run.error ||
        trials.error ||
        summary.error) && (
        <ErrorNotice
          error={
            error ||
            options.error ||
            runs.error ||
            run.error ||
            trials.error ||
            summary.error
          }
        />
      )}

      {/* UNIFIED CONTROL CENTER */}
      <section
        className="chart-card lab-hero-control research-config"
        style={{ padding: 24 }}
      >
        {/* Module switches */}
        {modules && (
          <div>
            <h2 style={{ fontSize: 16, marginBottom: 12 }}>
              {tLab("modules")}
            </h2>
            <div className="lab-modules">
              {modules.map((m) => (
                <label
                  key={m.id}
                  className={`lab-module ${m.implemented ? "" : "unavailable"}`}
                >
                  <span className="lab-module-top">
                    <SlidersHorizontal size={19} />
                    <input
                      type="checkbox"
                      role="switch"
                      aria-label={tLab(`${m.id}Title`)}
                      checked={m.id === "router" && routerEnabled}
                      disabled={!m.implemented || busy}
                      onChange={(e) => onToggleRouter?.(e.target.checked)}
                    />
                  </span>
                  <strong>{tLab(`${m.id}Title`)}</strong>
                  <small>{tLab(`${m.id}Owner`)}</small>
                  <p>{tLab(`${m.id}Hint`)}</p>
                  <span className="lab-status">{tLab(m.status)}</span>
                </label>
              ))}
            </div>
          </div>
        )}

        {/* Sample size quick-select */}
        <div style={{ marginTop: 20 }}>
          <h2 style={{ fontSize: 16, marginBottom: 12 }}>{tLab("dataset")}</h2>
          <div className="lab-sizes" role="group" aria-label={tLab("dataset")}>
            <button
              type="button"
              className={`button ${sampleSize === "50" ? "active" : ""}`}
              aria-pressed={sampleSize === "50"}
              disabled={busy}
              onClick={() => {
                setSampleSize("50");
                setSuite("huy-router-fixtures-v1");
                setConfigs(["fixture-reference", "fixture-small"]);
                setRepeats(1);
                reset();
              }}
            >
              <strong>50 {tLab("samples")}</strong>
              <span>{tLab("size50")}</span>
            </button>
            <button
              type="button"
              className={`button ${sampleSize === "200" ? "active" : ""}`}
              aria-pressed={sampleSize === "200"}
              disabled={busy}
              onClick={() => {
                setSampleSize("200");
                setSuite("huy-router-fixtures-v2");
                setConfigs([
                  "fixture-reference",
                  "fixture-small",
                  "fixture-medium",
                ]);
                setRepeats(1);
                reset();
              }}
            >
              <strong>200 {tLab("samples")}</strong>
              <span>{tLab("size200")}</span>
            </button>
            <button
              type="button"
              className={`button ${sampleSize === "600" ? "active" : ""}`}
              aria-pressed={sampleSize === "600"}
              disabled={busy}
              onClick={() => {
                setSampleSize("600");
                setSuite("huy-router-fixtures-v2");
                setConfigs([
                  "fixture-reference",
                  "fixture-small",
                  "fixture-medium",
                ]);
                setRepeats(3);
                reset();
              }}
            >
              <strong>600 {tLab("samples")}</strong>
              <span>{tLab("size600")}</span>
            </button>
          </div>
        </div>

        {/* SINGLE HERO RUN BUTTON */}
        <button
          type="button"
          className="button primary lab-hero-run-btn"
          disabled={
            busy ||
            active ||
            options.isLoading ||
            options.isError ||
            !configs.length ||
            (routerEnabled && !strategies.length)
          }
          onClick={() => void preflight()}
        >
          {busy ? <Spinner /> : <Zap size={20} />}
          <span>{busy ? tLab("running") : t("quickRun")}</span>
        </button>

        {checked && (
          <p
            className="muted"
            role="status"
            style={{ textAlign: "center", margin: "4px 0" }}
          >
            {checked.result.trials} {t("trials")} · {t("noCharge")}
          </p>
        )}
        {active && (
          <p className="muted" style={{ textAlign: "center", margin: "4px 0" }}>
            {t("active")}
          </p>
        )}

        {/* COLLAPSIBLE ADVANCED OPTIONS */}
        <details className="lab-accordion research-options">
          <summary>
            <span>
              ⚙️ {t("options")} ({t("source")}, {t("seed")}, {t("budget")},{" "}
              {t("policies")})
            </span>
            <ChevronDown size={16} />
          </summary>
          <div className="lab-accordion-content">
            <div className="research-inputs" style={{ marginBottom: 16 }}>
              <label className="research-budget">
                {t("source")}
                <select
                  value={source}
                  disabled={busy}
                  onChange={(e) => {
                    const next = e.target.value as "simulation" | "live";
                    reset();
                    setSource(next);
                    setConfigs(
                      next === "simulation"
                        ? suite === "huy-router-fixtures-v2"
                          ? [
                              "fixture-reference",
                              "fixture-small",
                              "fixture-medium",
                            ]
                          : ["fixture-reference", "fixture-small"]
                        : (options.data?.live_models ?? [])
                            .filter((m) => m.available)
                            .map((m) => m.config_id),
                    );
                  }}
                >
                  <option value="simulation">{t("simulation")}</option>
                  <option value="live" disabled={!options.data?.live_enabled}>
                    {t("livePilot")}
                    {!options.data?.live_enabled ? ` - ${t("disabled")}` : ""}
                  </option>
                </select>
              </label>

              <label>
                {t("suite")}
                <select
                  value={suite}
                  aria-label={t("suite")}
                  disabled={busy || source === "live"}
                  onChange={(e) => {
                    reset();
                    const next = e.target.value as NonNullable<
                      Request["suite_id"]
                    >;
                    setSuite(next);
                    setConfigs(
                      next === "huy-router-fixtures-v2"
                        ? [
                            "fixture-reference",
                            "fixture-small",
                            "fixture-medium",
                          ]
                        : ["fixture-reference", "fixture-small"],
                    );
                  }}
                >
                  <option value="huy-router-fixtures-v1">
                    {t("suitePair")}
                  </option>
                  <option value="huy-router-fixtures-v2">
                    {t("suiteThree")}
                  </option>
                </select>
              </label>
            </div>

            <fieldset disabled={busy} style={{ marginBottom: 16 }}>
              <legend>{t("models")}</legend>
              {(source === "simulation"
                ? options.data?.models
                : options.data?.live_models
              )?.map((m) => (
                <label className="research-choice" key={m.config_id}>
                  <input
                    type="checkbox"
                    disabled={
                      !m.available ||
                      m.config_id ===
                        (source === "simulation"
                          ? "fixture-reference"
                          : options.data?.live_reference_id)
                    }
                    checked={configs.includes(m.config_id)}
                    onChange={(e) => {
                      reset();
                      setConfigs(
                        e.target.checked
                          ? [...configs, m.config_id]
                          : configs.filter((id) => id !== m.config_id),
                      );
                    }}
                  />
                  <span>
                    <strong>{m.config_id}</strong>
                    <small>
                      {t.has(`modelNames.${m.config_id}`)
                        ? `${t(`modelNames.${m.config_id}`)} · `
                        : ""}
                      {m.context_window} ·{" "}
                      {t(
                        m.structured_output
                          ? "structuredAvailable"
                          : "textAvailable",
                      )}
                    </small>
                  </span>
                </label>
              ))}
            </fieldset>

            <fieldset disabled={busy} style={{ marginBottom: 16 }}>
              <legend>{t("policies")}</legend>
              {policies.map((p) => (
                <label className="research-choice" key={p}>
                  <input
                    type="checkbox"
                    checked={strategies.includes(p)}
                    onChange={(e) => {
                      reset();
                      setStrategies(
                        e.target.checked
                          ? [...strategies, p]
                          : strategies.filter((s) => s !== p),
                      );
                    }}
                  />
                  <span>
                    <strong>{t(`policyNames.${p}`)}</strong>
                    <small>{t(`policyHints.${p}`)}</small>
                  </span>
                </label>
              ))}
            </fieldset>

            <div className="research-inputs">
              <label>
                {t("seed")}
                <input
                  type="number"
                  disabled={busy}
                  min={0}
                  max={2147483647}
                  required
                  value={seed}
                  onChange={(e) => {
                    reset();
                    setSeed(e.target.valueAsNumber);
                  }}
                />
              </label>
              <label>
                {t("repeats")}
                <input
                  type="number"
                  disabled={busy}
                  min={1}
                  max={5}
                  required
                  value={repeats}
                  onChange={(e) => {
                    reset();
                    setRepeats(e.target.valueAsNumber);
                  }}
                />
              </label>
              <label className="research-budget">
                {t(source === "simulation" ? "budget" : "liveBudget")}
                <input
                  type="number"
                  disabled={busy}
                  min="0.01"
                  max="20"
                  step="0.01"
                  required
                  value={budget}
                  onChange={(e) => {
                    reset();
                    setBudget(e.target.value);
                  }}
                />
              </label>
            </div>
          </div>
        </details>
      </section>

      {/* RESULTS & COMPARISON SECTION */}
      {run.data && (
        <section
          className="chart-card research-progress research-results"
          style={{ marginTop: 24, padding: 24 }}
        >
          <div className="research-status-header">
            <div>
              <h2>
                {t("statusLabel")}: {t(`status.${run.data.status}`)}{" "}
                <small>
                  {t(
                    run.data.execution_source === "simulation"
                      ? "simulationShort"
                      : "livePilot",
                  )}
                </small>
              </h2>
              <p>
                {t("progressCount", {
                  done: run.data.completed,
                  total: run.data.total,
                })}
              </p>
            </div>
            {["pending", "running"].includes(run.data.status) && (
              <button
                className="button"
                disabled={busy || run.data.cancel_requested}
                onClick={cancel}
              >
                <X size={16} />
                {t("cancel")}
              </button>
            )}
          </div>
          <progress
            max={run.data.total}
            value={run.data.completed}
            aria-label={t("progress")}
          />

          {/* EXPORTS */}
          <details className="research-download" style={{ margin: "16px 0" }}>
            <summary style={{ width: "fit-content", cursor: "pointer" }}>
              {t("export")}
            </summary>
            <div className="document-actions" style={{ marginTop: 8 }}>
              {(["csv", "jsonl"] as const).map((format) => (
                <a
                  key={format}
                  className="button small"
                  href={`/api/v1/research/runs/${activeSelected}/export?format=${format}`}
                >
                  <Download size={14} />
                  {t("export")} {format.toUpperCase()}
                </a>
              ))}
            </div>
          </details>

          {/* 3 KPI CARDS */}
          {summary.data && summary.data.policies.length > 0 && (
            <div className="research-kpi-grid">
              <div className="research-kpi-card">
                <span className="kpi-label">{t("functional")}</span>
                <strong className="kpi-val success">
                  {summary.data.policies.reduce((a, b) => a + b.trials, 0) > 0
                    ? `${Math.round(
                        (summary.data.policies.reduce(
                          (a, b) => a + b.functional_passes,
                          0,
                        ) /
                          summary.data.policies.reduce(
                            (a, b) => a + b.trials,
                            0,
                          )) *
                          100,
                      )}%`
                    : "—"}
                </strong>
                <span className="kpi-sub">
                  {summary.data.policies.reduce(
                    (a, b) => a + b.functional_passes,
                    0,
                  )}
                  /{summary.data.policies.reduce((a, b) => a + b.trials, 0)}{" "}
                  {t("passedLabel")}
                </span>
              </div>
              <div className="research-kpi-card">
                <span className="kpi-label">{t("errors")}</span>
                <strong className="kpi-val">
                  {summary.data.policies.reduce((sum, p) => sum + p.errors, 0)}
                </strong>
                <span className="kpi-sub">{t("functionalHint")}</span>
              </div>
              <div className="research-kpi-card">
                <span className="kpi-label">{t("totalCalls")}</span>
                <strong className="kpi-val primary">
                  {summary.data.policies.reduce((a, b) => a + b.calls, 0)}{" "}
                  {t("callsUnit")}
                </strong>
                <span className="kpi-sub">
                  {t("policyCount", {
                    count: summary.data.policies.length,
                  })}
                </span>
              </div>
            </div>
          )}

          {/* VISUAL COMPARISON CHARTS (BASELINE vs OPTIMIZED) */}
          {summary.data && baselinePolicy && optimizedPolicy && (
            <div className="lab-charts-grid">
              <div className="lab-chart-card">
                <div className="lab-chart-title">{tLab("latency")}</div>
                <div className="lab-bar-row">
                  <span className="lab-bar-label">{tLab("baseline")}</span>
                  <div className="lab-bar-track">
                    <div
                      className="lab-bar-fill baseline"
                      style={{
                        width: `${Math.max(12, Math.round((baselineLat / maxLat) * 100))}%`,
                      }}
                    />
                  </div>
                  <span className="lab-bar-val">
                    {formatMetric(baselineLat, locale, " ms")}
                  </span>
                </div>
                <div className="lab-bar-row">
                  <span className="lab-bar-label">{tLab("optimized")}</span>
                  <div className="lab-bar-track">
                    <div
                      className="lab-bar-fill optimized"
                      style={{
                        width: `${Math.max(12, Math.round((optLat / maxLat) * 100))}%`,
                      }}
                    />
                  </div>
                  <span className="lab-bar-val">
                    {formatMetric(optLat, locale, " ms")}
                  </span>
                </div>
                {latSavingsPct > 0 && (
                  <span className="metric-badge good">
                    ⚡ -{latSavingsPct}% ms
                  </span>
                )}
              </div>

              <div className="lab-chart-card">
                <div className="lab-chart-title">{tLab("cost")}</div>
                <div className="lab-bar-row">
                  <span className="lab-bar-label">{tLab("baseline")}</span>
                  <div className="lab-bar-track">
                    <div
                      className="lab-bar-fill baseline"
                      style={{
                        width: `${Math.max(12, Math.round((baselineCost / maxCost) * 100))}%`,
                      }}
                    />
                  </div>
                  <span className="lab-bar-val">
                    ${baselineCost.toFixed(4)}
                  </span>
                </div>
                <div className="lab-bar-row">
                  <span className="lab-bar-label">{tLab("optimized")}</span>
                  <div className="lab-bar-track">
                    <div
                      className="lab-bar-fill optimized"
                      style={{
                        width: `${Math.max(12, Math.round((optCost / maxCost) * 100))}%`,
                      }}
                    />
                  </div>
                  <span className="lab-bar-val">${optCost.toFixed(4)}</span>
                </div>
                {costSavingsPct > 0 && (
                  <span className="metric-badge good">
                    ⚡ -{costSavingsPct}% USD
                  </span>
                )}
              </div>
            </div>
          )}

          {/* ROUTE DISTRIBUTION */}
          {summary.data?.routes &&
            Object.keys(summary.data.routes).length > 0 && (
              <div className="lab-chart-card" style={{ marginTop: 20 }}>
                <div className="lab-chart-title">{t("routes")}</div>
                {Object.entries(summary.data.routes).map(([id, count]) => (
                  <div className="research-route" key={id}>
                    <span>{id}</span>
                    <meter
                      min={0}
                      max={run.data!.completed || 1}
                      value={count}
                      aria-label={id}
                    />
                    <strong>{count}</strong>
                  </div>
                ))}
              </div>
            )}

          {/* POLICY COMPARISON TABLE */}
          {summary.data && (
            <div style={{ marginTop: 28 }}>
              <h3 style={{ fontSize: 15, marginBottom: 12 }}>{t("compare")}</h3>
              <div className="table-scroll">
                <table>
                  <thead>
                    <tr>
                      <th>Policy</th>
                      <th>{t("trials")}</th>
                      <th>Calls</th>
                      <th>{t("functional")}</th>
                      <th>{t("errors")}</th>
                      <th>{t("fallbackRate")}</th>
                      <th>p50 / p95 ms</th>
                      <th>{t("forecast")} USD</th>
                      <th>{t("calculatedCost")} USD</th>
                    </tr>
                  </thead>
                  <tbody>
                    {summary.data.policies.map((p) => (
                      <tr key={p.policy}>
                        <td>
                          <strong>{getPolicyLabel(p.policy, t)}</strong>
                        </td>
                        <td>{p.trials}</td>
                        <td>{p.calls}</td>
                        <td>
                          <span className="badge-pass">
                            {p.functional_passes}/{p.trials}
                          </span>
                        </td>
                        <td>
                          {p.errors > 0 ? (
                            <span className="badge-error">{p.errors}</span>
                          ) : (
                            "0"
                          )}
                        </td>
                        <td>
                          {p.fallback_rate == null
                            ? "—"
                            : `${formatMetric(p.fallback_rate * 100, locale)}% (${p.fallbacks})`}
                        </td>
                        <td>
                          {formatMetric(p.p50_ms, locale)} /{" "}
                          {formatMetric(p.p95_ms, locale)}
                        </td>
                        <td>{p.simulation_upper_usd ?? "—"}</td>
                        <td>{p.calculated_usd ?? "—"}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}

          {/* PREDICTOR FEATURE IMPORTANCES */}
          {summary.data?.predictor_importances &&
            summary.data.predictor_importances.length > 0 && (
              <details className="lab-accordion" style={{ marginTop: 20 }}>
                <summary
                  style={{
                    cursor: "pointer",
                    fontWeight: 500,
                    color: "var(--brand)",
                  }}
                >
                  <span>{t("featureImportance")}</span>
                  <ChevronDown size={16} />
                </summary>
                <div style={{ marginTop: 12 }}>
                  {summary.data.predictor_importances.map((predictor) => (
                    <div
                      className="research-predictor"
                      key={predictor.config_id}
                    >
                      <h3>{predictor.config_id}</h3>
                      {Object.entries(predictor.importances).map(
                        ([name, weight]) => (
                          <div className="research-feature-item" key={name}>
                            <span>
                              {t.has(`features.${name}`)
                                ? t(`features.${name}`)
                                : name}
                            </span>
                            <meter
                              min={0}
                              max={100}
                              value={Math.round(weight * 100)}
                              aria-label={`${predictor.config_id}: ${t.has(`features.${name}`) ? t(`features.${name}`) : name}`}
                            />
                            <strong>{Math.round(weight * 100)}%</strong>
                          </div>
                        ),
                      )}
                    </div>
                  ))}
                </div>
              </details>
            )}

          {/* COLLAPSIBLE DEEP TRIALS & RUN HISTORY */}
          <details className="research-case-details lab-accordion lab-accordion-details">
            <summary>
              <span>
                📋 {t("trialDetails")} ({run.data.completed} trials) &{" "}
                {t("runs")} ({runs.data?.length ?? 0})
              </span>
              <ChevronDown size={16} />
            </summary>
            <div className="lab-accordion-content">
              {/* RUNS LIST */}
              <div style={{ marginBottom: 24 }}>
                <h4 style={{ fontSize: 14, marginBottom: 8 }}>{t("runs")}</h4>
                {runs.isLoading ? (
                  <Spinner />
                ) : !runs.data?.length ? (
                  <p className="research-empty">{t("empty")}</p>
                ) : (
                  <div className="research-run-list">
                    {runs.data.map((r) => (
                      <button
                        key={r.id}
                        className={`research-run ${activeSelected === r.id ? "selected" : ""}`}
                        onClick={() => {
                          setSelected(r.id);
                          setOffset(0);
                        }}
                      >
                        <span>
                          <strong>
                            {new Intl.DateTimeFormat(locale, {
                              dateStyle: "short",
                              timeStyle: "short",
                            }).format(new Date(r.created_at))}
                          </strong>
                          <small>
                            {r.id.slice(0, 8)} · seed {r.request.seed}
                          </small>
                        </span>
                        <span>
                          {t(`status.${r.status}`)}
                          <small>
                            {r.completed}/{r.total}
                          </small>
                        </span>
                      </button>
                    ))}
                  </div>
                )}
                <div className="document-actions" style={{ marginTop: 8 }}>
                  <button
                    className="button small"
                    disabled={!runsOffset}
                    onClick={() => setRunsOffset(Math.max(0, runsOffset - 10))}
                  >
                    {t("previous")}
                  </button>
                  <button
                    className="button small"
                    disabled={(runs.data?.length ?? 0) < 10}
                    onClick={() => setRunsOffset(runsOffset + 10)}
                  >
                    {t("next")}
                  </button>
                </div>
              </div>

              {/* TRIALS TABLE */}
              <div style={{ marginBottom: 20 }}>
                <h4 style={{ fontSize: 14, marginBottom: 8 }}>
                  {t("trialDetails")}
                </h4>
                <div className="table-scroll">
                  <table>
                    <thead>
                      <tr>
                        <th>Case</th>
                        <th>Policy</th>
                        <th>Route</th>
                        <th>{t("mlScore")}</th>
                        <th>{t("mlThreshold")}</th>
                        <th>{t("outcome")}</th>
                        <th>Trace</th>
                      </tr>
                    </thead>
                    <tbody>
                      {trials.data?.map((row) => (
                        <tr key={row.id}>
                          <td>
                            <code>{row.case_id}</code> · {row.repeat + 1}
                          </td>
                          <td>{getPolicyLabel(row.policy, t)}</td>
                          <td>
                            <span className="route-chip">
                              {row.route?.config_id ?? "—"}
                            </span>
                          </td>
                          <td>
                            {row.route?.stages?.length
                              ? row.route.stages
                                  .map(
                                    (stage) =>
                                      `${stage.config_id}: ${stage.score == null ? stage.status : formatMetric(stage.score, locale)}`,
                                  )
                                  .join(" · ")
                              : row.route?.ml_score == null
                                ? "—"
                                : formatMetric(row.route.ml_score, locale)}
                          </td>
                          <td>
                            {row.route?.stages?.length
                              ? row.route.stages
                                  .map(
                                    (stage) =>
                                      `${stage.config_id}: ${stage.threshold == null ? "—" : formatMetric(stage.threshold, locale)}`,
                                  )
                                  .join(" · ")
                              : row.route?.calibrated_threshold == null
                                ? "—"
                                : formatMetric(
                                    row.route.calibrated_threshold,
                                    locale,
                                  )}
                          </td>
                          <td>
                            {row.error_code ??
                              (row.functional_pass ? t("pass") : t("mismatch"))}
                          </td>
                          <td>
                            <button
                              className="button small"
                              onClick={() => setTrace(row)}
                            >
                              {t("trace")}
                            </button>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
                <div className="document-actions" style={{ marginTop: 8 }}>
                  <button
                    className="button small"
                    disabled={!offset}
                    onClick={() => setOffset(Math.max(0, offset - 50))}
                  >
                    {t("previous")}
                  </button>
                  <span>
                    {offset + 1}–{offset + (trials.data?.length ?? 0)}
                  </span>
                  <button
                    className="button small"
                    disabled={offset + 50 >= run.data.completed}
                    onClick={() => setOffset(offset + 50)}
                  >
                    {t("next")}
                  </button>
                </div>
              </div>

              {/* PROVENANCE */}

              <details style={{ marginTop: 16 }}>
                <summary style={{ cursor: "pointer", color: "var(--brand)" }}>
                  {t("provenance")}
                </summary>
                <pre style={{ marginTop: 8 }}>
                  {JSON.stringify(
                    {
                      manifest: run.data.manifest_hash,
                      catalog: run.data.catalog_hash,
                      code: run.data.code_sha,
                      request: run.data.request,
                    },
                    null,
                    2,
                  )}
                </pre>
              </details>
            </div>
          </details>
        </section>
      )}
      <Drawer
        open={!!trace}
        onOpenChange={(open) => {
          if (!open) setTrace(null);
        }}
        title={t("trace")}
        description={t("honest")}
      >
        {trace && "case_id" in trace && (
          <p>
            {getPolicyLabel(trace.policy, t)} ·{" "}
            {trace.error_code ??
              (trace.functional_pass ? t("pass") : t("mismatch"))}
          </p>
        )}
        <details>
          <summary>{t("provenance")}</summary>
          <pre className="research-trace">{JSON.stringify(trace, null, 2)}</pre>
        </details>
      </Drawer>
    </section>
  );
}
