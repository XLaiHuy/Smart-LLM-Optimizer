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
      <button className="button primary" onClick={reset}>
        Thử lại / Try again
      </button>
    </main>
  );
}
