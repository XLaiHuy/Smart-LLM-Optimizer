import * as React from "react";
import type { ReactNode } from "react";

// Intentionally a small formatting subset. Raw HTML/URLs never become executable markup.
function inline(text: string): ReactNode[] {
  return text
    .split(/(`[^`\n]+`|\*\*[^*\n]+\*\*|(?<!\*)\*[^*\n]+\*(?!\*))/g)
    .map((part, i) => {
      if (/^`[^`\n]+`$/.test(part))
        return <code key={i}>{part.slice(1, -1)}</code>;
      if (/^\*\*[^*\n]+\*\*$/.test(part))
        return <strong key={i}>{part.slice(2, -2)}</strong>;
      if (/^\*[^*\n]+\*$/.test(part))
        return <em key={i}>{part.slice(1, -1)}</em>;
      return <React.Fragment key={i}>{part}</React.Fragment>;
    });
}

export function FormattedMessage({
  content,
  legacyMock = false,
}: {
  content: string;
  legacyMock?: boolean;
}) {
  const text =
    legacyMock && (content.match(/^```/gm)?.length ?? 0) % 2 === 0
      ? content.replace(
          /\n\n\*\(Ghi nhận \d+ messages received trong ngữ cảnh\)\*\s*$/,
          "",
        )
      : content;
  const lines = text.split("\n");
  const blocks: ReactNode[] = [];
  let index = 0;
  while (index < lines.length) {
    if (!lines[index].trim()) {
      index++;
      continue;
    }
    const key = index;
    if (lines[index].startsWith("```")) {
      index++;
      const code = [];
      while (index < lines.length && !lines[index].startsWith("```"))
        code.push(lines[index++]);
      if (index < lines.length) index++;
      blocks.push(
        <pre key={key}>
          <code>{code.join("\n")}</code>
        </pre>,
      );
    } else if (/^\s*(?:[-•]|\d+[.)])\s+/.test(lines[index])) {
      const ordered = /^\s*\d+[.)]\s+/.test(lines[index]);
      const pattern = ordered ? /^\s*\d+[.)]\s+/ : /^\s*[-•]\s+/;
      const items = [];
      while (index < lines.length && pattern.test(lines[index])) {
        items.push(
          <li key={index}>{inline(lines[index++].replace(pattern, ""))}</li>,
        );
      }
      blocks.push(
        ordered ? <ol key={key}>{items}</ol> : <ul key={key}>{items}</ul>,
      );
    } else {
      const paragraph = [];
      while (
        index < lines.length &&
        lines[index].trim() &&
        !lines[index].startsWith("```") &&
        !/^\s*(?:[-•]|\d+[.)])\s+/.test(lines[index])
      )
        paragraph.push(lines[index++]);
      blocks.push(<p key={key}>{inline(paragraph.join("\n"))}</p>);
    }
  }
  return <div className="formatted-message">{blocks}</div>;
}
