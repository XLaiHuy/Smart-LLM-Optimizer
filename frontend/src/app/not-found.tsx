import Link from "next/link";
export default function NotFound() {
  return (
    <main className="fatal">
      <h1>404</h1>
      <Link href="/">Về hội thoại / Back to workspace</Link>
    </main>
  );
}
