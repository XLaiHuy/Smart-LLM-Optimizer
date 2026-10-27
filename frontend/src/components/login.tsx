"use client";
import Image from "next/image";
import {
  LandingProblem,
  LandingModels,
  LandingEvidence,
  LandingFooter,
} from "./landing-sections";
import { LazySection } from "./lazy-section";
import Link from "next/link";
import { ArrowRight, ChevronRight, FileText, ShieldCheck } from "lucide-react";
import { useEffect, useState, type FormEvent } from "react";
import { useQuery } from "@tanstack/react-query";
import { useTranslations } from "next-intl";
import { api, unwrap, type User } from "@/lib/api";
import { LanguageSwitch } from "./language-switch";
import { Drawer, ErrorNotice, Spinner } from "./ui";

export function Login({
  onSuccess,
  expired,
}: {
  onSuccess: (user: User) => void;
  expired: boolean;
}) {
  const t = useTranslations("App");
  const l = useTranslations("Landing");
  const [open, setOpen] = useState(expired);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>();
  const info = useQuery({
    queryKey: ["platform-info"],
    queryFn: async () => unwrap(await api.GET("/v1/platform-info")),
    retry: false,
  });

  useEffect(() => {
    const revealElements = document.querySelectorAll("[data-reveal]");
    if (!revealElements.length) return;

    // Immediately reveal elements already inside the initial viewport
    revealElements.forEach((el) => {
      const rect = el.getBoundingClientRect();
      if (rect.top < window.innerHeight && rect.bottom > 0) {
        el.classList.add("is-visible");
      }
    });

    const observer = new IntersectionObserver(
      (entries) => {
        entries.forEach((entry) => {
          entry.target.classList.toggle("is-visible", entry.isIntersecting);
        });
      },
      { threshold: 0.12, rootMargin: "0px 0px -40px 0px" },
    );

    revealElements.forEach((el) => {
      observer.observe(el);
    });

    return () => observer.disconnect();
  }, []);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const fields = new FormData(event.currentTarget);
    setBusy(true);
    setError(undefined);
    try {
      onSuccess(
        unwrap(
          await api.POST("/v1/auth/login", {
            body: {
              username: String(fields.get("username")),
              password: String(fields.get("password")),
            },
          }),
        ),
      );
    } catch (reason) {
      setError(reason);
    } finally {
      setBusy(false);
    }
  }
  return (
    <main className="landing-page">
      <header className="landing-nav">
        <Link href="/" className="landing-brand">
          <Image
            src="/brand/ou-logo.jpg"
            width={64}
            height={39}
            alt="OU"
            priority
          />
          <span>
            Smart LLM <strong>Optimizer</strong>
          </span>
        </Link>
        <nav aria-label={l("navigation")}>
          <a href="#models">{l("research")}</a>
          <LanguageSwitch />
          <button className="button" onClick={() => setOpen(true)}>
            {t("login")}
          </button>
        </nav>
      </header>
      <section className="landing-hero">
        <div data-reveal="left">
          <p className="eyebrow">{l("eyebrow")}</p>
          <h1>
            {l("title")}
            <span>{l("titleAccent")}</span>
          </h1>
          <p className="landing-lead">{l("subtitle")}</p>
          <div className="landing-actions">
            <button className="button primary" onClick={() => setOpen(true)}>
              {l("start")}
              <ArrowRight size={18} />
            </button>
            <a className="button" href="#models">
              <FileText size={17} />
              {l("research")}
            </a>
          </div>
          <p className="landing-caption">
            {info.data
              ? l(info.data.execution_mode === "mock" ? "mock" : "live")
              : l("statusUnknown")}
          </p>
        </div>
        <div
          className="landing-flow"
          aria-label={l("flowTitle")}
          data-reveal="right"
        >
          <div className="landing-flow-heading">
            <span>{l("flowTitle")}</span>
            <span className="mock-badge">{l("illustration")}</span>
          </div>
          <p className="landing-example">{l("example")}</p>
          {(["understand", "filter", "choose", "measure"] as const).map(
            (key, index) => (
              <div className="landing-flow-row" key={key}>
                <span className="landing-step">0{index + 1}</span>
                <div>
                  <strong>{l(`${key}Title`)}</strong>
                  <p>{l(`${key}Hint`)}</p>
                </div>
                <ChevronRight size={16} />
              </div>
            ),
          )}
          <p className="landing-flow-note">
            <ShieldCheck size={17} />
            {l("flowNote")}
          </p>
        </div>
      </section>
      <LandingProblem />
      <LazySection kind="models">
        <LandingModels />
      </LazySection>
      <LandingEvidence />
      <LandingFooter />
      <Drawer
        open={open}
        onOpenChange={(value) => {
          if (!busy) setOpen(value);
        }}
        title={t("loginTitle")}
        description={t("loginHint")}
      >
        {expired && (
          <p className="notice" role="status">
            {t("expired")}
          </p>
        )}
        <form onSubmit={submit} className="login-form landing-login">
          <label htmlFor="username">{t("username")}</label>
          <input
            autoComplete="username"
            autoFocus
            id="username"
            name="username"
            required
            maxLength={64}
            disabled={busy}
          />
          <label htmlFor="password">{t("password")}</label>
          <input
            autoComplete="current-password"
            id="password"
            name="password"
            type="password"
            required
            maxLength={256}
            disabled={busy}
          />
          {error !== undefined && <ErrorNotice error={error} />}
          <button className="button primary" type="submit" disabled={busy}>
            {busy && <Spinner />}
            {busy ? t("loggingIn") : t("login")}
            <ArrowRight size={18} />
          </button>
        </form>
        <p className="account-hint">{t("accountHint")}</p>
      </Drawer>
    </main>
  );
}
