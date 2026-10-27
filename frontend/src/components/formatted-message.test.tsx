import { describe, expect, it, vi } from "vitest";
import { renderToString } from "react-dom/server";
import { FormattedMessage } from "./formatted-message";

vi.mock("next-intl", () => ({ useLocale: () => "vi" }));

describe("FormattedMessage GFM Markdown & KaTeX Parser", () => {
  it("renders LaTeX formulas cleanly", () => {
    const html = renderToString(
      <FormattedMessage
        content={
          "Công thức: \\(z = \\theta^T x\\)\n\n\\[\\hat{y} = \\sigma(z)\\]"
        }
      />,
    );
    expect(html).toContain("katex");
    expect(html).toContain("katex-display");
  });

  it("renders GFM Markdown tables", () => {
    const markdown = [
      "| Thuật toán | Độ phức tạp |",
      "| :--- | :---: |",
      "| BGD | O(Nd) |",
      "| SGD | O(d) |",
    ].join("\n");
    const html = renderToString(<FormattedMessage content={markdown} />);
    expect(html).toContain("<table");
    expect(html).toContain("<th");
    expect(html).toContain("Thuật toán");
    expect(html).toContain("O(Nd)");
  });

  it("renders headings, code blocks and lists", () => {
    const markdown = [
      "## Tiêu đề cấp 2",
      "---",
      "- Mục danh sách 1",
      "- Mục danh sách 2",
      "```python",
      "def hello():",
      "    print('world')",
      "```",
    ].join("\n");
    const html = renderToString(<FormattedMessage content={markdown} />);
    expect(html).toContain("<h2");
    expect(html).toContain("<hr");
    expect(html).toContain("<ul");
    expect(html).toContain("<li");
    expect(html).toContain("code-block");
    expect(html).toContain("def hello");
  });

  it("renders lightweight stream view with pulse cursor when isStreaming is true", () => {
    const streamContent = "Đang sinh token cho `print('hello')`...";
    const html = renderToString(
      <FormattedMessage content={streamContent} isStreaming={true} />,
    );
    expect(html).toContain("is-streaming");
    expect(html).toContain("after:content-[&#x27;▋&#x27;]");
    expect(html).toContain("after:animate-pulse");
    expect(html).toContain("<code");
    expect(html).toContain("print(&#x27;hello&#x27;)");
    // Should NOT parse KaTeX or complex tables during streaming
    expect(html).not.toContain("katex");
  });

  it("handles undefined, nullish, or empty content gracefully without error", () => {
    expect(() =>
      renderToString(<FormattedMessage content={undefined} />),
    ).not.toThrow();
    expect(() =>
      renderToString(<FormattedMessage content={""} />),
    ).not.toThrow();
    expect(() =>
      renderToString(<FormattedMessage content={""} isStreaming={true} />),
    ).not.toThrow();
  });

  it("handles unclosed block math without swallowing subsequent paragraphs", () => {
    const unclosedMath = [
      "$$",
      "Đoạn văn tiếp theo không bị nuốt chửng bởi công thức dở dang.",
      "- Danh sách việc cần làm",
    ].join("\n");
    const html = renderToString(<FormattedMessage content={unclosedMath} />);
    expect(html).toContain("Đoạn văn tiếp theo");
    expect(html).toContain("<ul");
    expect(html).toContain("Danh sách việc cần làm");
  });

  it("handles unclosed inline LaTeX without throwing parse errors", () => {
    const unclosedInline =
      "Công thức dở dang: \\(\\frac{1}{2 và văn bản tiếp tục";
    const streamingHtml = renderToString(
      <FormattedMessage content={unclosedInline} isStreaming={true} />,
    );
    expect(streamingHtml).toContain("Công thức dở dang");

    const finalHtml = renderToString(
      <FormattedMessage content={unclosedInline} isStreaming={false} />,
    );
    expect(finalHtml).toContain("Công thức dở dang");
  });

  it("preserves vertical bars inside math within table cells without breaking columns", () => {
    const tableWithMath = [
      "| Thành phần | Mô tả |",
      "| :--- | :--- |",
      "| **Encoder** \\(q_{\\phi}(z|x)\\) | Phân phối Gaussian |",
    ].join("\n");
    const html = renderToString(<FormattedMessage content={tableWithMath} />);
    expect(html).toContain("<table");
    // Should have exactly 2 columns in the row (2 <td> tags), not 3
    const tdCount = (html.match(/<td/g) || []).length;
    expect(tdCount).toBe(2);
    expect(html).toContain("katex");
  });

  it("renders nested math inside bold tags like **\\(\\lambda\\)**", () => {
    const boldMath = "- **\\(\\lambda\\)** là hệ số cân bằng";
    const html = renderToString(<FormattedMessage content={boldMath} />);
    expect(html).toContain("<strong");
    expect(html).toContain("katex");
    expect(html).toContain("hệ số cân bằng");
  });
});
