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
  PanelLeft,
  LogOut,
  Trash2,
  RefreshCw,
  History,
  Layers,
  Settings as SettingsIcon,
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
const PipelineFlow3D = dynamic(
  () => import("./3d/pipeline-flow-3d").then((m) => m.PipelineFlow3D),
  {
    loading: () => (
      <div className="flex h-full w-full items-center justify-center p-8">
        <Spinner />
      </div>
    ),
  },
);
import { ChatPanel } from "./chat-panel";
import { SettingsPanel } from "./settings-panel";

export function AuthenticatedWorkspace({
  user,
  dashboard,
  settings = false,
  pipeline = false,
  onLogout,
}: {
  user: User;
  dashboard: boolean;
  settings?: boolean;
  pipeline?: boolean;
  onLogout: () => void;
}) {
  const t = useTranslations("App");
  const client = useQueryClient();
  const router = useRouter();
  const params = useSearchParams();
  const paramSession = params.get("session");
  const [selected, setSelected] = useState<string | null>(paramSession);
  const [trace, setTrace] = useState<string | null>(null);
  const [mobileOpen, setMobileOpen] = useState(false);
  const [operation, setOperation] = useState(false);
  const [error, setError] = useState<unknown>();
  const [deleting, setDeleting] = useState<string | null>(null);
  const [requestBusy, setRequestBusy] = useState(false);
  const sessions = useInfiniteQuery({
    queryKey: ["sessions"],
    initialPageParam: 0,
    getNextPageParam: (lastPage: SessionInfo[], allPages) =>
      lastPage.length === 30 ? allPages.length * 30 : undefined,
    queryFn: async ({ pageParam = 0 }) =>
      unwrap(
        await api.GET("/v1/sessions", {
          params: { query: { offset: pageParam, limit: 30 } },
        }),
      ),
  });
  const sourceQuery = useQuery({
    queryKey: ["source-indicator"],
    queryFn: async () => unwrap(await api.GET("/v1/usage")),
    staleTime: 30000,
  });
  const source = sourceQuery.data?.execution_source ?? "mock";
  const sessionRows = (sessions.data?.pages.flat() ?? []) as SessionInfo[];
  async function newSession(title?: string): Promise<string> {
    const created = unwrap(
      await api.POST("/v1/sessions", {
        body: { title: title?.slice(0, 80) || t("newChat") },
      }),
    );
    await client.invalidateQueries({ queryKey: ["sessions"] });
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
          params: { path: { session_id: deleting } },
        }),
      );
      await client.invalidateQueries({ queryKey: ["sessions"] });
      if (selected === deleting) {
        setSelected(null);
        router.push("/");
      }
      setDeleting(null);
    } catch (e) {
      setError(e);
    } finally {
      setOperation(false);
    }
  }
  async function logout() {
    setOperation(true);
    try {
      unwrap(await api.POST("/v1/auth/logout"));
      onLogout();
      router.push("/");
    } catch (e) {
      setError(e);
    } finally {
      setOperation(false);
    }
  }
  const navigation = (
    <>
      <div className="brand-header">
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
          className={!dashboard && !settings && !pipeline ? "active" : ""}
        >
          <MessageSquare size={18} />
          {t("chat")}
        </Link>
        <Link href="/pipeline" className={pipeline ? "active" : ""}>
          <Layers size={18} />
          {t("pipeline")}
        </Link>
        <Link href="/settings" className={settings ? "active" : ""}>
          <SettingsIcon size={18} />{t("settings")}
        </Link>
        <Link href="/dashboard" className={dashboard ? "active" : ""}>
          <LayoutDashboard size={18} />
          {t("dashboard")}
        </Link>
      </nav>
      <div className="history-header">
        <span>{t("history")}</span>
        <button
          className="icon-button"
          onClick={() => sessions.refetch()}
          aria-label={t("refreshHistory")}
          disabled={sessions.isFetching}
        >
          <RefreshCw
            size={14}
            className={sessions.isFetching ? "spin" : ""}
          />
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
            {dashboard || settings || pipeline ? (
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
              className="icon-button history-delete"
              onClick={(e) => {
                e.stopPropagation();
                setDeleting(session.id);
              }}
              disabled={operation || requestBusy}
              aria-label={t("deleteSession")}
            >
              <Trash2 size={14} />
            </button>
          </div>
        ))}
        {sessions.hasNextPage && (
          <button
            className="button secondary small load-more"
            onClick={() => sessions.fetchNextPage()}
            disabled={sessions.isFetchingNextPage}
          >
            {sessions.isFetchingNextPage ? <Spinner /> : t("loadMore")}
          </button>
        )}
      </div>
      <div className="user-footer">
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
              {pipeline ? t("pipeline") : settings ? t("settings") : dashboard ? t("dashboard") : t("chat")}
            </strong>
          </div>
          <div className="topbar-actions">
            <span className="mock-badge">
              <span />
              {t(
                source === "mock" ? "simulationMode" : "liveMode",
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
        ) : settings ? (
          <SettingsPanel user={user} />
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
      <TraceInspector userId={user.id} requestId={trace} onClose={() => setTrace(null)} />
      <Dialog.Root
        open={!!deleting}
        onOpenChange={(open) => {
          if (!open && !operation) setDeleting(null);
        }}
      >
        <Dialog.Portal>
          <Dialog.Overlay className="overlay" />
          <Dialog.Content className="confirm-dialog">
            <Dialog.Title>{t("deleteTitle")}</Dialog.Title>
            <Dialog.Description>{t("deleteHint")}</Dialog.Description>
            <div className="dialog-actions">
              <button
                className="button secondary"
                onClick={() => setDeleting(null)}
                disabled={operation}
              >
                {t("cancel")}
              </button>
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
