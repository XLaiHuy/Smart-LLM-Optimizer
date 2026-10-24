import * as React from "react";
import type { ReactNode } from "react";
import katex from "katex";
import { Copy, Check } from "lucide-react";
import { useLocale } from "next-intl";

// Safe KaTeX renderer for mathematical formulas
function renderMath(formula: string, displayMode: boolean): ReactNode {
  try {
    const html = katex.renderToString(formula.trim(), {
      displayMode,
      throwOnError: false,
    });
    if (displayMode) {
      return (
        <div
          className="katex-display"
          dangerouslySetInnerHTML={{ __html: html }}
        />
      );
    }
    return (
      <span
        className="math-inline"
        dangerouslySetInnerHTML={{ __html: html }}
      />
    );
  } catch {
    return <code>{formula}</code>;
  }
}

// Inline parser supporting:
// 1. Math: \( ... \) or $ ... $
// 2. Code: ` ... `
// 3. Bold: ** ... **
// 4. Italic: * ... *
function inline(text: string): ReactNode[] {
  // Safe pattern without catastrophic backtracking:
  // - \( ... \)
  // - $...$ (non-empty, no leading/trailing space)
  // - `...`
  // - **...**
  // - *...*
  const pattern = /(\\\([^\n]+?\\\)|(?<![\w\\])\$(?!\s)[^\$\n]+?(?<!\s)\$|`[^`\n]+`|\*\*[^*\n]+\*\*|(?<!\*)\*[^*\n]+\*(?!\*))/g;

  return text.split(pattern).map((part, i) => {
    if (!part) return null;

    // Inline LaTeX \( ... \)
    if (part.startsWith("\\(") && part.endsWith("\\)")) {
      return (
        <React.Fragment key={i}>
          {renderMath(part.slice(2, -2), false)}
        </React.Fragment>
      );
    }

    // Inline LaTeX $ ... $
    if (part.startsWith("$") && part.endsWith("$") && part.length > 2) {
      return (
        <React.Fragment key={i}>
          {renderMath(part.slice(1, -1), false)}
        </React.Fragment>
      );
    }

    // Inline Code `...`
    if (/^`[^`\n]+`$/.test(part)) {
      return <code key={i}>{part.slice(1, -1)}</code>;
    }

    // Bold **...**
    if (/^\*\*[^*\n]+\*\*$/.test(part)) {
      return <strong key={i}>{inline(part.slice(2, -2))}</strong>;
    }

    // Italic *...*
    if (/^\*[^*\n]+\*$/.test(part)) {
      return <em key={i}>{inline(part.slice(1, -1))}</em>;
    }

    return <React.Fragment key={i}>{part}</React.Fragment>;
  });
}

// Interactive Mermaid Diagram Renderer
function MermaidBlock({ code }: { code: string }) {
  const [svg, setSvg] = React.useState<string | null>(null);
  const [error, setError] = React.useState<string | null>(null);
  const idRef = React.useRef(
    `mermaid-${Math.random().toString(36).substring(2, 9)}`,
  );

  React.useEffect(() => {
    let mounted = true;
    import("mermaid")
      .then((mermaidModule) => {
        const mermaid = mermaidModule.default;
        mermaid.initialize({
          startOnLoad: false,
          theme: "neutral",
          securityLevel: "loose",
          fontFamily: "Roboto, system-ui, sans-serif",
        });
        mermaid
          .render(idRef.current, code.trim())
          .then(({ svg }) => {
            if (mounted) setSvg(svg);
          })
          .catch((err) => {
            if (mounted) setError(String(err));
          });
      })
      .catch((err) => {
        if (mounted) setError(String(err));
      });

    return () => {
      mounted = false;
    };
  }, [code]);

  if (error) {
    return (
      <pre className="my-2 rounded bg-slate-100 p-3 text-xs text-slate-700 overflow-x-auto">
        <code>{code}</code>
      </pre>
    );
  }

  let locale = "vi";
  try {
    locale = useLocale();
  } catch {
    locale = "vi";
  }

  if (!svg) {
    return (
      <div className="my-3 flex items-center justify-center rounded-lg border border-slate-200 bg-slate-50/60 p-6 text-xs text-slate-500">
        <span className="animate-pulse">
          {locale === "en" ? "Rendering Mermaid diagram..." : "Đang dựng sơ đồ Mermaid..."}
        </span>
      </div>
    );
  }

  return (
    <div className="mermaid-diagram my-3 overflow-x-auto rounded-lg border border-slate-200 bg-white p-4 shadow-xs">
      <div className="mb-2 text-[11px] font-semibold tracking-wide text-slate-400 uppercase">
        {locale === "en" ? "Process Diagram (Mermaid)" : "Sơ đồ quy trình (Mermaid)"}
      </div>
      <div
        className="flex justify-center"
        dangerouslySetInnerHTML={{ __html: svg }}
      />
    </div>
  );
}

