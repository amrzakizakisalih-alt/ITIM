import { useState, useEffect } from "react";
import { T } from "./constants";
import LatexPreview from "./LatexPreview";

/**
 * MathCheckModal – Allows the user to submit their answer
 * and the correct answer for evaluation by the tutor.
 */
export default function MathCheckModal({ lastLatex, onClose, onSubmit }) {
  const [userLatex, setUserLatex] = useState(lastLatex || "");
  const [correctLatex, setCorrectLatex] = useState("");

  // Updates the field when lastLatex changes
  useEffect(() => {
    setUserLatex(lastLatex || "");
  }, [lastLatex]);

  const handleSubmit = () => {
    if (!userLatex.trim() || !correctLatex.trim()) return;
    onSubmit(userLatex.trim(), correctLatex.trim());
    onClose();
  };

  useEffect(() => {
    const onKey = (e) => { if (e.key === "Escape") onClose(); };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [onClose]);

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-labelledby="mathcheck-modal-title"
      onClick={(e) => { if (e.target === e.currentTarget) onClose(); }}
      style={{
        position: "fixed", inset: 0, zIndex: 1000,
        background: "rgba(0,0,0,0.78)", backdropFilter: "blur(6px)",
        display: "flex", alignItems: "center", justifyContent: "center",
      }}
    >
      <div style={{
        background: T.surface, border: `1px solid ${T.border}`,
        borderRadius: 18, width: 480, maxWidth: "95vw",
        display: "flex", flexDirection: "column", overflow: "hidden",
        boxShadow: "0 40px 100px #000c",
        animation: "fadeUp .2s ease",
      }}>
        <style>{`@keyframes fadeUp { from { opacity:0; transform:translateY(16px) } to { opacity:1; transform:translateY(0) } }`}</style>

        {/* Header */}
        <div style={{
          padding: "16px 20px", borderBottom: `1px solid ${T.border}`,
          display: "flex", alignItems: "center", gap: 12,
        }}>
          <span style={{ fontSize: 24 }}>🧮</span>
          <div style={{ flex: 1 }}>
            <div style={{ color: T.textPri, fontWeight: 600, fontSize: 14 }}>
              Check your answer
            </div>
            <div style={{ color: T.textHint, fontSize: 11, marginTop: 3 }}>
              Submit your work and the correct solution for evaluation
            </div>
          </div>
          <button onClick={onClose} style={{
            background: "transparent", border: "none", color: T.textSec,
            fontSize: 22, cursor: "pointer", padding: "2px 6px", borderRadius: 6,
          }}>✕</button>
        </div>

        {/* Body */}
        <div style={{ padding: "20px", display: "flex", flexDirection: "column", gap: 16 }}>
          {/* Your answer */}
          <div>
            <label style={{ display: "block", color: T.textSec, fontSize: 12, marginBottom: 6 }}>
              Your answer (LaTeX)
            </label>
            <input
              value={userLatex}
              onChange={(e) => setUserLatex(e.target.value)}
              placeholder="e.g. x^2 + 2x + 1"
              style={{
                width: "100%", background: T.darkBg, color: T.textPri,
                border: `1px solid ${T.border}`, borderRadius: 8,
                padding: "10px 12px", fontSize: 13, fontFamily: "'DM Mono', monospace",
                outline: "none",
              }}
            />
            <LatexPreview latex={userLatex} displayMode={false} />
          </div>

          {/* Correct answer */}
          <div>
            <label style={{ display: "block", color: T.textSec, fontSize: 12, marginBottom: 6 }}>
              Correct answer (LaTeX)
            </label>
            <input
              value={correctLatex}
              onChange={(e) => setCorrectLatex(e.target.value)}
              placeholder="e.g. (x+1)^2"
              style={{
                width: "100%", background: T.darkBg, color: T.textPri,
                border: `1px solid ${T.border}`, borderRadius: 8,
                padding: "10px 12px", fontSize: 13, fontFamily: "'DM Mono', monospace",
                outline: "none",
              }}
            />
            <LatexPreview latex={correctLatex} displayMode={false} />
          </div>
        </div>

        {/* Actions */}
        <div style={{
          padding: "14px 20px", borderTop: `1px solid ${T.border}`,
          display: "flex", justifyContent: "flex-end", gap: 10,
          background: T.panelBg,
        }}>
          <button onClick={onClose} style={{
            padding: "8px 16px", borderRadius: 8, cursor: "pointer",
            background: "transparent", color: T.textSec,
            border: `1px solid ${T.border}`, fontSize: 13,
          }}>Cancel</button>
          <button onClick={handleSubmit} style={{
            padding: "8px 18px", borderRadius: 8, cursor: "pointer",
            background: T.accent, color: "#fff",
            border: "none", fontSize: 13, fontWeight: 600,
          }}>Submit ↵</button>
        </div>
      </div>
    </div>
  );
}
