"use client";
import Image from "next/image";
import * as Switch from "@radix-ui/react-switch";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import {
  ArrowUp,
  ArrowUpRight,
  SlidersHorizontal,
  RefreshCw,
  Sparkles,
  BookOpen,
  GitCompare,
  ChevronDown,
  Zap,
} from "lucide-react";
import {
  useCallback,
  useEffect,
  useMemo,
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
  CHAT_DEADLINE_MS,
  type ChatRequest,
  type ChatResponse,
  type Flags,
} from "@/lib/api";
import { isTransportUncertain, recoverChat } from "@/lib/chat-recovery";
import { parseChatPreferences } from "@/lib/workspace-preferences";
import { DocumentsPanel } from "./documents-panel";
import { MessageMetrics } from "./message-metrics";
import { ProcessingProgress } from "./processing-progress";
import { FormattedMessage } from "./formatted-message";
import { ErrorNotice, Spinner } from "./ui";

import { getCleanModelName } from "@/lib/model-name";
export { getCleanModelName } from "@/lib/model-name";

export interface ShowcasePreset {
  id: string;
  labelKey: "presetMath" | "presetCode" | "presetReasoning" | "presetMemory";
  promptKey:
    | "presetMathPrompt"
    | "presetCodePrompt"
    | "presetReasoningPrompt"
    | "presetMemoryPrompt";
}

export const SHOWCASE_PRESETS: readonly ShowcasePreset[] = [
  {
    id: "math",
    labelKey: "presetMath",
    promptKey: "presetMathPrompt",
  },
  {
    id: "code",
    labelKey: "presetCode",
    promptKey: "presetCodePrompt",
  },
  {
    id: "reasoning",
    labelKey: "presetReasoning",
    promptKey: "presetReasoningPrompt",
  },
  {
    id: "memory",
    labelKey: "presetMemory",
    promptKey: "presetMemoryPrompt",
  },
] as const;

export function QuickShowcaseBar({
  disabled,
  onSelectPreset,
}: {
  disabled?: boolean;
  onSelectPreset: (promptText: string) => void;
}) {
  const t = useTranslations("App");
  const [collapsed, setCollapsed] = useState(false);

  return (
    <div
      className={`quick-showcase-bar ${collapsed ? "collapsed" : ""}`}
      role="region"
      aria-label={t("showcaseTitle")}
    >
      <div className="quick-showcase-header">
        <div className="quick-showcase-title">
          <Sparkles size={13} className="quick-showcase-icon" />
          <span>{t("showcaseTitle")}</span>
        </div>
        <button
          type="button"
          className="quick-showcase-toggle"
          onClick={() => setCollapsed(!collapsed)}
          aria-expanded={!collapsed}
          title={collapsed ? t("showcaseShow") : t("showcaseHide")}
        >
          <span>{collapsed ? t("showcaseShow") : t("showcaseHide")}</span>
          <ChevronDown
            size={13}
            className={`quick-showcase-chevron ${collapsed ? "" : "expanded"}`}
          />
        </button>
      </div>

      {!collapsed && (
        <div className="quick-showcase-presets">
          <p
            className="muted"
            style={{ flexBasis: "100%", gridColumn: "1 / -1" }}
          >
            {t("memorySetupHint")}
          </p>
          {SHOWCASE_PRESETS.map((preset) => {
            const promptText = t(preset.promptKey);
            return (
              <button
                key={preset.id}
                type="button"
                className="quick-showcase-btn"
                disabled={disabled}
                onClick={() => onSelectPreset(promptText)}
                title={promptText}
              >
                <span>{t(preset.labelKey)}</span>
              </button>
            );
          })}
        </div>
      )}
    </div>
  );
}

