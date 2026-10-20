"use client";
import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useLocale, useTranslations } from "next-intl";
import { FlaskConical, Play, Download, X, ArrowRight } from "lucide-react";
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
];

export function ResearchPanel({ user }: { user: User }) {
  const t = useTranslations("Research");
  const locale = useLocale();
  const client = useQueryClient();
  const allowed = user.role === "admin";
  const [configs, setConfigs] = useState([
    "fixture-reference",
    "fixture-small",
  ]);
  const [strategies, setStrategies] = useState<Strategy[]>(policies);
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
  const [error, setError] = useState<unknown>();
  const options = useQuery({
    queryKey: ["research-configs", user.id],
    enabled: allowed,
    queryFn: async () => unwrap(await api.GET("/v1/research/configs")),
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
  const run = useQuery({
    queryKey: ["research-run", user.id, selected],
    enabled: allowed && !!selected,
    refetchInterval: (query) =>
      ["pending", "running"].includes(query.state.data?.status ?? "")
        ? 1000
        : false,
    queryFn: async () =>
      unwrap(
        await api.GET("/v1/research/runs/{run_id}", {
          params: { path: { run_id: selected! } },
        }),
      ),
  });
  const trials = useQuery({
    queryKey: [
      "research-trials",
      user.id,
      selected,
      offset,
      run.data?.completed,
    ],
    enabled: allowed && !!selected,
    refetchInterval:
      run.data && ["pending", "running"].includes(run.data.status)
        ? 1500
        : false,
    queryFn: async () =>
      unwrap(
        await api.GET("/v1/research/runs/{run_id}/trials", {
          params: { path: { run_id: selected! }, query: { offset, limit: 50 } },
        }),
      ),
  });
  const summary = useQuery({
    queryKey: ["research-summary", user.id, selected, run.data?.completed],
    enabled: allowed && !!selected,
    refetchInterval:
      run.data && ["pending", "running"].includes(run.data.status)
        ? 1500
        : false,
    queryFn: async () =>
      unwrap(
        await api.GET("/v1/research/runs/{run_id}/summary", {
          params: { path: { run_id: selected! } },
        }),
      ),
  });
  const active = runs.data?.some((r) =>
    ["pending", "running"].includes(r.status),
  );
  function reset() {
    setChecked(null);
    setError(undefined);
  }
  async function preflight() {
    setBusy(true);
    setError(undefined);
    try {
      const request: Request = {
        client_request_id: crypto.randomUUID(),
        suite_id: "huy-router-fixtures-v1",
        config_ids: configs,
        policies: strategies,
        seed,
        repeats,
        budget_usd: budget,
        execution_source: source,
      };
      const result = unwrap(
        await api.POST("/v1/research/preflight", { body: request }),
      );
      setChecked({ request, result });
    } catch (e) {
      setError(e);
    } finally {
      setBusy(false);
    }
  }
  async function start() {
    if (!checked) return;
    setBusy(true);
    setError(undefined);
    try {
      const created = unwrap(
        await api.POST("/v1/research/runs", { body: checked.request }),
      );
      setSelected(created.id);
      setOffset(0);
      setChecked(null);
      await client.invalidateQueries({ queryKey: ["research-runs", user.id] });
    } catch (e) {
      setError(e);
    } finally {
      setBusy(false);
    }
  }
  async function cancel() {
    if (!selected) return;
    setBusy(true);
    setError(undefined);
    try {
      unwrap(
        await api.POST("/v1/research/runs/{run_id}/cancel", {
          params: { path: { run_id: selected } },
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
    <section className="overview-page research-page">
      <header className="page-heading">
        <div>
          <span className="eyebrow">ROUTER LAB · V1</span>
          <h1>{t("title")}</h1>
          <p className="muted">{t("subtitle")}</p>
        </div>
        <FlaskConical size={30} aria-hidden="true" />
      </header>
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
      <div className="research-layout">
        <section className="research-config chart-card">
          <h2>{t("configure")}</h2>
          {options.isLoading && <Spinner />}
          <form
            onSubmit={(e) => {
              e.preventDefault();
              void preflight();
            }}
          >
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
                      ? ["fixture-reference", "fixture-small"]
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
            <fieldset disabled={busy}>
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
                      {m.context_window} ·{" "}
                      {m.structured_output ? "JSON" : "text"}
                    </small>
                  </span>
                </label>
              ))}
            </fieldset>
            <fieldset disabled={busy}>
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
                  <span>{p}</span>
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
            </div>
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
            <button
              className="button"
              disabled={busy || !configs.length || !strategies.length}
            >
              {busy ? <Spinner /> : <ArrowRight size={16} />}
              {t("preflight")}
            </button>
          </form>
          {checked && (
            <div className="research-preflight" role="status">
              <strong>
                {checked.result.trials} {t("trials")} · ≤{" "}
                {checked.result.max_calls} calls
              </strong>
              <p>
                {t("forecast")}: USD{" "}
                {checked.result.simulation_upper_usd ??
                  checked.result.live_upper_usd}
              </p>
              <p>{t(source === "simulation" ? "noCharge" : "paidWarning")}</p>
              <button
                className="button primary"
                disabled={busy || active}
                onClick={start}
              >
                <Play size={16} />
                {t(source === "simulation" ? "start" : "startLive")}
              </button>
            </div>
          )}
          {active && <p className="muted">{t("active")}</p>}
        </section>
        <section className="research-results">
          <section className="activity-panel">
            <header>
              <h2>{t("runs")}</h2>
            </header>
            {runs.isLoading ? (
              <Spinner />
            ) : !runs.data?.length ? (
              <p className="research-empty">{t("empty")}</p>
            ) : (
              <div className="research-run-list">
                {runs.data.map((r) => (
                  <button
                    key={r.id}
                    className={`research-run ${selected === r.id ? "selected" : ""}`}
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
            <div className="document-actions">
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
          </section>
          {run.data && (
            <>
              <section className="chart-card research-progress">
                <div>
                  <h2>
                    {t("statusLabel")}: {t(`status.${run.data.status}`)}{" "}
                    <small>{run.data.execution_source.toUpperCase()}</small>
                  </h2>
                  <p>
                    {run.data.completed}/{run.data.total} {t("trials")}
                  </p>
                </div>
                <progress
                  max={run.data.total}
                  value={run.data.completed}
                  aria-label={t("progress")}
                />
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
                {run.data.error_code && (
                  <p role="alert">{run.data.error_code}</p>
                )}
                {run.data.accounting && (
                  <div className="research-accounting">
                    <p>
                      {run.data.accounting.calls} calls · {t("knownCost")}: USD{" "}
                      {run.data.accounting.known_subtotal_usd ?? "—"} ·{" "}
                      {t("unknownCost")}: {run.data.accounting.unknown_calls}
                    </p>
                    {run.data.accounting.uncommitted_calls.map((item) => (
                      <button
                        className="button small"
                        key={item.call.call_id}
                        onClick={() => setTrace(item)}
                      >
                        {t("uncommitted")} · {item.call.call_id.slice(0, 8)}
                      </button>
                    ))}
                  </div>
                )}
                <div className="document-actions">
                  {(["csv", "jsonl"] as const).map((format) => (
                    <a
                      key={format}
                      className="button small"
                      href={`/api/v1/research/runs/${selected}/export?format=${format}`}
                    >
                      <Download size={14} />
                      {t("export")} {format.toUpperCase()}
                    </a>
                  ))}
                </div>
                <details>
                  <summary>{t("provenance")}</summary>
                  <pre>
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
              </section>
              <section className="chart-card">
                <h2>{t("routes")}</h2>
                {Object.entries(summary.data?.routes ?? {}).map(
                  ([id, count]) => (
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
                  ),
                )}
              </section>
              <section className="activity-panel">
                <header>
                  <h2>{t("compare")}</h2>
                </header>
                <div className="table-scroll">
                  <table>
                    <thead>
                      <tr>
                        <th>Policy</th>
                        <th>{t("trials")}</th>
                        <th>Calls</th>
                        <th>{t("functional")}</th>
                        <th>{t("errors")}</th>
                        <th>p50 / p95 ms</th>
                        <th>{t("forecast")} USD</th>
                        <th>{t("calculatedCost")} USD</th>
                      </tr>
                    </thead>
                    <tbody>
                      {summary.data?.policies.map((p) => (
                        <tr key={p.policy}>
                          <td>{p.policy}</td>
                          <td>{p.trials}</td>
                          <td>{p.calls}</td>
                          <td>
                            {p.functional_passes}/{p.trials}
                          </td>
                          <td>{p.errors}</td>
                          <td>
                            {formatMetric(p.p50_ms, locale)} /{" "}
                            {formatMetric(p.p95_ms, locale)}
                          </td>
                          <td>{p.simulation_upper_usd ?? "\u2014"}</td>
                          <td>{p.calculated_usd ?? "\u2014"}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
                <p className="analytics-retention">
                  {t(
                    run.data.execution_source === "simulation"
                      ? "localTiming"
                      : "liveTiming",
                  )}
                </p>
              </section>
              <section className="activity-panel">
                <header>
                  <h2>{t("trialDetails")}</h2>
                </header>
                <div className="table-scroll">
                  <table>
                    <thead>
                      <tr>
                        <th>Case</th>
                        <th>Policy</th>
                        <th>Route</th>
                        <th>{t("outcome")}</th>
                        <th>Trace</th>
                      </tr>
                    </thead>
                    <tbody>
                      {trials.data?.map((row) => (
                        <tr key={row.id}>
                          <td>
                            {row.case_id} · {row.repeat + 1}
                          </td>
                          <td>{row.policy}</td>
                          <td>{row.route?.config_id ?? "—"}</td>
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
                <div className="document-actions">
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
              </section>
            </>
          )}
        </section>
      </div>
      <Drawer
        open={!!trace}
        onOpenChange={(open) => {
          if (!open) setTrace(null);
        }}
        title={t("trace")}
        description={t("honest")}
      >
        <pre className="research-trace">{JSON.stringify(trace, null, 2)}</pre>
      </Drawer>
    </section>
  );
}
