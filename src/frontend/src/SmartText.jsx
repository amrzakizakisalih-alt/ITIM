import { useState, useEffect } from "react";

/**
 * SmartText – Detects and renders:
 *   - Basic Markdown (**bold**, *italic*)
 *   - Inline LaTeX : $...$, \(...\)
 *   - Block LaTeX  : $$...$$, \[...\]
 * via KaTeX (CDN).
 */
function renderKatex(latex, displayMode) {
  if (typeof window === "undefined" || !window.katex) return null;
  try {
    return window.katex.renderToString(latex, {
      throwOnError: false,
      displayMode,
      trust: false,
      strict: false,
      errorColor: "#e8e8f0",
    });
  } catch {
    return null;
  }
}

function parseMarkdown(text) {
  if (!text) return text;
  // Bold **...**
  let html = text.replace(/\*\*(.*?)\*\*/g, "<strong>$1</strong>");
  // Italic *...* (avoids already processed **)
  html = html.replace(/(^|\s)\*([^*\s][^*]*?)\*(\s|$)/g, "$1<em>$2</em>$3");
  return html;
}

/**
 * Tokenizes mixed text (text + LaTeX).
 * Supports $...$, $$...$$, \(...\), \[...\].
 */
function tokenize(text) {
  if (!text) return [];

  const tokens = [];
  // Capture : $$block$$, $inline$, \[block\], \(inline\)
  const regex = /\$\$([\s\S]*?)\$\$|\$([\s\S]*?)\$|\\\[([\s\S]*?)\\\]|\\\(([\s\S]*?)\\\)/g;
  let lastIndex = 0;
  let match;

  while ((match = regex.exec(text)) !== null) {
    if (match.index > lastIndex) {
      tokens.push({ type: "text", value: text.slice(lastIndex, match.index) });
    }

    if (match[1] !== undefined) {
      tokens.push({ type: "block", value: match[1] });
    } else if (match[2] !== undefined) {
      tokens.push({ type: "inline", value: match[2] });
    } else if (match[3] !== undefined) {
      tokens.push({ type: "block", value: match[3] });
    } else if (match[4] !== undefined) {
      tokens.push({ type: "inline", value: match[4] });
    }

    lastIndex = regex.lastIndex;
  }

  if (lastIndex < text.length) {
    tokens.push({ type: "text", value: text.slice(lastIndex) });
  }

  return tokens;
}

export default function SmartText({ text }) {
  const [katexReady, setKatexReady] = useState(
    !!(typeof window !== "undefined" && window.katex)
  );

  useEffect(() => {
    if (katexReady) return;
    const id = setInterval(() => {
      if (typeof window !== "undefined" && window.katex) {
        setKatexReady(true);
        clearInterval(id);
      }
    }, 200);
    return () => clearInterval(id);
  }, [katexReady]);

  if (!text) return null;

  // If the text contains LaTeX commands but NO delimiter ($, \(, \[),
  // we wrap each "word" containing a \ in $...$. This renders formulas
  // without touching normal text.
  let processed = text;
  if (!text.includes("$") && !text.includes("\\(") && !text.includes("\\[")) {
    processed = text.replace(/[^\s.,;:!?]+/g, (word) => {
      if (word.includes("\\")) {
        return `$${word}$`;
      }
      return word;
    });
  }

  const tokens = tokenize(processed);

  return (
    <span>
      {tokens.map((part, i) => {
        if (part.type === "text") {
          const html = parseMarkdown(part.value);
          return (
            <span
              key={i}
              dangerouslySetInnerHTML={{
                __html: html.replace(/\n/g, "<br/>"),
              }}
            />
          );
        }

        const html = renderKatex(part.value, part.type === "block");
        if (!html) {
          // KaTeX not yet loaded → display delimiter + plain text
          const delim = part.type === "block" ? "$$" : "$";
          return (
            <span key={i}>
              {delim}
              {part.value}
              {delim}
            </span>
          );
        }

        return (
          <span
            key={i}
            dangerouslySetInnerHTML={{ __html: html }}
            style={
              part.type === "block"
                ? { display: "block", margin: "8px 0" }
                : {}
            }
          />
        );
      })}
    </span>
  );
}
