"use client";
import { useState } from "react";
import dynamic from "next/dynamic";
import { useQuery } from "@tanstack/react-query";
import { useTranslations } from "next-intl";
import { api, unwrap, type User } from "@/lib/api";
import { ErrorNotice, Spinner } from "./ui";
import { RouterTraining } from "./router-training";
const ResearchPanel = dynamic(
  () => import("./research-panel").then((m) => m.ResearchPanel),
  { loading: () => <Spinner /> },
);

export function OptimizerLab({ user }: { user: User }) {
  const t = useTranslations("OptimizerLab");
  const r = useTranslations("Research");
  const [router, setRouter] = useState(true);
  const [prompt, setPrompt] = useState(true);
  const [memory, setMemory] = useState(true);
  const query = useQuery({
    queryKey: ["optimizer-lab", user.id],
    enabled: user.role === "admin",
    queryFn: async () => unwrap(await api.GET("/v1/research/lab")),
    retry: false,
  });
  if (user.role !== "admin")
    return (
      <section className="research-forbidden">
        <h1>{r("forbidden")}</h1>
      </section>
    );
  return (
    <div className="optimizer-lab">
      <header className="lab-heading">
        <p className="eyebrow">OPTIMIZER LAB / OU</p>
        <h1>{t("title")}</h1>
        <p>{t("intro")}</p>
      </header>
      {query.isLoading && <Spinner />}
      {query.isError && <ErrorNotice error={query.error} />}
      <RouterTraining user={user} />
      <ResearchPanel
        user={user}
        routerEnabled={router}
        onToggleRouter={setRouter}
        promptEnabled={prompt}
        onTogglePrompt={setPrompt}
        memoryEnabled={memory}
        onToggleMemory={setMemory}
        modules={query.data?.modules}
      />
      <p className="lab-evidence-note">{t("evaluationLocked")}</p>
    </div>
  );
}
