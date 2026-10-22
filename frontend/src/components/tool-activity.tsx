"use client";
import { useTranslations } from "next-intl";
import type { components } from "@/lib/generated/api";

export function ToolActivity({
  events,
}: {
  events: components["schemas"]["ToolEvent"][];
}) {
  const t = useTranslations("Tools");
  if (!events.length) return null;
  return (
    <div className="tool-activity" aria-label={t("title")}>
      {events.map((event) => (
        <div key={event.call_id}>
          <span>
            {t.has(event.name) ? t(event.name) : event.name} · {t(event.status)}
          </span>
          {event.output_json && (
            <details>
              <summary>{t("details")}</summary>
              <pre>{formatOutput(event.output_json)}</pre>
            </details>
          )}
        </div>
      ))}
    </div>
  );
}

function formatOutput(raw: string) {
  try {
    const data = JSON.parse(raw);
    return data.value ?? JSON.stringify(data, null, 2);
  } catch {
    return raw;
  }
}
