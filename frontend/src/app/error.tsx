"use client";
export default function ErrorPage({
  error,
  reset,
}: {
  error?: Error & { digest?: string };
  reset: () => void;
}) {
  return (
    <main className="fatal">
      <h1>Không thể tải trang / Unable to load page</h1>
      <p style={{ color: "#64748b", fontSize: 14, margin: "8px 0 16px", maxWidth: 600 }}>
        Máy chủ đang bận hoặc đang khởi động lại. Vui lòng bấm thử lại hoặc tải lại trang. / The server is busy or restarting. Please try again or reload the page.
      </p>
      {error?.message && (
        <pre
          style={{
            maxWidth: 800,
            whiteSpace: "pre-wrap",
            color: "#dc2626",
            background: "#fef2f2",
            padding: 12,
            borderRadius: 8,
            fontSize: 13,
            margin: "16px 0",
            textAlign: "left",
          }}
        >
          {error.message}
        </pre>
      )}
      <div style={{ display: "flex", gap: 12, justifyContent: "center" }}>
        <button className="button primary" onClick={reset}>
          Thử lại / Try again
        </button>
        <button
          className="button"
          onClick={() => {
            if (typeof window !== "undefined") {
              window.location.href = window.location.pathname;
            }
          }}
        >
          Tải lại trang / Reload
        </button>
      </div>
    </main>
  );
}
