"use client";
import { useEffect, useState } from "react";
import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import { useLocale, useTranslations } from "next-intl";
import { Layers, ArrowRight, Sparkles } from "lucide-react";
import { api, unwrap, type User } from "@/lib/api";
import { LanguageSwitch } from "./language-switch";
import { DynamicNeuralRoutingCosmos3D } from "./3d";
import { ErrorNotice, Spinner } from "./ui";

export function SettingsPanel({ user }: { user: User }) {
  const t = useTranslations("Settings");
  const locale = useLocale();
  const [motion, setMotion] = useState(false);
  const [flags, setFlags] = useState({
    router: true,
    rewrite: true,
    context: true,
    memory: true,
  });
  useEffect(() => {
    const timer = window.setTimeout(() => {
      setMotion(localStorage.getItem(`smart-llm:motion:${user.id}`) === "on");
      try {
        const saved = JSON.parse(
          localStorage.getItem(`smart-llm:flags:${user.id}`) || "null",
        );
        if (
          saved &&
          Object.keys(flags).every((key) => typeof saved[key] === "boolean")
        )
          setFlags(saved);
      } catch {
        /* Defaults remain usable. */
      }
    }, 0);
    return () => window.clearTimeout(timer);
    // Read once per account; edits below are written explicitly, not during mount.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [user.id]);
  const runtime = useQuery({
    queryKey: ["runtime-settings", user.id],
    queryFn: async () => unwrap(await api.GET("/v1/runtime-settings")),
  });
  function changeMotion(value: boolean) {
    setMotion(value);
    localStorage.setItem(`smart-llm:motion:${user.id}`, value ? "on" : "off");
    window.dispatchEvent(new Event("storage"));
  }
  function changeFlag(key: keyof typeof flags, value: boolean) {
    const next = { ...flags, [key]: value };
    setFlags(next);
    localStorage.setItem(`smart-llm:flags:${user.id}`, JSON.stringify(next));
  }
  return (
    <div className="settings-page">
      <header>
        <h1>{t("title")}</h1>
        <p className="muted">{t("hint")}</p>
      </header>
      <section className="settings-card">
        <h2>{t("language")}</h2>
        <LanguageSwitch />
        <label className="settings-option">
          <input
            type="checkbox"
            checked={motion}
            onChange={(e) => changeMotion(e.target.checked)}
          />
          {t("motion")}
        </label>
        <p className="muted">{t("motionHint")}</p>
      </section>
      <section className="settings-card">
        <h2>{t("defaults")}</h2>
        <p className="muted">{t("nextRequest")}</p>
        {(Object.keys(flags) as (keyof typeof flags)[]).map((key) => (
          <label className="settings-option" key={key}>
            <input
              type="checkbox"
              checked={flags[key]}
              onChange={(e) => changeFlag(key, e.target.checked)}
            />
            {t(key)}
          </label>
        ))}
      </section>
      <section className="settings-card">
        <h2>{t("models")}</h2>
        {runtime.isLoading && <Spinner />}
        {runtime.isError && <ErrorNotice error={runtime.error} />}
        <div className="model-planet-cards">
          {runtime.data?.models.map((model) => (
            <article className="planet-card" key={model.model_id}>
              <strong>{model.label}</strong>
              <small>{model.provider}</small>
              <span>
                {model.available ? t("configured") : t("unavailable")}
              </span>
            </article>
          ))}
        </div>
        <p className="muted">{t("serverKeys")}</p>
        <p>
          {t("groupPolicy")}:{" "}
          {runtime.data
            ? t(
                runtime.data.group_policy_status === "GROUP_POLICY_READY"
                  ? "policyReady"
                  : "policyShadow",
              )
            : "—"}
        </p>
        <p>
          {t("quota")}: {user.quota_usd} USD · {t("readOnly")}
        </p>
      </section>
      <section className="settings-card flex flex-col gap-3">
        <div className="flex items-center justify-between">
          <div>
            <h2>{t("architecture")}</h2>
            <p className="muted text-xs">
              {locale === "vi"
                ? "Không gian kiến trúc 3D điều phối 3 mô hình (GPT-OSS 20B, GPT-6 Luna, GPT-OSS 120B)."
                : "3D Architecture space orchestrating 3 models (GPT-OSS 20B, GPT-6 Luna, GPT-OSS 120B)."}
            </p>
          </div>
          <Link
            href="/pipeline"
            className="button primary small inline-flex items-center gap-1.5 shadow-xs"
          >
            <Layers size={14} />
            <span>{locale === "vi" ? "Mở Luồng 3D Toàn Màn Hình" : "Open Full 3D Pipeline"}</span>
            <ArrowRight size={14} />
          </Link>
        </div>

        <div className="rounded-xl border border-slate-200 overflow-hidden bg-slate-900 shadow-xs">
          <div className="bg-slate-950/70 px-3 py-1.5 flex items-center justify-between text-xs text-slate-300 border-b border-slate-800">
            <span className="flex items-center gap-1.5">
              <Sparkles size={13} className="text-cyan-400" />
              {locale === "vi" ? "Thiên Hà Định Tuyến 3D (3 Model Orbit)" : "3D Neural Routing Cosmos"}
            </span>
            <span className="text-[11px] text-slate-400">
              Interactive 360°
            </span>
          </div>
          <DynamicNeuralRoutingCosmos3D height={280} interactive compact />
        </div>
      </section>
    </div>
  );
}
