"use client";
import Link from "next/link";
import { useTranslations } from "next-intl";
import { ArrowRight, Check, FileText, Scale, ShieldCheck } from "lucide-react";
import { useQuery } from "@tanstack/react-query";
import { api, unwrap } from "@/lib/api";

export function LandingProblem() {
  const l = useTranslations("Landing");
  return (
    <section className="landing-section landing-problem" id="problem">
      <div className="landing-section-heading" data-reveal>
        <p className="eyebrow">{l("problemTag")}</p>
        <h2>{l("problemTitle")}</h2>
        <p>{l("problemText")}</p>
      </div>
      <div className="landing-feature-grid">
        {(
          [
            ["fit", Scale],
            ["control", ShieldCheck],
            ["sources", FileText],
          ] as const
        ).map(([key, Icon], index) => (
          <article
            key={key}
            data-reveal="zoom"
            style={
              { "--reveal-delay": `${index * 90}ms` } as React.CSSProperties
            }
          >
            <Icon size={23} />
            <h3>{l(`${key}Title`)}</h3>
            <p>{l(`${key}Text`)}</p>
          </article>
        ))}
      </div>
    </section>
  );
}

export function LandingModels() {
  const l = useTranslations("Landing");
  const info = useQuery({
    queryKey: ["platform-info"],
    queryFn: async () => unwrap(await api.GET("/v1/platform-info")),
    retry: false,
  });
  return (
    <section className="landing-section" id="models">
      <div className="landing-section-heading" data-reveal>
        <p className="eyebrow">{l("modelsTag")}</p>
        <h2>{l("modelsTitle")}</h2>
        <p>{l("modelsHint")}</p>
      </div>
      {info.isError && (
        <p role="status" className="notice" data-reveal>
          {l("statusUnknown")}
        </p>
      )}
      <div className="landing-model-grid">
        {(
          info.data?.models ?? [
            { name: "GPT-OSS 20B", status: "planned" },
            { name: "GPT-OSS 120B", status: "planned" },
            { name: "GPT-6 Luna", status: "planned" },
          ]
        ).map((model, index) => {
          const modelKey = model.name.toLowerCase().includes("20b")
            ? "note20B"
            : model.name.toLowerCase().includes("120b")
              ? "note120B"
              : model.name.toLowerCase().includes("luna")
                ? "noteLuna"
                : "modelNote";
          return (
            <article
              key={model.name}
              data-reveal="zoom"
              style={
                { "--reveal-delay": `${index * 80}ms` } as React.CSSProperties
              }
            >
              <span className="landing-model-status">
                <Check size={14} />
                {info.data ? l(model.status) : l("statusUnknown")}
              </span>
              <h3>{model.name}</h3>
              <p>{l(modelKey)}</p>
            </article>
          );
        })}
      </div>
    </section>
  );
}

export function LandingEvidence() {
  const l = useTranslations("Landing");
  return (
    <section className="landing-section landing-evidence" id="evidence">
      <div data-reveal="left">
        <p className="eyebrow">{l("evidenceTag")}</p>
        <h2>{l("evidenceTitle")}</h2>
        <p>{l("evidenceText")}</p>
      </div>
      <div data-reveal="right">
        <a className="button" href="#models">
          {l("method")}
          <ArrowRight size={17} />
        </a>
      </div>
    </section>
  );
}

export function LandingFooter() {
  const l = useTranslations("Landing");
  const t = useTranslations("App");
  return (
    <footer className="landing-footer" data-reveal>
      <div>
        <strong>Smart LLM</strong>
        <p>{l("footer")}</p>
      </div>
      <nav aria-label={l("sourceCode")}>
        <a href="https://github.com/XLaiHuy/Smart-LLM-Optimizer">
          {l("sourceCode")}
        </a>
        <a href="https://github.com/XLaiHuy/Smart-LLM-Optimizer/issues">
          {l("reportIssue")}
        </a>
        <a href="#problem">{l("method")}</a>
      </nav>
      <span>{t("school")}</span>
    </footer>
  );
}
