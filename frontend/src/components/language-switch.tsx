"use client";
import { useLocale, useTranslations } from "next-intl";
import { useRouter } from "next/navigation";
import { setLocale } from "@/i18n/actions";

export function LanguageSwitch() {
  const locale = useLocale();
  const t = useTranslations("App");
  const router = useRouter();
  async function change(value: "vi" | "en") {
    await setLocale(value);
    router.refresh();
  }
  return (
    <div className="language-switch" role="group" aria-label={t("language")}>
      {(["vi", "en"] as const).map((value) => (
        <button
          key={value}
          lang={value}
          aria-pressed={locale === value}
          onClick={() => change(value)}
        >
          {value.toUpperCase()}
        </button>
      ))}
    </div>
  );
}
