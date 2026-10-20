"use client";
import { useEffect, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useTranslations } from "next-intl";
import { FileUp, FileText, Trash2, Eye } from "lucide-react";
import { api, unwrap, ApiError } from "@/lib/api";
import { Drawer, ErrorNotice, Spinner } from "./ui";

export function DocumentsPanel({
  open,
  onOpenChange,
  sessionId,
  userId,
  createSession,
  disabled,
  onSelected,
  onBusy,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  sessionId: string | null;
  userId: string;
  createSession: () => Promise<string>;
  disabled: boolean;
  onSelected: (ids: string[]) => void;
  onBusy: (busy: boolean) => void;
}) {
  const t = useTranslations("MVP");
  const client = useQueryClient();
  const [selected, setSelected] = useState<string[]>([]);
  const [uploading, setUploading] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<unknown>();
  const [preview, setPreview] = useState<string | null>(null);
  const [budget, setBudget] = useState("0.50");
  const [instruction, setInstruction] = useState("");
  const docs = useQuery({
    queryKey: ["documents", userId, sessionId],
    enabled: !!sessionId,
    queryFn: async () =>
      unwrap(
        await api.GET("/v1/sessions/{session_id}/documents", {
          params: { path: { session_id: sessionId! } },
        }),
      ),
  });
  const jobs = useQuery({
    queryKey: ["document-jobs", userId, sessionId],
    enabled: !!sessionId,
    refetchInterval: 1000,
    queryFn: async () =>
      unwrap(
        await api.GET("/v1/sessions/{session_id}/document-jobs", {
          params: { path: { session_id: sessionId! } },
        }),
      ),
  });
  const readyIds = selected
    .filter((id) => docs.data?.find((d) => d.id === id)?.status === "ready")
    .join(",");
  useEffect(() => {
    onSelected(readyIds ? readyIds.split(",") : []);
  }, [readyIds, onSelected]);
  const content = useQuery({
    queryKey: ["document-preview", userId, preview],
    enabled: !!preview,
    queryFn: async () =>
      unwrap(
        await api.GET("/v1/documents/{document_id}", {
          params: { path: { document_id: preview! } },
        }),
      ),
  });
  const active =
    uploading ||
    submitting ||
    !!jobs.data?.some((j) => ["pending", "running"].includes(j.status));
  const signature = jobs.data?.map((j) => j.id + ":" + j.status).join(",");
  useEffect(() => {
    onBusy(active);
  }, [active, onBusy]);
  useEffect(() => {
    void client.invalidateQueries({
      queryKey: ["documents", userId, sessionId],
    });
    void client.invalidateQueries({ queryKey: ["session", userId, sessionId] });
    void client.invalidateQueries({ queryKey: ["sessions", userId] });
    void client.invalidateQueries({ queryKey: ["usage", userId] });
  }, [signature, client, userId, sessionId]);
  function choose(ids: string[]) {
    setSelected(ids);
    onSelected(
      ids.filter(
        (id) => docs.data?.find((d) => d.id === id)?.status === "ready",
      ),
    );
  }
  async function upload(file: File) {
    setUploading(true);
    setError(undefined);
    try {
      if (file.size > 10 * 1024 * 1024)
        throw new ApiError("DOCUMENT_TOO_LARGE");
      const sid = sessionId || (await createSession());
      const form = new FormData();
      form.append("file", file);
      const response = await fetch(
        `/api/v1/sessions/${encodeURIComponent(sid)}/documents`,
        { method: "POST", body: form, credentials: "same-origin" },
      );
      if (response.status === 401)
        window.dispatchEvent(new Event("auth-expired"));
      if (!response.ok) {
        const body = await response.json();
        throw new ApiError(
          body.error?.code || "UPLOAD_FAILED",
          response.status,
        );
      }
      await client.invalidateQueries({ queryKey: ["documents", userId, sid] });
    } catch (reason) {
      setError(reason);
    } finally {
      setUploading(false);
    }
  }
  async function run(task: "index" | "summarize" | "compare") {
    if (!sessionId || !selected.length) return;
    setSubmitting(true);
    setError(undefined);
    try {
      unwrap(
        await api.POST("/v1/sessions/{session_id}/document-jobs", {
          params: { path: { session_id: sessionId } },
          body: {
            client_request_id: crypto.randomUUID(),
            task,
            document_ids: selected,
            instruction,
            max_total_usd: budget,
          },
        }),
      );
      await client.invalidateQueries({
        queryKey: ["document-jobs", userId, sessionId],
      });
    } catch (reason) {
      setError(reason);
    } finally {
      setSubmitting(false);
    }
  }
  async function remove(id: string) {
    setError(undefined);
    try {
      unwrap(
        await api.DELETE("/v1/documents/{document_id}", {
          params: { path: { document_id: id } },
        }),
      );
      choose(selected.filter((v) => v !== id));
      await client.invalidateQueries({
        queryKey: ["documents", userId, sessionId],
      });
    } catch (reason) {
      setError(reason);
    }
  }
  const ready =
    selected.length > 0 &&
    selected.every(
      (id) => docs.data?.find((d) => d.id === id)?.status === "ready",
    );
  return (
    <details
      className="document-panel"
      open={open}
      onToggle={(event) => onOpenChange(event.currentTarget.open)}
    >
      <summary>
        <FileText size={16} />
        {t("documents")}
        <span className="muted">{docs.data?.length || 0}/5</span>
        {active && <Spinner />}
      </summary>
      <div className="document-body">
        <p className="muted">{t("documentsHint")}</p>
        <label
          className={`button upload-control ${active || disabled ? "is-disabled" : ""}`}
        >
          <FileUp size={16} />
          {uploading ? t("processing") : t("upload")}
          <input
            aria-label={t("upload")}
            type="file"
            accept=".txt,.md,.pdf,.docx"
            disabled={active || disabled}
            onChange={(e) => {
              const file = e.target.files?.[0];
              if (file) void upload(file);
              e.target.value = "";
            }}
          />
        </label>
        {error !== undefined && <ErrorNotice error={error} />}
        {docs.isError && <ErrorNotice error={docs.error} />}
        {jobs.isError && <ErrorNotice error={jobs.error} />}
        {!docs.data?.length && <p className="muted">{t("noDocuments")}</p>}
        <div className="document-list">
          {docs.data?.map((doc) => (
            <div className="document-row" key={doc.id}>
              <label>
                <input
                  type="checkbox"
                  aria-label={`${t("selectSource")} ${doc.filename}`}
                  checked={selected.includes(doc.id)}
                  disabled={active || disabled}
                  onChange={(e) =>
                    choose(
                      e.target.checked
                        ? [...selected, doc.id]
                        : selected.filter((id) => id !== doc.id),
                    )
                  }
                />
                <span>
                  {doc.filename}
                  <small>
                    {t.has(doc.status) ? t(doc.status) : doc.status} ·{" "}
                    {doc.characters.toLocaleString()} chars · {doc.chunks}{" "}
                    chunks
                  </small>
                </span>
              </label>
              <button
                className="icon-button"
                aria-label={`${t("preview")} ${doc.filename}`}
                onClick={() => setPreview(doc.id)}
              >
                <Eye size={15} />
              </button>
              <button
                className="icon-button"
                aria-label={`${t("delete")} ${doc.filename}`}
                disabled={active || disabled}
                onClick={() => void remove(doc.id)}
              >
                <Trash2 size={15} />
              </button>
            </div>
          ))}
        </div>
        {!!selected.length && (
          <div className="document-controls">
            <label>
              {t("budget")}
              <input
                type="number"
                min="0.001"
                max="1"
                step="0.01"
                value={budget}
                disabled={active || disabled}
                onChange={(e) => setBudget(e.target.value)}
              />
            </label>
            <label>
              {t("instruction")}
              <input
                value={instruction}
                maxLength={5000}
                disabled={active || disabled}
                onChange={(e) => setInstruction(e.target.value)}
              />
            </label>
            <div className="document-actions">
              <button
                className="button small"
                disabled={active || disabled}
                onClick={() => void run("index")}
              >
                {t("index")}
              </button>
              <button
                className="button small"
                disabled={active || disabled || !ready}
                onClick={() => void run("summarize")}
              >
                {t("summarize")}
              </button>
              <button
                className="button small"
                disabled={active || disabled || !ready || selected.length < 2}
                onClick={() => void run("compare")}
              >
                {t("compare")}
              </button>
            </div>
            <small className="muted">{t("jobBudgetHint")}</small>
          </div>
        )}
        {!!jobs.data?.length && (
          <div className="document-jobs">
            <h3>{t("jobs")}</h3>
            {jobs.data.slice(0, 5).map((job) => (
              <div key={job.id}>
                <span>
                  {t(job.task)} ·{" "}
                  {t.has(job.status) ? t(job.status) : job.status}
                </span>
                <small>
                  {job.completed_steps}/{job.total_steps} · {t("coverage")}
                </small>
                {job.total_steps > 0 && (
                  <progress
                    max={job.total_steps}
                    value={job.completed_steps}
                    aria-label={t("coverage")}
                  />
                )}
                {job.error_code && (
                  <p className="field-error">
                    {t("partial")} · {job.error_code}
                  </p>
                )}
              </div>
            ))}
          </div>
        )}
      </div>
      <Drawer
        open={!!preview}
        onOpenChange={(open) => !open && setPreview(null)}
        title={t("previewTitle")}
      >
        {content.isLoading && <Spinner />}
        {content.isError && <ErrorNotice error={content.error} />}
        {content.data && (
          <>
            <h3>{content.data.filename}</h3>
            <pre className="document-preview">{content.data.text}</pre>
          </>
        )}
      </Drawer>
    </details>
  );
}
