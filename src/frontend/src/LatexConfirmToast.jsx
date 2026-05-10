import { useEffect } from "react";
import { T } from "./constants";
import LatexPreview from "./LatexPreview";

/**
 * LatexConfirmToast – Displayed when the backend detects LaTeX
 * automatically (OCR stroke). Asks the user for confirmation.
 *
 * The component no longer has built-in positioning; it is positioned
 * by its parent (attached to the upper-left corner of the ChatPanel).
 *
 * Props:
 *   latex      : detected string
 *   onYes      : callback "it is correct"
 *   onNo       : callback "no, manual input"
 *   onDismiss  : callback to close the toast
 */
export default function LatexConfirmToast({ latex, onYes, onNo, onDismiss }) {
  useEffect(() => {
    const onKey = (e) => {
      if (e.key === "Escape") onDismiss?.();
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [onDismiss]);

  return (
    <div
      style={{
        background: T.surface,
        border: `1px solid ${T.accent}`,
        borderRadius: 14,
        padding: "14px 18px",
        boxShadow: "0 20px 60px #000c",
        display: "flex",
        flexDirection: "column",
        gap: 10,
        minWidth: 280,
        maxWidth: "90vw",
        animation: "slideDown .25s ease",
      }}
    >
      <style>{`
        @keyframes slideDown {
          from { opacity: 0; transform: translateY(-20px); }
          to   { opacity: 1; transform: translateY(0); }
        }
      `}</style>

      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
        <div style={{ color: T.textSec, fontSize: 12, fontWeight: 600 }}>
          🖊️ I detected this formula
        </div>
        <button
          onClick={onDismiss}
          aria-label="Dismiss"
          style={{
            background: "transparent",
            border: "none",
            color: T.textSec,
            fontSize: 16,
            cursor: "pointer",
            lineHeight: 1,
            padding: "0 0 0 8px",
          }}
        >
          ×
        </button>
      </div>

      <LatexPreview latex={latex} displayMode={false} />

      <div style={{ display: "flex", justifyContent: "flex-end", gap: 8, marginTop: 4 }}>
        <button
          onClick={onNo}
          title="Enter manually instead"
          style={{
            padding: "6px 14px",
            borderRadius: 8,
            background: "transparent",
            color: T.textSec,
            border: `1px solid ${T.border}`,
            fontSize: 12,
            cursor: "pointer",
          }}
        >
          No, enter manually
        </button>
        <button
          onClick={onYes}
          title="Submit detected formula"
          style={{
            padding: "6px 16px",
            borderRadius: 8,
            background: T.accent,
            color: "#fff",
            border: "none",
            fontSize: 12,
            fontWeight: 600,
            cursor: "pointer",
          }}
        >
          Yes, submit ↵
        </button>
      </div>
    </div>
  );
}
