"use client";
import { useEffect, useLayoutEffect, useRef, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { useTranslations } from "next-intl";
import { ChevronDown, Check, X } from "lucide-react";
import { api, unwrap } from "@/lib/api";
import { Spinner } from "./ui";

export function ProcessingProgress({
  sessionId,
  clientRequestId,
  requestId,
  active = false,
}: {
  sessionId: string;
  clientRequestId?: string;
  requestId?: string;
  active?: boolean;
}) {
  const t = useTranslations("Processing");
  const [open, setOpen] = useState(false);
  const [above, setAbove] = useState(false);
  const [following, setFollowing] = useState(true);
  const anchor = useRef<HTMLDivElement>(null);
  const button = useRef<HTMLButtonElement>(null);
  const popup = useRef<HTMLDivElement>(null);
  const list = useRef<HTMLUListElement>(null);
  const query = useQuery({
    queryKey: ["processing", sessionId, requestId ?? clientRequestId],
    enabled: active || open,
    retry: false,
    refetchInterval: (q) =>
      active &&
      !["succeeded", "failed", "interrupted"].includes(
        q.state.data?.status ?? "",
      )
        ? 700
        : false,
    queryFn: async () =>
      unwrap(
        requestId
          ? await api.GET(
              "/v1/sessions/{session_id}/requests/{request_id}/progress",
              {
                params: {
                  path: { session_id: sessionId, request_id: requestId },
                },
              },
            )
          : await api.GET("/v1/sessions/{session_id}/progress", {
              params: {
                path: { session_id: sessionId },
                query: { client_request_id: clientRequestId! },
              },
            }),
      ),
  });
  const events = query.data?.events ?? [];
  const running =
    active &&
    !["succeeded", "failed", "interrupted"].includes(query.data?.status ?? "");
  useLayoutEffect(() => {
    if (!open || !button.current || !popup.current) return;
    const container = button.current.closest(".conversation-scroll");
    const place = () => {
      if (!button.current || !popup.current) return;
      const trigger = button.current.getBoundingClientRect();
      const viewport = container?.getBoundingClientRect();
      const below =
        Math.min(window.innerHeight, viewport?.bottom ?? window.innerHeight) -
        trigger.bottom;
      const aboveSpace = trigger.top - Math.max(0, viewport?.top ?? 0);
      const required = 64 + Math.min(230, list.current?.scrollHeight ?? 100);
      const openAbove = below < required && aboveSpace > below;
      setAbove(openAbove);
      popup.current.style.setProperty(
        "--processing-space",
        `${Math.max(80, (openAbove ? aboveSpace : below) - 12)}px`,
      );
    };
    place();
    container?.addEventListener("scroll", place, { passive: true });
    window.addEventListener("resize", place);
    return () => {
      container?.removeEventListener("scroll", place);
      window.removeEventListener("resize", place);
    };
  }, [open, events.length, query.isLoading]);
  useEffect(() => {
    if (!open) return;
    const trigger = button.current!;
    popup.current?.focus({ preventScroll: true });
    const outside = (e: PointerEvent) => {
      if (!anchor.current?.contains(e.target as Node)) setOpen(false);
    };
    const key = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        setOpen(false);
        trigger.focus({ preventScroll: true });
      }
    };
    const observer = new IntersectionObserver(
      (entries) => {
        if (!entries[0].isIntersecting) setOpen(false);
      },
      { root: trigger.closest(".conversation-scroll") },
    );
    observer.observe(trigger);
    document.addEventListener("pointerdown", outside);
    document.addEventListener("keydown", key);
    return () => {
      observer.disconnect();
      document.removeEventListener("pointerdown", outside);
      document.removeEventListener("keydown", key);
    };
  }, [open]);
  useEffect(() => {
    if (open && following && list.current)
      list.current.scrollTop = list.current.scrollHeight;
  }, [events.length, open, following]);
  return (
    <div
      ref={anchor}
      className={`processing-progress ${active ? "processing-active" : "processing-saved"}`}
    >
      {active ? (
        <button
          type="button"
          ref={button}
          className={`processing-capsule ${open ? "is-open" : ""}`}
          aria-expanded={open}
          aria-haspopup="dialog"
          onClick={() => {
            setFollowing(true);
            setOpen(!open);
          }}
        >
          {running && <Spinner />}
          <span className="processing-capsule-text processing-current">
            {t(
              query.data?.current_stage ??
                (running ? "waiting" : (query.data?.status ?? "waiting")),
            )}
          </span>
          <span className="processing-capsule-badge">
            {events.length > 0 && (
              <span className="capsule-step-count">
                {events.filter((e) => e.status === "succeeded").length}/
                {events.length}
              </span>
            )}
            <span className="capsule-arrow">▾</span>
          </span>
        </button>
      ) : (
        <button
          type="button"
          ref={button}
          className="icon-button processing-trigger"
          aria-label={t("view")}
          aria-expanded={open}
          aria-haspopup="dialog"
          onClick={() => {
            setFollowing(true);
            setOpen(!open);
          }}
        >
          <ChevronDown size={15} />
        </button>
      )}
      {open && (
        <div
          ref={popup}
          tabIndex={-1}
          role="dialog"
          aria-label={t("view")}
          className={`processing-popup ${above ? "above" : "below"}`}
        >
          <header>
            <strong>{t("title")}</strong>
            <button
              type="button"
              className="icon-button"
              aria-label={t("close")}
              onClick={() => {
                setOpen(false);
                button.current?.focus({ preventScroll: true });
              }}
            >
              <X size={15} />
            </button>
          </header>
          <ul
            ref={list}
            onWheel={() => setFollowing(false)}
            onTouchMove={() => setFollowing(false)}
            onKeyDown={(e) => {
              if (["ArrowUp", "PageUp", "Home"].includes(e.key))
                setFollowing(false);
            }}
            tabIndex={0}
            onScroll={(e) => {
              const el = e.currentTarget;
              if (el.scrollHeight - el.scrollTop - el.clientHeight < 8)
                setFollowing(true);
            }}
          >
            {!events.length && (
              <li>
                {t(
                  query.isLoading
                    ? "waiting"
                    : query.isError
                      ? "unavailable"
                      : "empty",
                )}
              </li>
            )}
            {events.map((event) => (
              <li key={event.sequence} className={`processing-${event.status}`}>
                {event.status === "running" ? (
                  <Spinner />
                ) : event.status === "succeeded" ? (
                  <Check size={15} />
                ) : (
                  <span className="processing-dot" />
                )}
                <span>
                  {t(`steps.${event.stage}`)}
                  <small>{t(event.status)}</small>
                </span>
              </li>
            ))}
          </ul>
          {!following && running && (
            <button
              type="button"
              className="button small"
              onClick={() => setFollowing(true)}
            >
              {t("follow")}
            </button>
          )}
        </div>
      )}
    </div>
  );
}
