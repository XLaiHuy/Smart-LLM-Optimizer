"use client";
import Link from "next/link";
import { useTranslations } from "next-intl";
import { ArrowLeft } from "lucide-react";
import { LanguageSwitch } from "@/components/language-switch";

export default function ResearchGuide() {
  const t = useTranslations("Guide");
  return (
    <main className="research-guide">
      <header>
        <Link className="button" href="/">
          <ArrowLeft size={17} />
          {t("back")}
        </Link>
        <LanguageSwitch />
      </header>
      <p className="eyebrow">SMART LLM OPTIMIZER · OU</p>
      <h1>{t("title")}</h1>
      <p className="landing-lead">{t("intro")}</p>
      {["routing", "tools", "data", "cost", "limits"].map((key, index) => (
        <section key={key}>
          <span className="eyebrow">0{index + 1}</span>
          <h2>{t(`${key}Title`)}</h2>
          <p>{t(`${key}Text`)}</p>
        </section>
      ))}
    </main>
  );
}
