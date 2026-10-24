"use client";
import Image from "next/image";
import Link from "next/link";
import * as Dialog from "@radix-ui/react-dialog";
import { useRouter, useSearchParams } from "next/navigation";
import {
  useInfiniteQuery,
  useQuery,
  useQueryClient,
} from "@tanstack/react-query";
import {
  Plus,
  MessageSquare,
  LayoutDashboard,
  Layers,
  PanelLeft,
  LogOut,
  Trash2,
  RefreshCw,
  History,
  FlaskConical,
} from "lucide-react";
import { useState } from "react";
import { useTranslations } from "next-intl";
import { api, unwrap, type User, type SessionInfo } from "@/lib/api";
import { LanguageSwitch } from "./language-switch";
import { Drawer, ErrorNotice, Spinner } from "./ui";
import dynamic from "next/dynamic";
const TraceInspector = dynamic(() =>
  import("./trace-inspector").then((m) => m.TraceInspector),
);
const OverviewPanel = dynamic(
  () => import("./overview").then((m) => m.OverviewPanel),
  {
    loading: () => (
      <div className="metric-skeleton">
        <Spinner />
      </div>
    ),
  },
);
import { ChatPanel } from "./chat-panel";
const OptimizerLab = dynamic(
  () => import("./optimizer-lab").then((m) => m.OptimizerLab),
  {
    loading: () => (
      <div className="metric-skeleton">
        <Spinner />
      </div>
    ),
  },
);
const PipelineFlow3D = dynamic(
  () => import("./3d/pipeline-flow-3d").then((m) => m.PipelineFlow3D),
  {
    loading: () => (
      <div className="flex h-full w-full items-center justify-center">
        <Spinner />
      </div>
    ),
    ssr: false,
  },
);

