"use client";

import { useEffect, useRef, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useTranslations } from "next-intl";
import { api, unwrap, ApiError, type User } from "@/lib/api";
import type { components } from "@/lib/generated/api";
import { ErrorNotice } from "./ui";

type Request = components["schemas"]["TrainingRequest-Input"];
const stages = [
  "collect",
  "distill",
  "train",
  "evaluate",
  "import",
  "complete",
] as const;

export function RouterTraining({ user }: { user: User }) {
  const t = useTranslations("RouterTraining");
  const client = useQueryClient();
  const [mode, setMode] = useState<Request["mode"]>("cache");
  const [budget, setBudget] = useState("1");
  const [autoImport, setAutoImport] = useState(false);
  const [attention, setAttention] = useState(false);
  const [phase, setPhase] = useState<Request["phase"]>("full");
  const [selected, setSelected] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>();
  const submitting = useRef(false);
  const [pending, setPending] = useState<Request | null>(null);
  const info = useQuery({
    queryKey: ["router-training-info", user.id],
    queryFn: async () => unwrap(await api.GET("/v1/research/training")),
    retry: false,
  });
  const latest = useQuery({
    queryKey: ["router-training-latest", user.id],
    queryFn: async () => unwrap(await api.GET("/v1/research/training/latest")),
    retry: false,
  });
  const jobId = selected ?? latest.data?.id;
  const status = useQuery({
    queryKey: ["router-training-job", user.id, jobId],
    queryFn: async () =>
      unwrap(
        await api.GET("/v1/research/training/jobs/{job_id}", {
          params: { path: { job_id: jobId! } },
        }),
      ),
    enabled: !!jobId,
    refetchInterval: (query) =>
      query.state.data?.status === "running" ? 1500 : false,
    retry: false,
  });
  const job = status.data ?? (latest.data?.id === jobId ? latest.data : null);
  const running = job?.status === "running";
  const available =
    mode === "cache" ? info.data?.cache_available : info.data?.live_available;
  const pilot = info.data?.pilot ?? false;
  const validBudget = Number(budget) > 0 && Number(budget) <= (pilot ? 5 : 20);
  const completedStages = {
    collect: (job?.total ?? 0) > 0,
    distill: (job?.completed ?? 0) > 0,
    train: !!job?.artifact_hash,
    evaluate: !!job?.pilot_report?.attention,
    import: !!job?.imported,
    complete: job?.status === "succeeded",
  };
  const reviews = useQuery({
    queryKey: ["router-training-reviews", user.id, jobId],
    queryFn: async () =>
      unwrap(
        await api.GET("/v1/research/training/jobs/{job_id}/reviews", {
          params: { path: { job_id: jobId! } },
        }),
      ),
    enabled: !!jobId && pilot && !running,
    retry: false,
  });
  useEffect(() => {
    if (job?.imported) {
      void client.invalidateQueries({
        queryKey: ["research-configs", user.id],
      });
      void client.invalidateQueries({
        queryKey: ["router-training-info", user.id],
      });
    }
  }, [client, user.id, job?.id, job?.imported]);

  async function start() {
    if (submitting.current) return;
    submitting.current = true;
    setBusy(true);
    setError(undefined);
    const request = pending ?? {
      client_request_id: crypto.randomUUID(),
      mode,
      budget_usd: budget,
      hybrid: true,
      auto_import: autoImport,
      flash_attention: pilot || attention,
      phase,
      collection_batches: 1,
    };
    setPending(request);
    try {
      const result = unwrap(
        await api.POST("/v1/research/training/jobs", { body: request }),
      );
      setPending(null);
      client.setQueryData(["router-training-job", user.id, result.id], result);
      setSelected(result.id);
      await client.invalidateQueries({
        queryKey: ["router-training-latest", user.id],
      });
    } catch (e) {
      setError(e);
      if (e instanceof ApiError && e.status >= 400 && e.status < 500)
        setPending(null);
    } finally {
      submitting.current = false;
      setBusy(false);
    }
  }

  async function resume(nextPhase: "full" | "collect" | "train") {
    if (!jobId || submitting.current) return;
    submitting.current = true;
    setBusy(true);
    setError(undefined);
    try {
      const result = unwrap(
        await api.POST("/v1/research/training/jobs/{job_id}/resume", {
          params: { path: { job_id: jobId } },
          body: { phase: nextPhase },
        }),
      );
      client.setQueryData(["router-training-job", user.id, jobId], result);
      await client.invalidateQueries({
        queryKey: ["router-training-latest", user.id],
      });
    } catch (e) {
      setError(e);
    } finally {
      submitting.current = false;
      setBusy(false);
    }
  }

  async function importModel() {
    if (!jobId || submitting.current) return;
    submitting.current = true;
    setBusy(true);
    setError(undefined);
    try {
      const result = unwrap(
        await api.POST("/v1/research/training/jobs/{job_id}/import", {
          params: { path: { job_id: jobId } },
        }),
      );
      client.setQueryData(["router-training-job", user.id, jobId], result);
      await Promise.all([
        client.invalidateQueries({
          queryKey: ["router-training-info", user.id],
        }),
        client.invalidateQueries({ queryKey: ["research-configs", user.id] }),
      ]);
    } catch (e) {
      setError(e);
    } finally {
      submitting.current = false;
      setBusy(false);
    }
  }

  return (
    <section
      className="router-training"
      aria-labelledby="router-training-title"
    >
      <div>
        <p className="eyebrow">ROUTER TRAINING</p>
        <h2 id="router-training-title">{t("title")}</h2>
        <p>{t("intro")}</p>
      </div>
      {info.isError && <ErrorNotice error={info.error} />}
      {latest.isError && <ErrorNotice error={latest.error} />}
      {!info.isLoading && !info.data?.configured && (
        <p className="training-note">{t("setup")}</p>
      )}
      <div className="training-controls">
        <label>
          {t("source")}
          <select
            value={mode}
            disabled={busy || running || !!pending}
            onChange={(e) => setMode(e.target.value as Request["mode"])}
          >
            <option value="cache">{t("cache")}</option>
            <option value="live">{t("live")}</option>
          </select>
        </label>
        <label>
          {t("budget")}
          <input
            type="number"
            min="0.01"
            max={pilot ? "5" : "20"}
            step="0.01"
            value={budget}
            disabled={busy || running || !!pending}
            onChange={(e) => setBudget(e.target.value)}
          />
        </label>
        {pilot && (
          <label>
            {t("phase")}
            <select
              value={phase}
              disabled={busy || running || !!pending}
              onChange={(e) => setPhase(e.target.value as Request["phase"])}
            >
              <option value="full">{t("fullPhase")}</option>
              <option value="collect">{t("collectPhase")}</option>
            </select>
          </label>
        )}
      </div>
      {pilot && <p className="training-note">{t("pilotCap")}</p>}
      {mode === "live" && !info.data?.live_available && (
        <p className="training-note">{t("liveLocked")}</p>
      )}
      <label className="training-auto-import">
        <input
          type="checkbox"
          checked={pilot || attention}
          disabled={
            pilot ||
            !info.data?.attention_available ||
            busy ||
            running ||
            !!pending
          }
          onChange={(e) => setAttention(e.target.checked)}
        />
        {t("attention")}
      </label>
      <label className="training-auto-import">
        <input
          type="checkbox"
          checked={autoImport}
          disabled={busy || running || !!pending}
          onChange={(e) => setAutoImport(e.target.checked)}
        />
        {t("autoImport")}
      </label>
      <button
        className="primary"
        disabled={
          busy ||
          running ||
          !available ||
          !validBudget ||
          info.isLoading ||
          latest.isLoading ||
          latest.isError ||
          (pilot && !!job)
        }
        onClick={start}
      >
        {busy || running ? t("running") : pending ? t("retry") : t("start")}
      </button>
      {error instanceof ApiError && t.has(`errors.${error.code}`) ? (
        <p role="alert" className="training-note">
          {t(`errors.${error.code}`)}
        </p>
      ) : error ? (
        <ErrorNotice error={error} />
      ) : null}
      {status.isError && <ErrorNotice error={status.error} />}
      {job && (
        <div className="training-status" role="status" aria-live="polite">
          <p>
            <strong>{t(`status.${job.status}`)}</strong> ·{" "}
            {t(`stages.${job.stage}`)}
          </p>
          <ol aria-label={t("steps")}>
            {stages.slice(0, 5).map((stage) => (
              <li
                key={stage}
                aria-current={job.stage === stage ? "step" : undefined}
                data-done={
                  pilot
                    ? completedStages[stage]
                    : stages.indexOf(stage) < stages.indexOf(job.stage)
                }
              >
                {t(`stages.${stage}`)}
              </li>
            ))}
          </ol>
          <p>
            {t("progress", {
              completed: job.completed ?? 0,
              total: job.total ?? 0,
              cached: job.cache_hits ?? 0,
              calls: job.api_calls ?? 0,
            })}
          </p>
          <p>{t("spent", { amount: job.spent_usd ?? "0" })}</p>
          {!!job.unknown_cost_calls && (
            <p className="training-note">
              {t("unknownCost", { count: job.unknown_cost_calls })}
            </p>
          )}
          {job.error_code && (
            <p className="training-note">
              {t.has(`errors.${job.error_code}`)
                ? t(`errors.${job.error_code}`)
                : t("failedHint")}{" "}
              <code>{job.error_code}</code>
            </p>
          )}
          {job.imported && <p>{t("imported")}</p>}
          {pilot && !running && (
            <div className="training-actions">
              <button
                disabled={
                  busy ||
                  !!job.artifact_hash ||
                  !!job.pilot_report?.attention ||
                  job.pilot_report?.stopped_reason ===
                    "DISPATCH_REVIEW_REQUIRED" ||
                  !!job.unknown_cost_calls ||
                  job.pilot_report?.stopped_reason === "PROVIDER_RATE_LIMITED"
                }
                onClick={() => resume("full")}
              >
                {t("resume")}
              </button>
              <button
                disabled={
                  busy ||
                  !job.ready_for_training ||
                  !!job.pilot_report?.attention
                }
                onClick={() => resume("train")}
              >
                {t("trainCollected")}
              </button>
            </div>
          )}
          {pilot &&
            job.pilot_report?.conclusion === "INSUFFICIENT_EVIDENCE" && (
              <p className="training-note">{t("insufficient")}</p>
            )}
          {pilot &&
            !running &&
            reviews.data
              ?.filter((r) => !r.reviewed)
              .map((row) => (
                <ReviewCase
                  key={row.task_id}
                  jobId={job.id}
                  row={row}
                  onSaved={() => {
                    void reviews.refetch();
                    void status.refetch();
                  }}
                />
              ))}
          {job.artifact_hash && (
            <div className="training-actions">
              <a
                href={`/api/v1/research/training/jobs/${encodeURIComponent(job.id)}/artifact`}
                download
              >
                {t("download")}
              </a>
              {job.status === "succeeded" &&
                !job.imported &&
                (!pilot || job.pilot_report?.import_eligible === true) && (
                  <button disabled={busy} onClick={importModel}>
                    {t("import")}
                  </button>
                )}
            </div>
          )}
          {pilot && job.pilot_report && (
            <details>
              <summary>{t("pilotReport")}</summary>
              <pre>{JSON.stringify(job.pilot_report, null, 2)}</pre>
            </details>
          )}
          {job.holdout_report && Object.keys(job.holdout_report).length > 0 && (
            <details>
              <summary>{t("report")}</summary>
              <pre>{JSON.stringify(job.holdout_report, null, 2)}</pre>
            </details>
          )}
        </div>
      )}
      <p className="training-note">{t("scope")}</p>
    </section>
  );
}

