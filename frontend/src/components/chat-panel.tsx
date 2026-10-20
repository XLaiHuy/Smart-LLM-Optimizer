"use client";
import Image from "next/image";
import * as Switch from "@radix-ui/react-switch";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import {
  ArrowUp,
  ArrowUpRight,
  SlidersHorizontal,
  RefreshCw,
  Check,
  FileText,
} from "lucide-react";
import { useEffect, useRef, useState, type FormEvent } from "react";
import { useTranslations } from "next-intl";
import {
  api,
  unwrap,
  ApiError,
  allFlags,
  requestFlags,
  type ChatRequest,
  type Flags,
} from "@/lib/api";
import { ErrorNotice, Spinner } from "./ui";

export function ChatPanel({
  userId,
  selected,
  createSession,
  onTrace,
  onBusy,
}: {
  userId: string;
  selected: string | null;
  createSession: (title?: string) => Promise<string>;
  onTrace: (id: string) => void;
  onBusy: (busy: boolean) => void;
}) {
  const t = useTranslations("App");
  const client = useQueryClient();
  const [draft, setDraft] = useState("");
  const [mode, setMode] = useState<"baseline" | "optimized">("baseline");
  const [flags, setFlags] = useState<Flags>(allFlags);
  const [configOpen, setConfigOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>();
  const [retrying, setRetrying] = useState(false);
  const pending = useRef<ChatRequest | null>(null);
  const end = useRef<HTMLDivElement>(null);
  const detail = useQuery({
    queryKey: ["session", userId, selected],
    enabled: !!selected,
    queryFn: async () =>
      unwrap(
        await api.GET("/v1/sessions/{session_id}", {
          params: { path: { session_id: selected! } },
        }),
      ),
  });
  const messages = detail.data?.messages ?? [];
  useEffect(() => {
    end.current?.scrollIntoView({ behavior: "instant", block: "end" });
  }, [messages.length, busy]);
  async function send(event: FormEvent) {
    event.preventDefault();
    if (busy || (!draft.trim() && !pending.current)) return;
    setBusy(true);
    onBusy(true);
    setError(undefined);
    try {
      if (!pending.current) {
        const sessionId = selected || (await createSession(draft));
        pending.current = {
          session_id: sessionId,
          client_request_id: crypto.randomUUID(),
          message: draft,
          mode,
          flags: requestFlags(mode, flags),
          ...(mode === "optimized" ? { policy_id: "foundation-mock-v3" } : {}),
        };
      }
      const answer = unwrap(
        await api.POST("/v1/chat", { body: pending.current }),
      );
      pending.current = null;
      setRetrying(false);
      setDraft("");
      await client.invalidateQueries({ queryKey: ["session", userId] });
      await client.invalidateQueries({ queryKey: ["sessions", userId] });
      await client.invalidateQueries({ queryKey: ["overview", userId] });
      client.setQueryData(["trace", answer.request_id], answer);
    } catch (reason) {
      setError(reason);
      const uncertain =
        !(reason instanceof ApiError) ||
        ["REQUEST_IN_PROGRESS", "SESSION_BUSY"].includes(reason.code);
      if (!uncertain) pending.current = null;
      setRetrying(uncertain && pending.current !== null);
    } finally {
      setBusy(false);
      onBusy(pending.current !== null);
    }
  }
  const locked = busy || retrying;
  return (
    <section className="chat-panel">
      <header className="chat-toolbar">
        <div className="conversation-label">
          <span className="environment-dot" />
          <span>{detail.data?.title || t("private")}</span>
        </div>
        <button
          className={`button small ${configOpen ? "selected" : ""}`}
          aria-expanded={configOpen}
          onClick={() => setConfigOpen(!configOpen)}
        >
          <SlidersHorizontal size={15} />
          <span>{t("configuration")}</span>
        </button>
      </header>
      {configOpen && (
        <section className="configuration-panel">
          <div>
            <h2>{t("configuration")}</h2>
            <p>{t("configHint")}</p>
          </div>
          <div className="flag-grid">
            {(Object.keys(flags) as (keyof Flags)[]).map((key) => (
              <label key={key} className="flag-control">
                <span>
                  {t(key)}
                  <small>
                    {mode === "optimized" && flags[key]
                      ? t("not_implemented")
                      : t("disabled")}
                  </small>
                </span>
                <Switch.Root
                  className="switch"
                  checked={mode === "optimized" && flags[key]}
                  disabled={locked || mode === "baseline"}
                  onCheckedChange={(checked) =>
                    setFlags({ ...flags, [key]: checked })
                  }
                  aria-label={t(key)}
                >
                  <Switch.Thumb className="switch-thumb" />
                </Switch.Root>
              </label>
            ))}
          </div>
        </section>
      )}
      <div className="conversation-scroll" aria-live="polite" aria-busy={busy}>
        {detail.isLoading && (
          <div className="center-loader">
            <Spinner />
          </div>
        )}
        {detail.isError && (
          <div className="message-list">
            <ErrorNotice error={detail.error} />
            <button className="button" onClick={() => detail.refetch()}>
              {t("retry")}
            </button>
          </div>
        )}
        {!detail.isLoading && !messages.length && !detail.isError && (
          <div className="welcome">
            <span className="welcome-mark">
              <Image src="/brand/ou-logo.jpg" width={89} height={54} alt="OU" />
            </span>
            <p className="eyebrow">SMART LLM OPTIMIZER</p>
            <h1>{t("welcome")}</h1>
            <p>{t("welcomeHint")}</p>
            <div className="welcome-tags">
              <span>
                <Check size={14} />
                {t("private")}
              </span>
              <span>
                <FileText size={14} />
                {t("trace")}
              </span>
            </div>
          </div>
        )}
        {!!messages.length && (
          <div className="message-list">
            {messages.map((message, index) => (
              <article
                key={message.id || index}
                className={`message ${message.role}`}
              >
                <div className={`message-avatar ${message.role}`}>
                  {message.role === "user" ? (
                    <span>U</span>
                  ) : (
                    <Image
                      src="/brand/ou-logo.jpg"
                      width={24}
                      height={15}
                      alt="OU"
                    />
                  )}
                </div>
                <div className="message-body">
                  <header>
                    <strong>
                      {message.role === "user" ? t("you") : t("assistant")}
                    </strong>
                    {message.role === "assistant" && (
                      <span className="mock-badge">MOCK</span>
                    )}
                  </header>
                  <div className="message-content">{message.content}</div>
                  {message.role === "assistant" && message.request_id && (
                    <button
                      className="trace-link"
                      onClick={() => onTrace(message.request_id!)}
                    >
                      <ArrowUpRight size={14} />
                      {t("viewTrace")}
                    </button>
                  )}
                </div>
              </article>
            ))}
          </div>
        )}
        {busy && (
          <div className="thinking" role="status">
            <Spinner />
            {t("sending")}
          </div>
        )}
        <div ref={end} />
      </div>
      <div className="composer-wrap">
        {error !== undefined && <ErrorNotice error={error} />}
        <form className={`composer ${busy ? "busy" : ""}`} onSubmit={send}>
          <label htmlFor="message" className="sr-only">
            {t("composer")}
          </label>
          <textarea
            id="message"
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            placeholder={t("placeholder")}
            maxLength={50000}
            readOnly={locked}
            rows={2}
            onKeyDown={(e) => {
              if (
                e.key === "Enter" &&
                !e.shiftKey &&
                !e.nativeEvent.isComposing
              ) {
                e.preventDefault();
                e.currentTarget.form?.requestSubmit();
              }
            }}
          />
          <div className="composer-bottom">
            <div className="mode-switch" role="group" aria-label={t("mode")}>
              {(["baseline", "optimized"] as const).map((value) => (
                <button
                  type="button"
                  key={value}
                  aria-pressed={mode === value}
                  disabled={locked}
                  onClick={() => setMode(value)}
                >
                  {t(value)}
                </button>
              ))}
            </div>
            <button
              className="send-button"
              type="submit"
              aria-label={retrying ? t("retry") : t("send")}
              disabled={
                busy ||
                (!draft.trim() && !retrying) ||
                detail.isLoading ||
                detail.isError
              }
            >
              {busy ? (
                <Spinner />
              ) : retrying ? (
                <RefreshCw size={18} />
              ) : (
                <ArrowUp size={20} />
              )}
            </button>
          </div>
        </form>
        <div className="composer-footer">
          <span>{t("composerHint")}</span>
          <span>G0 · {t("mockShort")}</span>
        </div>
        <p className="mock-disclosure">{t("mockHint")}</p>
      </div>
    </section>
  );
}