export function AuthenticatedWorkspace({
  user,
  dashboard,
  research = false,
  pipeline = false,
  onLogout,
}: {
  user: User;
  dashboard: boolean;
  research?: boolean;
  pipeline?: boolean;
  onLogout: () => void;
}) {
  const t = useTranslations("App");
  const lab = useTranslations("Research");
  const client = useQueryClient();
  const router = useRouter();
  const models = useQuery({
    queryKey: ["models", user.id],
    queryFn: async () => unwrap(await api.GET("/v1/models")),
  });
  const source = models.data?.[0]?.execution_source ?? "mock";
  const queryParamSession = useSearchParams().get("session");
  const [createdSession, setCreatedSession] = useState<string | null>(null);
  const selected = queryParamSession ?? createdSession;
  function setSelected(id: string | null) {
    setCreatedSession(id);
    router.replace(id ? `/?session=${encodeURIComponent(id)}` : "/");
  }
  const [mobileOpen, setMobileOpen] = useState(false);
  const [trace, setTrace] = useState<string | null>(null);
  const [deleting, setDeleting] = useState<SessionInfo | null>(null);
  const [operation, setOperation] = useState(false);
  const [error, setError] = useState<unknown>();
  const [requestBusy, setRequestBusy] = useState(false);
  const sessions = useInfiniteQuery({
    queryKey: ["sessions", user.id],
    initialPageParam: 0,
    queryFn: async ({ pageParam }) =>
      unwrap(
        await api.GET("/v1/sessions", {
          params: { query: { offset: pageParam, limit: 50 } },
        }),
      ),
    getNextPageParam: (last, pages) =>
      last.length === 50 ? pages.length * 50 : undefined,
  });
  const sessionRows = sessions.data?.pages.flat() ?? [];
  const mvp = useTranslations("MVP");
  async function newSession(title?: string) {
    const created = unwrap(
      await api.POST("/v1/sessions", {
        body: { title: title?.slice(0, 80) || t("newChat") },
      }),
    );
    await client.invalidateQueries({ queryKey: ["sessions", user.id] });
    setSelected(created.id);
    setMobileOpen(false);
    return created.id;
  }
  async function create() {
    setOperation(true);
    setError(undefined);
    try {
      await newSession();
    } catch (e) {
      setError(e);
    } finally {
      setOperation(false);
    }
  }
  async function remove() {
    if (!deleting) return;
    setOperation(true);
    setError(undefined);
    try {
      unwrap(
        await api.DELETE("/v1/sessions/{session_id}", {
          params: { path: { session_id: deleting.id } },
        }),
      );
      if (selected === deleting.id) setSelected(null);
      setDeleting(null);
      setTrace(null);
      client.removeQueries({ queryKey: ["session", user.id, deleting.id] });
      client.removeQueries({ queryKey: ["trace"] });
      await client.invalidateQueries({ queryKey: ["sessions", user.id] });
      await client.invalidateQueries({ queryKey: ["overview", user.id] });
    } catch (e) {
      setError(e);
    } finally {
      setOperation(false);
    }
  }
  async function logout() {
    setOperation(true);
    setError(undefined);
    try {
      unwrap(await api.POST("/v1/auth/logout"));
      await client.cancelQueries();
      onLogout();
    } catch (e) {
      setError(e);
      setOperation(false);
    }
  }
  const navigation = (
    <>
      <div className="brand">
        <Image
          src="/brand/ou-logo.jpg"
          alt="OU"
          width={51}
          height={31}
          priority
        />
        <div>
          <strong>Smart LLM</strong>
        </div>
      </div>
      <button
        className="new-chat button primary"
        onClick={create}
        disabled={operation || requestBusy}
      >
        <Plus size={18} />
        {t("newChat")}
      </button>
      <nav className="main-nav" aria-label={t("workspace")}>
        <Link
          href="/"
          className={!dashboard && !research && !pipeline ? "active" : ""}
        >
          <MessageSquare size={18} />
          {t("chat")}
        </Link>
        <Link href="/pipeline" className={pipeline ? "active" : ""}>
          <Layers size={18} />
          {t("pipeline")}
        </Link>
        {user.role === "admin" && (
          <Link href="/research" className={research ? "active" : ""}>
            <FlaskConical size={18} />
            {lab("nav")}
          </Link>
        )}
        <Link href="/dashboard" className={dashboard ? "active" : ""}>
          <LayoutDashboard size={18} />
          {t("dashboard")}
        </Link>
      </nav>
      <div className="history-heading">
        <span>{t("history")}</span>
        <button
          className="icon-button"
          aria-label={t("refreshHistory")}
          onClick={() => sessions.refetch()}
        >
          <RefreshCw size={14} />
        </button>
      </div>
      <div className="history-list">
        {sessions.isLoading && <Spinner />}
        {sessions.isError && <ErrorNotice error={sessions.error} />}
        {!sessions.isLoading && !sessionRows.length && (
          <div className="history-empty">
            <History size={21} />
            <strong>{t("noHistory")}</strong>
            <p>{t("noHistoryHint")}</p>
          </div>
        )}
        {sessionRows.map((session) => (
          <div
            className={`history-row ${selected === session.id ? "selected" : ""}`}
            key={session.id}
          >
            {dashboard || pipeline ? (
              <Link
                className="history-select"
                href={`/?session=${encodeURIComponent(session.id)}`}
              >
                <MessageSquare size={15} />
                <span>{session.title}</span>
              </Link>
            ) : (
              <button
                className="history-select"
                onClick={() => {
                  setSelected(session.id);
                  setMobileOpen(false);
                }}
                disabled={requestBusy}
              >
                <MessageSquare size={15} />
                <span>{session.title}</span>
                {session.active && <Spinner />}
              </button>
            )}
            <button
              className="icon-button delete-button"
              aria-label={`${t("delete")} ${session.title}`}
              disabled={requestBusy || operation}
              onClick={() => {
                setError(undefined);
                setDeleting(session);
              }}
            >
              <Trash2 size={14} />
            </button>
          </div>
        ))}
        {sessions.hasNextPage && (
          <button
            className="button small"
            disabled={sessions.isFetchingNextPage || requestBusy}
            onClick={() => void sessions.fetchNextPage()}
          >
            {sessions.isFetchingNextPage ? <Spinner /> : mvp("next")}
          </button>
        )}
      </div>
      <div className="sidebar-footer">
        <div className="foundation-note">
          <span className="environment-dot">{t("foundation")}</span>
          <p>{t("school")}</p>
        </div>
        <div className="user-row">
          <span className="avatar">
            {user.username.slice(0, 1).toUpperCase()}
          </span>
          <div>
            <strong>{user.username}</strong>
            <span>{t(user.role === "admin" ? "roleAdmin" : "roleUser")}</span>
          </div>
          <button
            className="icon-button"
            onClick={logout}
            disabled={operation || requestBusy}
            aria-label={t("logout")}
          >
            <LogOut size={18} />
          </button>
        </div>
      </div>
    </>
  );
  return (
    <div className="app-shell">
      <aside className="sidebar">{navigation}</aside>
      <Drawer
        open={mobileOpen}
        onOpenChange={setMobileOpen}
        title={t("workspace")}
        side="left"
      >
        <div className="mobile-navigation">{navigation}</div>
      </Drawer>
      <main className="main-area">
        <header className="topbar">
          <div className="topbar-title">
            <button
              className="icon-button mobile-menu"
              onClick={() => setMobileOpen(true)}
              aria-label={t("menu")}
            >
              <PanelLeft size={20} />
            </button>
            <span>{t("workspace")}</span>
            <span className="slash">/</span>
            <strong>
              {pipeline
                ? t("pipeline")
                : research
                  ? lab("nav")
                  : dashboard
                    ? t("dashboard")
                    : t("chat")}
            </strong>
          </div>
          <div className="topbar-actions">
            <span className="mock-badge">
              <span />
              {t(
                pipeline
                  ? "pipeline"
                  : research
                    ? "researchArea"
                    : source === "mock"
                      ? "simulationMode"
                      : "liveMode",
              )}
            </span>
            <LanguageSwitch />
          </div>
        </header>
        {error !== undefined && !deleting && (
          <div className="shell-error">
            <ErrorNotice error={error} />
          </div>
        )}
        {pipeline ? (
          <PipelineFlow3D />
        ) : research ? (
          <OptimizerLab user={user} />
        ) : dashboard ? (
          <OverviewPanel user={user} onTrace={setTrace} />
        ) : (
          <ChatPanel
            userId={user.id}
            selected={selected}
            createSession={newSession}
            onTrace={setTrace}
            onBusy={setRequestBusy}
          />
        )}
      </main>
      <TraceInspector requestId={trace} onClose={() => setTrace(null)} />
      <Dialog.Root
        open={!!deleting}
        onOpenChange={(open) => {
          if (!open && !operation) setDeleting(null);
        }}
      >
        <Dialog.Portal>
          <Dialog.Overlay className="overlay" />
          <Dialog.Content className="confirm-dialog">
            <Trash2 size={24} />
            <Dialog.Title>{t("deleteTitle")}</Dialog.Title>
            <Dialog.Description>{t("deleteHint")}</Dialog.Description>
            {error !== undefined && <ErrorNotice error={error} />}
            <div className="dialog-actions">
              <Dialog.Close className="button" disabled={operation}>
                {t("cancel")}
              </Dialog.Close>
              <button
                className="button danger"
                disabled={operation}
                onClick={remove}
              >
                {operation ? <Spinner /> : null}
                {t("confirmDelete")}
              </button>
            </div>
          </Dialog.Content>
        </Dialog.Portal>
      </Dialog.Root>
    </div>
  );
}