// Code Block with Language Tag and 1-Click Copy
function CodeBlock({ language, code }: { language: string; code: string }) {
  const [copied, setCopied] = React.useState(false);
  let locale = "vi";
  try {
    locale = useLocale();
  } catch {
    locale = "vi";
  }

  function handleCopy() {
    if (typeof navigator !== "undefined" && navigator.clipboard?.writeText) {
      navigator.clipboard
        .writeText(code)
        .then(() => {
          setCopied(true);
          setTimeout(() => setCopied(false), 2000);
        })
        .catch(() => {});
    }
  }

  return (
    <div className="code-block my-3 overflow-hidden rounded-lg border border-slate-800 bg-[#0f172a] text-[#f8fafc] shadow-md">
      <div className="flex items-center justify-between border-b border-slate-800 bg-[#090d16] px-4 py-2 text-xs text-slate-300">
        <span className="font-mono text-[11px] uppercase tracking-wider text-sky-400 font-semibold">
          {language || "code"}
        </span>
        <button
          type="button"
          onClick={handleCopy}
          className="inline-flex items-center gap-1.5 text-[11px] text-slate-300 hover:text-white transition-colors cursor-pointer"
        >
          {copied ? (
            <>
              <Check size={12} className="text-emerald-400" />
              <span className="text-emerald-400 font-medium">
                {locale === "en" ? "Copied" : "Đã chép"}
              </span>
            </>
          ) : (
            <>
              <Copy size={12} />
              <span>{locale === "en" ? "Copy" : "Sao chép"}</span>
            </>
          )}
        </button>
      </div>
      <pre
        className="overflow-x-auto p-4 font-mono text-[13.5px] leading-relaxed text-[#f8fafc]"
        style={{ background: "#0f172a", color: "#f8fafc" }}
      >
        <code style={{ background: "transparent", color: "#f8fafc" }}>{code}</code>
      </pre>
    </div>
  );
}

// Context-aware Markdown Table Cell Parser (preserves | inside math formulas or inline code)
function parseMarkdownCells(line: string): string[] {
  const trimmed = line.trim().replace(/^\|/, "").replace(/\|$/, "");
  const cells: string[] = [];
  let current = "";
  let inParenMath = false; // \( ... \)
  let inBracketMath = false; // \[ ... \]
  let inDollarMath = false; // $ ... $
  let inCode = false; // ` ... `

  for (let i = 0; i < trimmed.length; i++) {
    const char = trimmed[i];
    const prev = i > 0 ? trimmed[i - 1] : "";
    const next = i + 1 < trimmed.length ? trimmed[i + 1] : "";

    // Toggle inline code `
    if (char === "`" && prev !== "\\") {
      inCode = !inCode;
      current += char;
      continue;
    }

    if (!inCode) {
      // Toggle \( and \)
      if (char === "\\" && next === "(") {
        inParenMath = true;
        current += "\\(";
        i++;
        continue;
      }
      if (char === "\\" && next === ")") {
        inParenMath = false;
        current += "\\)";
        i++;
        continue;
      }

      // Toggle \[ and \]
      if (char === "\\" && next === "[") {
        inBracketMath = true;
        current += "\\[";
        i++;
        continue;
      }
      if (char === "\\" && next === "]") {
        inBracketMath = false;
        current += "\\]";
        i++;
        continue;
      }

      // Toggle $ ... $
      if (char === "$" && prev !== "\\") {
        inDollarMath = !inDollarMath;
        current += char;
        continue;
      }
    }

    // Split on | only if not inside math or code, and not escaped
    if (
      char === "|" &&
      !inCode &&
      !inParenMath &&
      !inBracketMath &&
      !inDollarMath &&
      prev !== "\\"
    ) {
      cells.push(current.trim());
      current = "";
    } else {
      current += char;
    }
  }

  cells.push(current.trim());
  return cells;
}

