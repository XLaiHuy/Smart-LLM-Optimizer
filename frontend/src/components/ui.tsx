"use client";
import * as Dialog from "@radix-ui/react-dialog";
import { X, LoaderCircle } from "lucide-react";
import { useTranslations } from "next-intl";
import { ApiError, api, unwrap } from "@/lib/api";
import { useQuery } from "@tanstack/react-query";
import { useState } from "react";

function ProviderDiagnostics({ requestId }: { requestId: string }) {
  const t = useTranslations("Errors");
  const [expanded, setExpanded] = useState(false);
  const calls = useQuery({
    queryKey: ["failed-provider-calls", requestId],
    enabled: expanded,
    queryFn: async () =>
      unwrap(
        await api.GET("/v1/traces/{request_id}/calls", {
          params: { path: { request_id: requestId } },
        }),
      ),
  });
  return (
    <details onToggle={(event) => setExpanded(event.currentTarget.open)}>
      <summary>{t("providerCalls")}</summary>
      {calls.isLoading && <Spinner />}
      {calls.isError && <p>{t("NETWORK_ERROR")}</p>}
      {calls.data?.map((call) => (
        <p key={call.call_id}>
          {call.model_id} · {call.error_code || call.dispatch_state}
          {call.retry_after_seconds != null &&
            ` · ${t("retryAfter", { seconds: Math.ceil(call.retry_after_seconds) })}`}
        </p>
      ))}
    </details>
  );
}

export function Spinner() {
  return <LoaderCircle className="spin" size={18} aria-hidden="true" />;
}
export function ErrorNotice({ error }: { error: unknown }) {
  const t = useTranslations("Errors");
  const code = error instanceof ApiError ? error.code : "NETWORK_ERROR";
  return (
    <div role="alert" className="error-notice">
      {t.has(code) ? t(code) : t("UNKNOWN")}
      {error instanceof ApiError && error.retryAfterSeconds != null && (
        <small>
          {" "}
          · {t("retryAfter", { seconds: Math.ceil(error.retryAfterSeconds) })}
        </small>
      )}
      {error instanceof ApiError && error.requestId && (
        <>
          <small className="mono"> · Request ID: {error.requestId}</small>
          <ProviderDiagnostics
            key={error.requestId}
            requestId={error.requestId}
          />
        </>
      )}
    </div>
  );
}

export function Drawer({
  open,
  onOpenChange,
  title,
  description,
  children,
  side = "right",
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  title: string;
  description?: string;
  children: React.ReactNode;
  side?: "left" | "right";
}) {
  const t = useTranslations("App");
  return (
    <Dialog.Root open={open} onOpenChange={onOpenChange}>
      <Dialog.Portal>
        <Dialog.Overlay className="overlay" />
        <Dialog.Content
          className={`drawer ${side}`}
          {...(!description ? { "aria-describedby": undefined } : {})}
        >
          <header className="drawer-heading">
            <div>
              <Dialog.Title>{title}</Dialog.Title>
              {description && (
                <Dialog.Description>{description}</Dialog.Description>
              )}
            </div>
            <Dialog.Close className="icon-button" aria-label={t("close")}>
              <X size={19} />
            </Dialog.Close>
          </header>
          <div className="drawer-body">{children}</div>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}
