"use client";
import { useLocale, useTranslations } from "next-intl";
import { useRouter } from "next/navigation";
import { setLocale } from "@/i18n/actions";
import { useState, useTransition } from "react";

export function LanguageSwitch() {
  const locale = useLocale();
  const t = useTranslations("App");
  const router = useRouter();
  const [pending, startTransition] = useTransition();
  const [failed, setFailed] = useState(false);
  function change(value: "vi" | "en") {
    if (value === locale || pending) return;
    setFailed(false);
    startTransition(async () => {
      try {
        await setLocale(value);
        router.refresh();
      } catch {
        setFailed(true);
      }
    });
  }
  return (
    <div
      className="language-switch"
      role="group"
      aria-label={t("language")}
      aria-busy={pending}
    >
      {(["vi", "en"] as const).map((value) => (
        <button
          key={value}
          lang={value}
          aria-pressed={locale === value}
          disabled={pending}
          onClick={() => change(value)}
        >
          {value.toUpperCase()}
        </button>
      ))}
      {failed && <span role="alert">{t("languageFailed")}</span>}
    </div>
  );
}
