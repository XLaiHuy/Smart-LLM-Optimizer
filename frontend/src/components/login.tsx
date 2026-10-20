"use client";
import Image from "next/image";
import { ArrowRight, ArrowUpRight } from "lucide-react";
import { useState, type FormEvent } from "react";
import { useTranslations } from "next-intl";
import { api, unwrap, type User } from "@/lib/api";
import { LanguageSwitch } from "./language-switch";
import { ErrorNotice, Spinner } from "./ui";

export function Login({
  onSuccess,
  expired,
}: {
  onSuccess: (user: User) => void;
  expired: boolean;
}) {
  const t = useTranslations("App");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>();
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const fields = new FormData(event.currentTarget);
    setBusy(true);
    setError(undefined);
    try {
      const user = unwrap(
        await api.POST("/v1/auth/login", {
          body: {
            username: String(fields.get("username")),
            password: String(fields.get("password")),
          },
        }),
      );
      onSuccess(user);
    } catch (reason) {
      setError(reason);
    } finally {
      setBusy(false);
    }
  }
  return (
    <main className="login-page">
      <section className="login-story">
        <div className="school-lockup">
          <Image
            src="/brand/ou-logo.jpg"
            width={64}
            height={39}
            alt="OU"
            priority
          />
          <span>{t("school")}</span>
        </div>
        <div className="story-copy">
          <p className="eyebrow">{t("loginTag")}</p>
          <h1>
            {t("loginStatement")
              .split("\n")
              .map((line, i) => (
                <span key={i}>
                  {line}
                  <br />
                </span>
              ))}
          </h1>
          <p>{t("loginDescription")}</p>
          <div className="story-rule" />
        </div>
        <footer>
          <span>Smart LLM Optimizer</span>
          <ArrowUpRight size={22} />
        </footer>
      </section>
      <section className="login-form-panel">
        <div className="login-top">
          <span className="environment-dot">{t("foundation")}</span>
          <LanguageSwitch />
        </div>
        <div className="login-form-wrap">
          <p className="eyebrow">WORKSPACE ACCESS</p>
          <h2>{t("loginTitle")}</h2>
          <p className="muted">{t("loginHint")}</p>
          {expired && (
            <p className="notice" role="status">
              {t("expired")}
            </p>
          )}
          <form onSubmit={submit} className="login-form">
            <label htmlFor="username">{t("username")}</label>
            <input
              autoComplete="username"
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
              {busy ? <Spinner /> : null}
              {busy ? t("loggingIn") : t("login")}
              <ArrowRight size={18} />
            </button>
          </form>
          <p className="account-hint">{t("accountHint")}</p>
          <div className="login-mock-note">
            <span className="mock-badge">MOCK</span>
            <p>{t("mockHint")}</p>
          </div>
        </div>
        <footer className="login-footer">OU · {t("product")}</footer>
      </section>
    </main>
  );
}