// GFM Markdown Table Renderer
function MarkdownTable({ rows }: { rows: string[] }) {
  const headers = parseMarkdownCells(rows[0]);
  const alignments = rows[1]
    ? parseMarkdownCells(rows[1]).map((sep) => {
        if (sep.startsWith(":") && sep.endsWith(":")) return "center";
        if (sep.endsWith(":")) return "right";
        return "left";
      })
    : [];

  const bodyRows = rows.slice(2).map(parseMarkdownCells);

  return (
    <div className="table-wrapper my-3 overflow-x-auto rounded-lg border border-slate-200 shadow-xs">
      <table>
        <thead>
          <tr>
            {headers.map((h, i) => (
              <th
                key={i}
                style={{ textAlign: (alignments[i] as any) || "left" }}
              >
                {inline(h)}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {bodyRows.map((row, r) => (
            <tr key={r}>
              {row.map((cell, c) => (
                <td
                  key={c}
                  style={{ textAlign: (alignments[c] as any) || "left" }}
                >
                  {inline(cell)}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function isTableStart(lines: string[], i: number): boolean {
  if (i + 1 >= lines.length) return false;
  const current = lines[i].trim();
  const next = lines[i + 1].trim();
  if (!current.includes("|") || !next.includes("|")) return false;
  // Check if next line is a table delimiter like |---|---| or | :--- | :---: |
  return /^\s*\|?\s*:?-+:?\s*(\|\s*:?-+:?\s*)+\|?\s*$/.test(next);
}

export function FormattedMessage({
  content,
  legacyMock = false,
  isStreaming = false,
}: {
  content?: string;
  legacyMock?: boolean;
  isStreaming?: boolean;
}) {
  const safeContent = content ?? "";
  const text =
    legacyMock && (safeContent.match(/^```/gm)?.length ?? 0) % 2 === 0
      ? safeContent.replace(
          /\n\n\*\(Ghi nhận \d+ messages received trong ngữ cảnh\)\*\s*$/,
          "",
        )
      : safeContent;

  // Lightweight Stream Rendering: fast, zero KaTeX / Mermaid / GFM table re-parsing jitter
  if (isStreaming) {
    const codeSpanPattern = /(`[^`\n]+`)/g;
    const parts = text.split(codeSpanPattern);

    return (
      <div className="formatted-message is-streaming whitespace-pre-wrap break-words font-sans text-[16px] leading-[1.65] text-[#0f172a] after:content-['▋'] after:ml-0.5 after:text-blue-600 after:animate-pulse after:font-bold">
        {parts.map((part, i) => {
          if (part.startsWith("`") && part.endsWith("`") && part.length > 2) {
            return (
              <code
                key={i}
                className="rounded bg-slate-100 px-1.5 py-0.5 font-mono text-[0.9em] text-slate-800"
              >
                {part.slice(1, -1)}
              </code>
            );
          }
          return <React.Fragment key={i}>{part}</React.Fragment>;
        })}
      </div>
    );
  }

  const lines = text.split("\n");
  const blocks: ReactNode[] = [];
  let index = 0;

  while (index < lines.length) {
    const rawLine = lines[index];
    const trimmed = rawLine.trim();

    if (!trimmed) {
      index++;
      continue;
    }

    const key = index;

    // 1. Code Block & Mermaid
    if (trimmed.startsWith("```")) {
      const language = trimmed.slice(3).trim();
      index++;
      const code = [];
      while (index < lines.length && !lines[index].trim().startsWith("```")) {
        code.push(lines[index++]);
      }
      if (index < lines.length) index++;

      if (language === "mermaid") {
        blocks.push(<MermaidBlock key={key} code={code.join("\n")} />);
      } else {
        blocks.push(
          <CodeBlock
            key={key}
            language={language}
            code={code.join("\n")}
          />,
        );
      }
      continue;
    }

    // 2. Display Block Math: \[ ... \] or $$ ... $$
    if (trimmed.startsWith("\\[") || trimmed.startsWith("$$")) {
      const isBracket = trimmed.startsWith("\\[");
      const endMarker = isBracket ? "\\]" : "$$";

      let firstContent = trimmed.slice(2).trim();

      if (firstContent.endsWith(endMarker) && firstContent.length > endMarker.length) {
        // Single-line block math
        firstContent = firstContent.slice(0, -endMarker.length).trim();
        blocks.push(<React.Fragment key={key}>{renderMath(firstContent, true)}</React.Fragment>);
        index++;
        continue;
      }

      // Check if closing marker exists in subsequent lines
      const hasClosingMarker = lines.slice(index + 1).some((l) => l.includes(endMarker));
      if (hasClosingMarker) {
        const mathLines: string[] = [];
        if (firstContent) mathLines.push(firstContent);
        index++;

        while (index < lines.length && !lines[index].includes(endMarker)) {
          mathLines.push(lines[index++]);
        }
        if (index < lines.length) {
          const last = lines[index++].split(endMarker)[0].trim();
          if (last) mathLines.push(last);
        }

        blocks.push(
          <React.Fragment key={key}>
            {renderMath(mathLines.join("\n"), true)}
          </React.Fragment>,
        );
        continue;
      }
      // If no closing marker exists, treat this line as regular paragraph content to avoid infinite loop
      blocks.push(<p key={key}>{inline(rawLine)}</p>);
      index++;
      continue;
    }

    // 3. GFM Markdown Table
    if (isTableStart(lines, index)) {
      const tableLines: string[] = [];
      while (index < lines.length && lines[index].trim().includes("|")) {
        tableLines.push(lines[index++]);
      }
      blocks.push(<MarkdownTable key={key} rows={tableLines} />);
      continue;
    }

    // 4. Headings: #, ##, ###
    if (trimmed.startsWith("# ") && !trimmed.startsWith("## ")) {
      blocks.push(<h1 key={key}>{inline(trimmed.slice(2))}</h1>);
      index++;
      continue;
    }
    if (trimmed.startsWith("## ") && !trimmed.startsWith("### ")) {
      blocks.push(<h2 key={key}>{inline(trimmed.slice(3))}</h2>);
      index++;
      continue;
    }
    if (trimmed.startsWith("### ")) {
      blocks.push(<h3 key={key}>{inline(trimmed.slice(4))}</h3>);
      index++;
      continue;
    }

    // 5. Horizontal Rule: ---, ***, ___
    if (/^(?:---|\*\*\*|___)\s*$/.test(trimmed)) {
      blocks.push(<hr key={key} />);
      index++;
      continue;
    }

    // 6. Blockquote: > ...
    if (trimmed.startsWith("> ")) {
      const quoteLines: string[] = [];
      while (index < lines.length && lines[index].trim().startsWith("> ")) {
        quoteLines.push(lines[index++].trim().slice(2));
      }
      blocks.push(
        <blockquote key={key}>
          {inline(quoteLines.join("\n"))}
        </blockquote>,
      );
      continue;
    }

    // 7. Lists: Ordered (1.) or Unordered (- / • / *)
    if (/^\s*(?:[-•*]|\d+[.)])\s+/.test(rawLine)) {
      const ordered = /^\s*\d+[.)]\s+/.test(rawLine);
      const pattern = ordered ? /^\s*\d+[.)]\s+/ : /^\s*[-•*]\s+/;
      const items = [];
      while (index < lines.length && pattern.test(lines[index])) {
        items.push(
          <li key={index}>{inline(lines[index++].replace(pattern, ""))}</li>,
        );
      }
      blocks.push(
        ordered ? <ol key={key}>{items}</ol> : <ul key={key}>{items}</ul>,
      );
      continue;
    }

    // 8. Paragraphs
    const paragraph = [];
    while (
      index < lines.length &&
      lines[index].trim() &&
      !lines[index].trim().startsWith("```") &&
      !lines[index].trim().startsWith("\\[") &&
      !lines[index].trim().startsWith("$$") &&
      !isTableStart(lines, index) &&
      !lines[index].trim().startsWith("# ") &&
      !lines[index].trim().startsWith("## ") &&
      !lines[index].trim().startsWith("### ") &&
      !/^(?:---|\*\*\*|___)\s*$/.test(lines[index].trim()) &&
      !lines[index].trim().startsWith("> ") &&
      !/^\s*(?:[-•*]|\d+[.)])\s+/.test(lines[index])
    ) {
      paragraph.push(lines[index++]);
    }
    if (paragraph.length > 0) {
      blocks.push(<p key={key}>{inline(paragraph.join("\n"))}</p>);
    } else {
      // Safety guard: ensure index always advances
      index++;
    }
  }

  return <div className="formatted-message">{blocks}</div>;
}