function ReviewCase({
  jobId,
  row,
  onSaved,
}: {
  jobId: string;
  row: components["schemas"]["TrainingReviewCase"];
  onSaved: () => void;
}) {
  const t = useTranslations("RouterTraining");
  const [decisions, setDecisions] = useState<Record<string, string>>({});
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>();
  async function save() {
    if (busy) return;
    setBusy(true);
    setError(undefined);
    try {
      unwrap(
        await api.POST("/v1/research/training/jobs/{job_id}/reviews", {
          params: { path: { job_id: jobId } },
          body: {
            items: row.answers.map((a) => ({
              task_id: row.task_id,
              config_id: a.config_id,
              response_sha256: a.response_sha256,
              qualified: decisions[a.config_id] === "yes",
              reason,
            })),
          },
        }),
      );
      onSaved();
    } catch (e) {
      setError(e);
    } finally {
      setBusy(false);
    }
  }
  return (
    <details>
      <summary>
        {t("reviewCase", { id: row.task_id.slice(-12), split: row.split })}
      </summary>
      {row.task.map((m, i) => (
        <pre key={i} style={{ whiteSpace: "pre-wrap" }}>
          {m.content}
        </pre>
      ))}
      <p>{t("reference")}</p>
      <pre style={{ whiteSpace: "pre-wrap" }}>{row.gold}</pre>
      {row.answers.map((a, i) => (
        <div key={a.config_id}>
          <p>{t("answer", { index: i + 1 })}</p>
          <pre style={{ whiteSpace: "pre-wrap" }}>{a.text}</pre>
          <label>
            {t("qualified")}
            <select
              value={decisions[a.config_id] ?? ""}
              disabled={busy}
              onChange={(e) =>
                setDecisions({ ...decisions, [a.config_id]: e.target.value })
              }
            >
              <option value="">{t("chooseReview")}</option>
              <option value="yes">{t("pass")}</option>
              <option value="no">{t("fail")}</option>
            </select>
          </label>
        </div>
      ))}
      <label>
        {t("reviewReason")}
        <textarea
          value={reason}
          minLength={8}
          maxLength={2000}
          disabled={busy}
          onChange={(e) => setReason(e.target.value)}
        />
      </label>
      <button
        disabled={
          busy ||
          reason.trim().length < 8 ||
          row.answers.some((a) => !decisions[a.config_id])
        }
        onClick={save}
      >
        {t("saveReview")}
      </button>
      {error ? <ErrorNotice error={error} /> : null}
    </details>
  );
}
