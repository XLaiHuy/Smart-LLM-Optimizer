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
  Sparkles,
  BookOpen,
  GitCompare,
} from "lucide-react";
import {
  useCallback,
  useEffect,
  useRef,
  useState,
  type FormEvent,
} from "react";
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
import { DocumentsPanel } from "./documents-panel";
import { MessageMetrics } from "./message-metrics";
import { ProcessingProgress } from "./processing-progress";
import { FormattedMessage } from "./formatted-message";
import { ErrorNotice, Spinner } from "./ui";

export function ChatPanel({
  userId,
  selected,
  createSession,
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
  const mvp = useTranslations("MVP");
  const [documentBusy, setDocumentBusy] = useState(false);
  const [documentsOpen, setDocumentsOpen] = useState(false);
  const [sources, setSources] = useState<{
    session: string | null;
    ids: string[];
  }>({ session: null, ids: [] });
  const selectSources = useCallback(
    (ids: string[]) => setSources({ session: selected, ids }),
    [selected],
  );
  const models = useQuery({
    queryKey: ["models", userId],
    queryFn: async () => unwrap(await api.GET("/v1/models")),
  });
  const source = models.data?.[0]?.execution_source ?? "mock";
  const [draft, setDraft] = useState("");
  const [mode, setMode] = useState<"baseline" | "optimized">("optimized");
  const [flags, setFlags] = useState<Flags>(allFlags);
  const [configOpen, setConfigOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const [flight, setFlight] = useState<{
    session: string;
    request: string;
  } | null>(null);
  const [error, setError] = useState<unknown>();
  const [retrying, setRetrying] = useState(false);
  const pending = useRef<ChatRequest | null>(null);
  const end = useRef<HTMLDivElement>(null);
  const nearBottom = useRef(true);
  const detail = useQuery({
    queryKey: ["session", userId, selected],
    enabled: !!selected,
    refetchInterval: (q) => (q.state.data?.active ? 700 : false),
    queryFn: async () =>
      unwrap(
        await api.GET("/v1/sessions/{session_id}", {
          params: { path: { session_id: selected! } },
        }),
      ),
  });
  const messages = detail.data?.messages ?? [];
  const resumedRequest = detail.data?.active_client_request_id;
  const processing = busy || !!resumedRequest;
  const currentFlight =
    flight && busy
      ? flight
      : resumedRequest && selected
        ? { session: selected, request: resumedRequest }
        : null;
  useEffect(() => {
    if (messages.length > 0 && nearBottom.current) {
      end.current?.scrollIntoView({ behavior: "instant", block: "end" });
    }
  }, [messages.length, busy]);
  async function send(event: FormEvent) {
    event.preventDefault();
    if (documentBusy || processing || (!draft.trim() && !pending.current))
      return;
    setDocumentsOpen(false);
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
          document_ids: sources.session === selected ? sources.ids : [],
          mode,
          flags: requestFlags(mode, flags),
          ...(mode === "optimized"
            ? {
                policy_id:
                  source === "live"
                    ? "quality-guarded-v3"
                    : "foundation-mock-v3",
              }
            : {}),
        };
      }
      setFlight({
        session: pending.current.session_id,
        request: pending.current.client_request_id,
      });
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
  const locked = processing || retrying || documentBusy;
  useEffect(() => {
    onBusy(processing || retrying || documentBusy);
  }, [processing, retrying, documentBusy, onBusy]);
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
      <div
        className="conversation-scroll"
        aria-live="polite"
        aria-busy={processing}
        onScroll={(e) => {
          const el = e.currentTarget;
          nearBottom.current =
            el.scrollHeight - el.scrollTop - el.clientHeight < 100;
        }}
      >
        <div className="scroll-inner-wrapper">
          <DocumentsPanel
            key={selected || "new"}
            open={documentsOpen}
            onOpenChange={setDocumentsOpen}
            sessionId={selected}
            userId={userId}
            createSession={() => createSession()}
            disabled={busy || retrying}
            onSelected={selectSources}
            onBusy={setDocumentBusy}
          />
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
              <div className="welcome-hero-wrap">
                <div className="hero-glow" />
                <span className="welcome-mark">
                  <Image
                    src="/brand/ou-logo.jpg"
                    width={92}
                    height={56}
                    alt="OU"
                    priority
                  />
                </span>
              </div>
              <p className="eyebrow">SMART LLM OPTIMIZER</p>
              <h1>{t("welcome")}</h1>
              <p>{t("welcomeHint")}</p>
              <div className="welcome-tags">
                <span>
                  <Check size={14} />
                  {t("private")}
                </span>
              </div>
              <div className="welcome-prompts">
                <button
                  type="button"
                  className="welcome-prompt-card"
                  onClick={() => setDraft(t("promptQnaSample"))}
                >
                  <div className="prompt-icon-wrap">
                    <BookOpen size={18} />
                  </div>
                  <div className="prompt-content">
                    <strong>{t("promptQna")}</strong>
                    <p>{t("promptQnaHint")}</p>
                  </div>
                  <ArrowUpRight className="prompt-arrow-icon" size={16} />
                </button>
                <button
                  type="button"
                  className="welcome-prompt-card"
                  onClick={() => setDraft(t("promptSummarySample"))}
                >
                  <div className="prompt-icon-wrap">
                    <Sparkles size={18} />
                  </div>
                  <div className="prompt-content">
                    <strong>{t("promptSummary")}</strong>
                    <p>{t("promptSummaryHint")}</p>
                  </div>
                  <ArrowUpRight className="prompt-arrow-icon" size={16} />
                </button>
                <button
                  type="button"
                  className="welcome-prompt-card"
                  onClick={() => setDraft(t("promptCompareSample"))}
                >
                  <div className="prompt-icon-wrap">
                    <GitCompare size={18} />
                  </div>
                  <div className="prompt-content">
                    <strong>{t("promptCompare")}</strong>
                    <p>{t("promptCompareHint")}</p>
                  </div>
                  <ArrowUpRight className="prompt-arrow-icon" size={16} />
                </button>
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
                    </header>
                    <div className="message-content">
                      {message.role === "assistant" ? (
                        <FormattedMessage
                          content={message.content}
                          legacyMock={source === "mock"}
                        />
                      ) : (
                        message.content
                      )}
                    </div>
                    {message.role === "assistant" && message.request_id && (
                      <MessageMetrics requestId={message.request_id} />
                    )}
                  </div>
                </article>
              ))}
            </div>
          )}
          {(processing || (!!error && !!currentFlight)) && (
            <div className="thinking" role="status">
              {currentFlight ? (
                <ProcessingProgress
                  sessionId={currentFlight.session}
                  clientRequestId={currentFlight.request}
                  active
                />
              ) : (
                <>
                  <Spinner />
                  {t("sending")}
                </>
              )}
            </div>
          )}
          <div ref={end} />
        </div>
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
                processing ||
                documentBusy ||
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
          <span>
            {t(source === "mock" ? "simulationMode" : "liveMode")} ·{" "}
            {sources.session === selected ? sources.ids.length : 0}{" "}
            {mvp("sourceSelected")}
          </span>
        </div>
        <p className="mock-disclosure">
          {source === "mock" ? t("mockHint") : mvp("noOptimizer")}
        </p>
      </div>
    </section>
  );
}
