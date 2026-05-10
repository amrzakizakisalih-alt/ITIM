import { useMemo } from "react";
import { T } from "./constants";

/**
 * LatexPreview – Real-time KaTeX rendering of a LaTeX string.
 * Uses the katex CDN (window.katex).
 */
export default function LatexPreview({ latex, displayMode = false, fallback = null, inline = false }) {
  const html = useMemo(() => {
    if (!latex || !latex.trim()) return null;
    if (typeof window === "undefined" || !window.katex) return null;
    try {
      return window.katex.renderToString(latex, {
        throwOnError: false,
        displayMode,
        trust: false,
        strict: false,
      });
    } catch {
      return null;
    }
  }, [latex, displayMode]);

  if (!html) return fallback;

  if (inline) {
    return (
      <span
        style={{ color: T.textPri }}
        dangerouslySetInnerHTML={{ __html: html }}
      />
    );
  }

  return (
    <div
      style={{
        padding: displayMode ? "12px 16px" : "4px 8px",
        background: T.darkBg,
        border: `1px dashed ${T.border}`,
        borderRadius: 8,
        marginTop: 6,
        overflowX: "auto",
        color: T.textPri,
        fontSize: displayMode ? 14 : 13,
      }}
      dangerouslySetInnerHTML={{ __html: html }}
    />
  );
}
