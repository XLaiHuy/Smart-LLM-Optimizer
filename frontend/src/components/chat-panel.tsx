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
  type ChatRequest,
  type Flags,
} from "@/lib/api";
import { DocumentsPanel } from "./documents-panel";
import { MessageMetrics } from "./message-metrics";
import { ProcessingProgress } from "./processing-progress";
import { FormattedMessage } from "./formatted-message";
import { ErrorNotice, Spinner } from "./ui";

export function getCleanModelName(configId: string, modelId?: string): string {
  if (!configId) return modelId || "";
  const map: Record<string, string> = {
    "groq-llama-3.3-70b-versatile": "Llama 3.3 70B (Groq)",
    "groq-qwen-2.5-coder-32b": "Qwen 2.5 Coder 32B (Groq)",
    "groq-llama-3.1-8b-instant": "Llama 3.1 8B (Groq)",
    "groq-gpt-oss-120b": "GPT OSS 120B (Groq)",
    "groq-qwen-3.8-27b": "Qwen 3.8 27B (Groq)",
    "groq-gpt-oss-20b": "GPT OSS 20B (Groq)",
    "openai/gpt-oss-120b": "GPT OSS 120B (Groq)",
    "qwen/qwen3.8-27b": "Qwen 3.8 27B (Groq)",
    "openai/gpt-oss-20b": "GPT OSS 20B (Groq)",
    "openrouter-gemini-2.0-flash-exp-free": "Gemini 2.0 Flash (Free)",
    "openrouter-deepseek-r1-free": "DeepSeek R1 (Free)",
    "openrouter-meta-llama-3.3-70b-instruct-free": "Llama 3.3 70B (Free)",
    "openai-gpt-6-luna": "GPT-6 Luna (OpenAI)",
    "openai-gpt-5.6-terra": "GPT-5.6 Terra (OpenAI)",
    "openai-gpt-6.1-sol": "GPT-6.1 Sol (OpenAI)",
    "mock-baseline": "Mock Baseline (Default)",
    "mock-small": "Mock Fast (Small)",
    "mock-quality": "Mock Frontier (Quality)",
    "gpt-6-luna": "GPT-6 Luna (OpenAI)",
    "gpt-5.6-terra": "GPT-5.6 Terra (OpenAI)",
    "gpt-6.1-sol": "GPT-6.1 Sol (OpenAI)",
  };
  if (map[configId]) return map[configId];
  if (modelId && map[modelId]) return map[modelId];
  const lower = configId.toLowerCase();
  if (lower.includes("luna")) return "GPT-6 Luna (OpenAI)";
  if (lower.includes("terra")) return "GPT-5.6 Terra (OpenAI)";
  if (lower.includes("sol")) return "GPT-6.1 Sol (OpenAI)";
  if (lower.includes("120b")) return "GPT OSS 120B (Groq)";
  if (lower.includes("3.8-27b")) return "Qwen 3.8 27B (Groq)";
  if (lower.includes("20b")) return "GPT OSS 20B (Groq)";
  if (lower.includes("llama-3.3-70b") && lower.includes("groq")) return "Llama 3.3 70B (Groq)";
  if (lower.includes("llama-3.3-70b-versatile")) return "Llama 3.3 70B (Groq)";
  if (lower.includes("qwen-2.5-coder-32b")) return "Qwen 2.5 Coder 32B (Groq)";
  if (lower.includes("llama-3.1-8b-instant") || (lower.includes("llama-3.1-8b") && lower.includes("groq"))) return "Llama 3.1 8B (Groq)";
  if (lower.includes("gemini-2.0-flash")) return "Gemini 2.0 Flash (Free)";
  if (lower.includes("deepseek-r1")) return "DeepSeek R1 (Free)";
  if (lower.includes("llama-3.3-70b")) return "Llama 3.3 70B (Free)";
  return modelId || configId;
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
    const nonEmbeddings = models.data.filter((m) => m.endpoint !== "embeddings");
    const nonMock = nonEmbeddings.filter(
      (m) =>
        !m.config_id.toLowerCase().startsWith("mock-") &&
        !m.model_id.toLowerCase().startsWith("mock-"),
    );
    return nonMock.length > 0 ? nonMock : nonEmbeddings;
  }, [models.data]);

  const [candidateOverride, setCandidateOverride] = useState<string | null>(null);

  const selectedCandidate = useMemo(() => {
    if (candidateOverride && genuineModels.some((m) => m.config_id === candidateOverride)) {
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
  const scrollContainerRef = useRef<HTMLDivElement>(null);
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
  const lastContent = messages[messages.length - 1]?.content;

  // Stable anchor to bottom without ancestor container jitter
  useEffect(() => {
    if (messages.length > 0 && nearBottom.current && scrollContainerRef.current) {
      scrollContainerRef.current.scrollTop = scrollContainerRef.current.scrollHeight;
    }
  }, [messages.length, busy, lastContent]);

  useEffect(() => {
    nearBottom.current = true;
    if (scrollContainerRef.current) {
      scrollContainerRef.current.scrollTop = scrollContainerRef.current.scrollHeight;
    }
  }, [selected]);
  async function send(event: FormEvent) {
    event.preventDefault();
    if (documentBusy || processing || (!draft.trim() && !pending.current))
      return;
    setDocumentsOpen(false);
    setBusy(true);
    onBusy(true);
    setError(undefined);
    nearBottom.current = true;
    if (scrollContainerRef.current) {
      scrollContainerRef.current.scrollTop = scrollContainerRef.current.scrollHeight;
    }
    try {
      if (!pending.current) {
        const sessionId = selected || (await createSession(draft));
        pending.current = {
          session_id: sessionId,
          client_request_id: crypto.randomUUID(),
          message: draft,
          document_ids: sources.session === selected ? sources.ids : [],
          constraints: { deadline_ms: 60000 },
          mode,
          flags: requestFlags(mode, flags),
          ...(mode === "optimized"
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
          {!detail.isLoading && !messages.length && !detail.isError && (
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
                    {genuineModels.map((m) => (
                      <option key={m.config_id} value={m.config_id}>
                        {getCleanModelName(m.config_id, m.model_id)}
                      </option>
                    ))}
                  </select>
                  <ChevronDown size={13} className="select-arrow" />
                </div>
                <span
                  className="mode-tag-pill manual"
                  title="Gửi trực tiếp đến mô hình đã chọn, bỏ qua toàn bộ module tối ưu hóa"
                >
                  🎯 Chuẩn (Trực tiếp)
                </span>
              </div>
            ) : (
              <div className="auto-model-display">
                <span
                  className="mode-tag-pill auto"
                  title="Tự động phân tích đa chiều và chọn mô hình tối ưu"
                >
                  ⚡ Tối ưu tự động (ML Router)
                </span>
              </div>
            )}
          </div>
        </div>

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
                  Chế độ trực tiếp · {getCleanModelName(selectedCandidate, selectedCandidate)}
                </span>
              ) : (
                <span className="active-mode-subtext">
                  Tối ưu tự động · ML Multi-Model Router
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
