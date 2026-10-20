"use client";
export default function ErrorPage({ reset }: { reset: () => void }) {
  return (
    <main className="fatal">
      <h1>Không thể tải trang / Unable to load page</h1>
      <button className="button primary" onClick={reset}>
        Thử lại / Try again
      </button>
    </main>
  );
}
