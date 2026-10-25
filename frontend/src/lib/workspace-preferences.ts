export type ChatMode = "baseline" | "optimized";

export interface ChatPreferences {
  mode: ChatMode;
  candidate: string | null;
}

export function parseChatPreferences(
  raw: string | null,
): ChatPreferences | null {
  if (!raw) return null;
  try {
    const value = JSON.parse(raw) as Partial<ChatPreferences>;
    if (value.mode !== "baseline" && value.mode !== "optimized") return null;
    return {
      mode: value.mode,
      candidate: typeof value.candidate === "string" ? value.candidate : null,
    };
  } catch {
    return null;
  }
}

export function shouldPollDocumentJobs(
  jobs: ReadonlyArray<{ status: string }> | undefined,
): number | false {
  return jobs?.some((job) => ["pending", "running"].includes(job.status))
    ? 1000
    : false;
}
