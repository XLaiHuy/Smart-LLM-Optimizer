"use client";
import * as Dialog from "@radix-ui/react-dialog";
import { X, LoaderCircle } from "lucide-react";
import { useTranslations } from "next-intl";
import { ApiError } from "@/lib/api";

export function Spinner() {
  return <LoaderCircle className="spin" size={18} aria-hidden="true" />;
}
export function ErrorNotice({ error }: { error: unknown }) {
  const t = useTranslations("Errors");
  const code = error instanceof ApiError ? error.code : "NETWORK_ERROR";
  return (
    <div role="alert" className="error-notice">
      {t.has(code) ? t(code) : t("UNKNOWN")}
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