export function ChatPanel({
  userId,
  selected,
  createSession,
  onBusy,
  onTrace,
}: {
  userId: string;
  selected: string | null;
  createSession: (title?: string) => Promise<string>;
  onTrace: (id: string) => void;
  onBusy: (busy: boolean) => void;
}) {
  const t = useTranslations("App");
  const client = useQueryClient();
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
  const genuineModels = useMemo(() => {
    if (!models.data) return [];
    const nonEmbeddings = models.data.filter(
      (m) => m.endpoint !== "embeddings",
    );
    const nonMock = nonEmbeddings.filter(
      (m) =>
        !m.config_id.toLowerCase().startsWith("mock-") &&
        !m.model_id.toLowerCase().startsWith("mock-"),
    );
    return nonMock.length > 0 ? nonMock : nonEmbeddings;
  }, [models.data]);

  const tieredModels = useMemo(() => {
    const fast: typeof genuineModels = [];
    const code: typeof genuineModels = [];
    const reasoning: typeof genuineModels = [];

    for (const m of genuineModels) {
      const lower = (m.config_id + " " + (m.model_id || "")).toLowerCase();
      if (
        lower.includes("coder") ||
        lower.includes("qwen-2.5-coder") ||
        lower.includes("3.8-27b") ||
        lower.includes("sol")
      ) {
        code.push(m);
      } else if (
        lower.includes("70b") ||
        lower.includes("120b") ||
        lower.includes("r1") ||
        lower.includes("terra") ||
        lower.includes("reasoning") ||
        lower.includes("astra")
      ) {
        reasoning.push(m);
      } else {
        fast.push(m);
      }
    }
    return { fast, code, reasoning };
  }, [genuineModels]);

  const [candidateOverride, setCandidateOverride] = useState<string | null>(
    null,
  );

  const selectedCandidate = useMemo(() => {
    if (
      candidateOverride &&
      genuineModels.some((m) => m.config_id === candidateOverride)
    ) {
      return candidateOverride;
    }
    const preferred = genuineModels.find(
      (m) => m.config_id === "groq-llama-3.3-70b-versatile",
    );
    if (preferred) return preferred.config_id;
    if (genuineModels.length > 0) return genuineModels[0].config_id;
    return candidateOverride || "groq-llama-3.3-70b-versatile";
  }, [genuineModels, candidateOverride]);

  const [draft, setDraft] = useState("");
  const [mode, setMode] = useState<"baseline" | "optimized">("optimized");
  const [preferencesLoaded, setPreferencesLoaded] = useState(false);
  const [flags, setFlags] = useState<Flags>(allFlags);
  const [configOpen, setConfigOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const [pendingPrompt, setPendingPrompt] = useState<string | null>(null);
  const [flight, setFlight] = useState<{
    session: string;
    request: string;
  } | null>(null);
  const [error, setError] = useState<unknown>();
  const [retrying, setRetrying] = useState(false);
  const pending = useRef<ChatRequest | null>(null);
  const sending = useRef(false);
  const scrollContainerRef = useRef<HTMLDivElement>(null);
  const end = useRef<HTMLDivElement>(null);
  const nearBottom = useRef(true);

  useEffect(() => {
    const timer = window.setTimeout(() => {
      const saved = parseChatPreferences(
        window.localStorage.getItem(`smart-llm:chat-preferences:${userId}`),
      );
      if (saved) {
        setMode(saved.mode);
        setCandidateOverride(saved.candidate);
      }
      try {
        const defaults = JSON.parse(
          window.localStorage.getItem(`smart-llm:flags:${userId}`) || "null",
        );
        if (
          defaults &&
          Object.keys(allFlags).every(
            (key) => typeof defaults[key] === "boolean",
          )
        )
          setFlags(defaults);
      } catch {
        /* A broken local preference never blocks chat. */
      }
      setPreferencesLoaded(true);
    }, 0);
    return () => window.clearTimeout(timer);
  }, [userId]);

  useEffect(() => {
    if (!preferencesLoaded) return;
    window.localStorage.setItem(
      `smart-llm:chat-preferences:${userId}`,
      JSON.stringify({ mode, candidate: selectedCandidate }),
    );
  }, [preferencesLoaded, mode, selectedCandidate, userId]);

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
    flight && (busy || retrying)
      ? flight
      : resumedRequest && selected
        ? { session: selected, request: resumedRequest }
        : null;
  const lastContent = messages[messages.length - 1]?.content;
  const acceptAnswer = useCallback(
    async (answer: ChatResponse) => {
      pending.current = null;
      setError(undefined);
      setRetrying(false);
      setPendingPrompt(null);
      setDraft("");
      await client.invalidateQueries({ queryKey: ["session", userId] });
      await client.invalidateQueries({ queryKey: ["sessions", userId] });
      await client.invalidateQueries({ queryKey: ["overview", userId] });
      client.setQueryData(["trace", userId, answer.request_id], answer);
      client.setQueryData(["trace", answer.request_id], answer);
    },
    [client, userId],
  );

  useEffect(() => {
    const attempt = pending.current;
    if (!retrying || !attempt) return;
    let cancelled = false;
    let timer: ReturnType<typeof setTimeout>;
    const stopAt = Date.now() + CHAT_DEADLINE_MS + 20000;
    const poll = async () => {
      try {
        const recovered = await recoverChat(attempt);
        if (cancelled || pending.current !== attempt) return;
        if (recovered.status === "succeeded") {
          await acceptAnswer(recovered.response);
          return;
        }
        if (recovered.status === "failed") {
          pending.current = null;
          setRetrying(false);
          setPendingPrompt(null);
          setError(recovered.error);
          await client.invalidateQueries({ queryKey: ["session", userId] });
          return;
        }
      } catch {
        /* Keep the same request; a failed status read never authorizes POST. */
      }
      if (!cancelled && pending.current === attempt && Date.now() < stopAt)
        timer = setTimeout(poll, 1000);
    };
    timer = setTimeout(poll, 750);
    return () => {
      cancelled = true;
      clearTimeout(timer);
    };
  }, [retrying, acceptAnswer, client, userId]);

  // Stable anchor to bottom without ancestor container jitter
  useEffect(() => {
    if ((messages.length > 0 || pendingPrompt) && scrollContainerRef.current) {
      if (nearBottom.current || busy) {
        end.current?.scrollIntoView({ behavior: "smooth" });
      }
    }
  }, [messages.length, busy, pendingPrompt, lastContent]);

  useEffect(() => {
    const timer = window.setTimeout(() => {
      nearBottom.current = true;
      setPendingPrompt(null);
      if (scrollContainerRef.current) {
        scrollContainerRef.current.scrollTop =
          scrollContainerRef.current.scrollHeight;
      }
    }, 0);
    return () => window.clearTimeout(timer);
  }, [selected]);

  async function submitPrompt(
    text: string,
    overrideMode?: "baseline" | "optimized",
  ) {
    if (
      sending.current ||
      documentBusy ||
      processing ||
      (!text.trim() && !pending.current)
    )
      return;
    sending.current = true;
    const effectiveMode = overrideMode || mode;
    if (overrideMode) setMode(overrideMode);
    setDocumentsOpen(false);
    setBusy(true);
    onBusy(true);
    setError(undefined);
    nearBottom.current = true;
    setPendingPrompt(pending.current?.message || text);
    try {
      if (!pending.current) {
        const sessionId = selected || (await createSession(text));
        pending.current = {
          session_id: sessionId,
          client_request_id: crypto.randomUUID(),
          message: text.trim(),
          document_ids: sources.session === selected ? sources.ids : [],
          constraints: { deadline_ms: CHAT_DEADLINE_MS },
          mode: effectiveMode,
          flags: requestFlags(effectiveMode, flags),
          ...(effectiveMode === "optimized"
            ? {
                policy_id:
                  source === "live"
                    ? "quality-guarded-v3"
                    : "foundation-mock-v3",
              }
            : selectedCandidate
              ? { policy_id: `fixed_candidate:${selectedCandidate}` }
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
      await acceptAnswer(answer);
    } catch (reason) {
      setError(
        isTransportUncertain(reason)
          ? new ApiError("TRANSPORT_UNCERTAIN", 502)
          : reason,
      );
      const uncertain =
        isTransportUncertain(reason) ||
        !(reason instanceof ApiError) ||
        [
          "REQUEST_IN_PROGRESS",
          "SESSION_BUSY",
          "IDEMPOTENCY_CONFLICT",
        ].includes(reason.code);
      setDraft(pending.current?.message || text);
      if (!uncertain) {
        pending.current = null;
        setPendingPrompt(null);
      }
      setRetrying(uncertain && pending.current !== null);
    } finally {
      sending.current = false;
      setBusy(false);
      onBusy(pending.current !== null);
    }
  }
  async function resendSessionPrompt(
    text: string,
    overrideMode?: "baseline" | "optimized",
  ) {
    await submitPrompt(text, overrideMode);
  }
  async function send(event: FormEvent) {
    event.preventDefault();
    await submitPrompt(draft);
  }
  const locked = processing || retrying || documentBusy;
  useEffect(() => {
    onBusy(processing || retrying || documentBusy);
  }, [processing, retrying, documentBusy, onBusy]);

  async function runPreset(promptText: string) {
    if (locked || !promptText.trim()) return;
    setDraft(promptText);
    await resendSessionPrompt(promptText, "optimized");
  }
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
                    {(mode !== "baseline" || key !== "router") && flags[key]
                      ? t("applied")
                      : t("disabled")}
                  </small>
                </span>
                <Switch.Root
                  className="switch"
                  checked={
                    mode === "baseline" && key === "router" ? false : flags[key]
                  }
                  disabled={locked || (mode === "baseline" && key === "router")}
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
        ref={scrollContainerRef}
        className="conversation-scroll"
        aria-live="polite"
        aria-busy={processing}
        onScroll={(e) => {
          const el = e.currentTarget;
          nearBottom.current =
            el.scrollHeight - el.scrollTop - el.clientHeight < 80;
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
          {!detail.isLoading &&
            !messages.length &&
            !detail.isError &&
            (selected &&
            detail.data?.title &&
            detail.data.title !== t("newChat") ? (
              <div className="empty-session-notice">
                <div className="empty-session-card">
                  <div className="empty-session-badge">
                    <Sparkles size={14} />
                    <span>{t("emptySessionBadge")}</span>
                  </div>
                  <h3>{detail.data.title}</h3>
                  <p>{t("emptySessionHint")}</p>
                  <div className="empty-session-actions">
                    <button
                      type="button"
                      className="button primary"
                      disabled={locked}
                      onClick={() => resendSessionPrompt(detail.data!.title)}
                    >
                      <ArrowUp size={16} />
                      <span>{t("emptySessionResend")}</span>
                    </button>
                    <button
                      type="button"
                      className="button"
                      disabled={locked}
                      onClick={() => setDraft(detail.data!.title)}
                    >
                      <span>{t("emptySessionLoad")}</span>
                    </button>
                  </div>
                </div>
              </div>
            ) : (
              <div className="welcome">
                <div className="welcome-hero-wrap">
                  <div className="hero-glow" />
                  <span className="welcome-mark">
                    <Image
                      src="/brand/ou-logo.jpg"
                      width={80}
                      height={48}
                      alt="OU"
                      priority
                    />
                  </span>
                </div>
                <p className="eyebrow">SMART LLM</p>
                <h1>{t("welcome")}</h1>
                <p>{t("welcomeHint")}</p>

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
            ))}
          {(!!messages.length || !!pendingPrompt) && (
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
                          isStreaming={
                            processing &&
                            currentFlight !== null &&
                            index === messages.length - 1
                          }
                        />
                      ) : (
                        message.content
                      )}
                    </div>
                    {message.role === "assistant" && message.request_id && (
                      <MessageMetrics
                        requestId={message.request_id}
                        onTrace={onTrace}
                      />
                    )}
                  </div>
                </article>
              ))}
              {pendingPrompt && (
                <article className="message user optimistic-message">
                  <div className="message-avatar user">
                    <span>U</span>
                  </div>
                  <div className="message-body">
                    <header>
                      <strong>{t("you")}</strong>
                      <span className="optimistic-pill">
                        {t("optimisticSending")}
                      </span>
                    </header>
                    <div className="message-content">{pendingPrompt}</div>
                  </div>
                </article>
              )}
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
        {/* Exterior 2-Mode Control Bar */}
        <div
          className="composer-mode-bar"
          role="region"
          aria-label="Routing Mode"
        >
          <div
            className="composer-mode-toggle"
            role="group"
            aria-label={t("mode")}
          >
            <button
              type="button"
              className={`mode-btn ${mode === "optimized" ? "active" : ""}`}
              aria-pressed={mode === "optimized"}
              disabled={locked}
              onClick={() => setMode("optimized")}
              title={t("autoHint")}
            >
              <Zap size={13} className="mode-icon" />
              <span>{t("modeAuto")}</span>
            </button>
            <button
              type="button"
              className={`mode-btn ${mode === "baseline" ? "active" : ""}`}
              aria-pressed={mode === "baseline"}
              disabled={locked}
              onClick={() => setMode("baseline")}
              title={t("standardHint")}
            >
              <SlidersHorizontal size={13} className="mode-icon" />
              <span>{t("modeStandard")}</span>
            </button>
          </div>

          <div className="composer-model-selection">
            {mode === "baseline" ? (
              <div className="manual-model-picker">
                <div className="select-wrapper">
                  <select
                    id="model-select"
                    value={selectedCandidate}
                    onChange={(e) => setCandidateOverride(e.target.value)}
                    disabled={locked}
                    className="model-select-dropdown"
                    aria-label={t("selectModel")}
                  >
                    {tieredModels.fast.length > 0 && (
                      <optgroup label={t("tierFast")}>
                        {tieredModels.fast.map((m) => (
                          <option key={m.config_id} value={m.config_id}>
                            {getCleanModelName(m.config_id, m.model_id)}
                          </option>
                        ))}
                      </optgroup>
                    )}
                    {tieredModels.code.length > 0 && (
                      <optgroup label={t("tierCode")}>
                        {tieredModels.code.map((m) => (
                          <option key={m.config_id} value={m.config_id}>
                            {getCleanModelName(m.config_id, m.model_id)}
                          </option>
                        ))}
                      </optgroup>
                    )}
                    {tieredModels.reasoning.length > 0 && (
                      <optgroup label={t("tierReasoning")}>
                        {tieredModels.reasoning.map((m) => (
                          <option key={m.config_id} value={m.config_id}>
                            {getCleanModelName(m.config_id, m.model_id)}
                          </option>
                        ))}
                      </optgroup>
                    )}
                  </select>
                  <ChevronDown size={13} className="select-arrow" />
                </div>
                <span
                  className="mode-tag-pill manual"
                  title={t("modeDirectHint")}
                >
                  {t("modeDirectPill")}
                </span>
              </div>
            ) : (
              <div className="auto-model-display">
                <span className="mode-tag-pill auto" title={t("modeAutoHint")}>
                  {t("modeAutoPill")}
                </span>
              </div>
            )}
          </div>
        </div>

        <QuickShowcaseBar disabled={locked} onSelectPreset={runPreset} />

        {error !== undefined && <ErrorNotice error={error} />}
        <form className={`composer ${busy ? "busy" : ""}`} onSubmit={send}>
          <label htmlFor="message" className="sr-only">
            {t("composer")}
          </label>
          <textarea
            id="message"
            className="composer-textarea"
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
            <div className="composer-bottom-info">
              {mode === "baseline" ? (
                <span className="active-mode-subtext">
                  {t("modeDirectSubtext", {
                    model: getCleanModelName(
                      selectedCandidate,
                      selectedCandidate,
                    ),
                  })}
                </span>
              ) : (
                <span className="active-mode-subtext">
                  {t("modeAutoSubtext")}
                </span>
              )}
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
        </div>
      </div>
    </section>
  );
}
