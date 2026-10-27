"use client";
import { useQuery } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { useLocale, useTranslations } from "next-intl";
import dynamic from "next/dynamic";
import { api, unwrap } from "@/lib/api";
import {
  PIPELINE,
  pipelineState,
  callPaths,
  type Execution,
} from "@/lib/execution-view";
import { Spinner, ErrorNotice } from "./ui";
const Scene = dynamic(
  () => import("./3d/trace-scene").then((m) => m.TraceScene),
  { ssr: false, loading: () => <Spinner /> },
);

export function TraceExperience({
  requestId,
  userId,
}: {
  requestId: string | null;
  userId: string;
}) {
  const t = useTranslations("TraceView"),
    locale = useLocale();
  const [mode, setMode] = useState<"routing" | "architecture">(requestId ? "routing" : "architecture");
  const [motion, setMotion] = useState(false);
  const [simulationPlaying, setSimulationPlaying] = useState(true);
  const [reduceMotion, setReduceMotion] = useState(true);
  useEffect(() => {
    const reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)");
    const update = () => {
      setReduceMotion(reducedMotion.matches);
      setMotion(
        !window.matchMedia("(prefers-reduced-motion: reduce)").matches &&
          localStorage.getItem(`smart-llm:motion:${userId}`) === "on",
      );
    };
    update();
    reducedMotion.addEventListener("change", update);
    window.addEventListener("storage", update);
    return () => {
      reducedMotion.removeEventListener("change", update);
      window.removeEventListener("storage", update);
    };
  }, [userId]);
  const runtime = useQuery({
    queryKey: ["runtime-settings", userId],
    queryFn: async () => unwrap(await api.GET("/v1/runtime-settings")),
  });
  const query = useQuery<Execution>({
    queryKey: ["execution", userId, requestId],
    enabled: !!requestId,
    queryFn: async () =>
      unwrap(
        await api.GET("/v1/requests/{request_id}/execution", {
          params: { path: { request_id: requestId! } },
        }),
      ),
    refetchInterval: (q) => (q.state.data?.status === "running" ? 1000 : false),
  });
  const execution = query.data,
    models = runtime.data?.models ?? [];
  const paths = callPaths(execution, models);
  return (
    <section className="trace-experience">
      <div className="trace-view-tabs" role="tablist" aria-label={t("views")}>
        {(["routing", "architecture"] as const).map((view) => (
          <button
            key={view}
            id={`trace-tab-${view}`}
            role="tab"
            aria-controls="trace-view-panel"
            aria-selected={mode === view}
            className="button small"
            onClick={() => setMode(view)}
          >
            {t(view)}
          </button>
        ))}
      </div>
      <div
        role="tabpanel"
        id="trace-view-panel"
        aria-labelledby={`trace-tab-${mode}`}
      >
        {mode === "architecture" ? (
          <div className="simulation-controls">
            <p>
              <strong>{t("simulation")}</strong>
              <br />
              <span className="muted">{t("simulationHint")}</span>
            </p>
            <button
              className="button small"
              disabled={reduceMotion}
              onClick={() => setSimulationPlaying((p) => !p)}
            >
              {t(
                simulationPlaying && !reduceMotion
                  ? "pauseSimulation"
                  : "playSimulation",
              )}
            </button>
            {reduceMotion && <small>{t("reducedMotion")}</small>}
          </div>
        ) : (
          !requestId && <p className="muted">{t("schematic")}</p>
        )}
        {query.isLoading && <Spinner />}
        {query.isError && <ErrorNotice error={query.error} />}
        {runtime.isError && <ErrorNotice error={runtime.error} />}
        {models.length === 3 && (
          <Scene
            key={mode}
            mode={mode}
            models={models}
            execution={execution}
            locale={locale}
            motion={
              mode === "architecture"
                ? simulationPlaying && !reduceMotion
                : motion
            }
            simulation={mode === "architecture"}
          />
        )}
        {mode === "routing" ? (
          <>
            <div className="model-planet-cards">
              {models.map((model, index) => {
                const selected =
                  execution?.status === "succeeded" &&
                  execution.route?.model_id === model.model_id;
                const stage = execution?.route?.stages.find(
                  (s) => s.config_id === model.config_id,
                );
                return (
                  <article
                    key={model.model_id}
                    data-model-id={model.model_id}
                    className={`planet-card planet-${index} ${selected ? "selected" : ""}`}
                  >
                    <strong>{model.label}</strong>
                    <small>
                      {model.provider === "openai" ? "OpenAI" : "OpenRouter"}
                    </small>
                    {selected && <span>{t("finalModel")}</span>}
                    {stage && (
                      <small>
                        {t("score")}: {stage.score?.toFixed(3) ?? "—"} /{" "}
                        {t("threshold")}: {stage.threshold?.toFixed(3) ?? "—"}
                        <br />
                        {stage.status}
                      </small>
                    )}
                  </article>
                );
              })}
            </div>
            <ol className="execution-calls">
              {paths.map((path) => (
                <li
                  key={path.call.call_id}
                  data-status={
                    path.failed ? "failed" : path.call.dispatch_state
                  }
                >
                  <strong>
                    {path.sequence}.{" "}
                    {path.model?.label ??
                      `${t("legacyModel")}: ${path.call.model_id}`}
                  </strong>{" "}
                  · {path.call.provider_host ?? t("unknown")} ·{" "}
                  {path.failed ? t("failed") : path.call.dispatch_state}
                </li>
              ))}
            </ol>
            {!!execution?.route?.attention_features?.length &&
              execution.route.attention_executed && (
                <details>
                  <summary>{t("attention")}</summary>
                  <p className="muted">{t("attentionHint")}</p>
                  <div className="attention-bars">
                    {execution.route.attention_features.map((value, i) => (
                      <label key={i}>
                        Attention {i + 1}
                        <meter min={0} max={1} value={value} />
                        {value.toFixed(3)}
                      </label>
                    ))}
                  </div>
                </details>
              )}
          </>
        ) : (
          <ol className="architecture-stages">
            {PIPELINE.map((step) => (
              <li
                key={step.id}
                data-status={pipelineState(execution, step.events)}
              >
                <strong>{locale === "en" ? step.en : step.vi}</strong>
                <span className="status-pill">
                  {t(pipelineState(execution, step.events))}
                </span>
                <p>{step.detail}</p>
                {execution?.events
                  .filter((e) => step.events.includes(e.stage as never))
                  .map((e) => (
                    <small key={e.sequence}>
                      {e.sequence}. {e.stage}: {t(e.status)} · {e.at}
                      <br />
                    </small>
                  ))}
              </li>
            ))}
          </ol>
        )}
        {execution?.legacy && <p className="muted">{t("legacyHint")}</p>}
        {execution?.route?.task_family && (
          <p>
            {t("task")}: <strong>{execution.route.task_family}</strong> ·{" "}
            {execution.route.group_profile_applied
              ? t("profileApplied")
              : t("shadow")}
          </p>
        )}
        <p className="muted">{t("measurementHint")}</p>
      </div>
    </section>
  );
}
