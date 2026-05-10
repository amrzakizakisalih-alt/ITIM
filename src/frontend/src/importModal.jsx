import { useState, useRef, useEffect, useCallback } from "react";
import { T } from "./constants";

function escapeHtml(str) {
  if (!str) return "";
  return str
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

export default function ImportModal({ file, onClose, onEmbed, onFeedAI }) {
  const [dataUrl, setDataUrl]   = useState(null);
  const [pdfPages, setPdfPages] = useState(null);
  const [counting, setCounting] = useState(false);
  const isPdf = file?.type === "application/pdf";
  const isImg = file?.type?.startsWith("image/");

  // Read file → dataUrl
  useEffect(() => {
    if (!file) return;
    const reader = new FileReader();
    reader.onload = (e) => setDataUrl(e.target.result);
    reader.readAsDataURL(file);
  }, [file]);

  // Count PDF pages via pdf.js
  useEffect(() => {
    if (!isPdf || !dataUrl) return;
    setCounting(true);
    const run = async () => {
      try {
        const { getPdfDocument } = await import("./pdfService.js");
        const pdf = await getPdfDocument(dataUrl);
        setPdfPages(pdf.numPages);
      } catch { setPdfPages("?"); }
      finally { setCounting(false); }
    };
    run();
  }, [isPdf, dataUrl]);

  const openNewTab = () => {
    if (!dataUrl) return;
    const w = window.open("", "_blank");
    const safeName = escapeHtml(file.name);
    if (isPdf) {
      w.document.write(
        `<html><head><title>${safeName}</title></head>` +
        `<body style="margin:0;background:#1a1a2e">` +
        `<embed src="${dataUrl}" type="application/pdf" width="100%" height="100%" style="min-height:100vh">` +
        `</body></html>`
      );
    } else {
      w.document.write(
        `<html><head><title>${safeName}</title></head>` +
        `<body style="margin:0;background:#1a1a2e;display:flex;align-items:center;justify-content:center;min-height:100vh">` +
        `<img src="${dataUrl}" style="max-width:100%;max-height:100vh;object-fit:contain">` +
        `</body></html>`
      );
    }
    w.document.close();
  };

  const embedInDoc = () => {
    const n = isPdf ? (typeof pdfPages === "number" ? pdfPages : 1) : 1;
    onEmbed(file, dataUrl, n);
    onClose();
  };

  const feedAI = () => {
    onFeedAI?.(file, dataUrl);
    onClose();
  };

  const fmt = (b) => b > 1048576 ? `${(b / 1048576).toFixed(1)} MB` : `${Math.round(b / 1024)} KB`;

  if (!file) return null;

  const embedLabel = counting
    ? "counting pages…"
    : isPdf
      ? `+ ${pdfPages ?? "?"} page${pdfPages !== 1 ? "s" : ""} will be added`
      : "+ 1 page will be added";

  useEffect(() => {
    const onKey = (e) => { if (e.key === "Escape") onClose(); };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [onClose]);

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-labelledby="import-modal-title"
      onClick={(e) => { if (e.target === e.currentTarget) onClose(); }}
      style={{
        position: "fixed", inset: 0, zIndex: 1000,
        background: "rgba(0,0,0,0.78)", backdropFilter: "blur(6px)",
        display: "flex", alignItems: "center", justifyContent: "center",
      }}
    >
      <div style={{
        background: T.surface, border: `1px solid ${T.border}`,
        borderRadius: 18, width: 700, maxWidth: "95vw", maxHeight: "90vh",
        display: "flex", flexDirection: "column", overflow: "hidden",
        boxShadow: "0 40px 100px #000c",
        animation: "fadeUp .2s ease",
      }}>
        <style>{`@keyframes fadeUp { from { opacity:0; transform:translateY(16px) } to { opacity:1; transform:translateY(0) } }`}</style>

        {/* ── Header ── */}
        <div style={{
          padding: "16px 20px", borderBottom: `1px solid ${T.border}`,
          display: "flex", alignItems: "center", gap: 12,
        }}>
          <span style={{ fontSize: 24 }}>{isPdf ? "📄" : "🖼️"}</span>
          <div style={{ flex: 1, minWidth: 0 }}>
            <div id="import-modal-title" style={{ color: T.textPri, fontWeight: 600, fontSize: 14, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>
              {file.name}
            </div>
            <div style={{ color: T.textHint, fontSize: 11, marginTop: 3, display: "flex", gap: 10 }}>
              <span>{fmt(file.size)}</span>
              <span style={{ color: T.border }}>·</span>
              <span>{file.type || "unknown type"}</span>
              {isPdf && (
                <>
                  <span style={{ color: T.border }}>·</span>
                  <span style={{ color: counting ? T.amberWarn : T.greenOk }}>
                    {counting ? "counting pages…" : `${pdfPages ?? "?"} page${pdfPages !== 1 ? "s" : ""}`}
                  </span>
                </>
              )}
              {isImg && <><span style={{ color: T.border }}>·</span><span>1 page</span></>}
            </div>
          </div>
          <button onClick={onClose} style={{ background: "transparent", border: "none", color: T.textSec, fontSize: 22, cursor: "pointer", padding: "2px 6px", borderRadius: 6 }}>✕</button>
        </div>

        {/* ── Preview ── */}
        <div style={{
          flex: 1, overflow: "hidden", background: T.darkBg,
          display: "flex", alignItems: "center", justifyContent: "center",
          minHeight: 320, position: "relative",
        }}>
          {!dataUrl && (
            <div style={{ color: T.textHint, fontSize: 13 }}>Loading preview…</div>
          )}
          {dataUrl && isPdf && (
            <iframe
              src={dataUrl + "#toolbar=0&navpanes=0"}
              title="PDF preview"
              style={{ width: "100%", height: "100%", minHeight: 380, border: "none" }}
            />
          )}
          {dataUrl && isImg && (
            <img src={dataUrl} alt="preview"
              style={{ maxWidth: "100%", maxHeight: 420, objectFit: "contain", display: "block" }}
            />
          )}
          {dataUrl && !isPdf && !isImg && (
            <div style={{ color: T.textHint, fontSize: 13, padding: 32, textAlign: "center" }}>
              <div style={{ fontSize: 40, marginBottom: 12 }}>📎</div>
              No visual preview available for this file type.
            </div>
          )}
        </div>

        {/* ── Actions ── */}
        <div style={{
          padding: "16px 20px", borderTop: `1px solid ${T.border}`,
          display: "flex", gap: 10, alignItems: "stretch",
          background: T.panelBg,
        }}>
          {/* Open in new tab */}
          <ActionCard
            icon="↗️"
            title="Open in new tab"
            sub="View only, no annotation"
            disabled={!dataUrl}
            onClick={openNewTab}
            variant="secondary"
          />

          {/* Embed */}
          <ActionCard
            icon="📋"
            title="Insert into document"
            sub={embedLabel}
            disabled={!dataUrl || counting}
            onClick={embedInDoc}
            variant="primary"
          />

          {/* Feed AI */}
          <ActionCard
            icon="🧠"
            title="Feed AI"
            sub="Analyze & generate exercises"
            disabled={!dataUrl || counting}
            onClick={feedAI}
            variant="secondary"
          />

          {/* Cancel */}
          <button onClick={onClose} style={{
            padding: "0 18px", borderRadius: 12, cursor: "pointer",
            background: "transparent", color: T.textSec,
            border: `1px solid ${T.border}`, fontSize: 13, flexShrink: 0,
          }}>Cancel</button>
        </div>
      </div>
    </div>
  );
}

function ActionCard({ icon, title, sub, disabled, onClick, variant }) {
  const [hov, setHov] = useState(false);
  const isPrimary = variant === "primary";
  return (
    <button
      onClick={onClick}
      disabled={disabled}
      onMouseEnter={() => setHov(true)}
      onMouseLeave={() => setHov(false)}
      style={{
        flex: 1, padding: "14px 16px", borderRadius: 12, cursor: disabled ? "not-allowed" : "pointer",
        background: isPrimary
          ? (hov && !disabled ? T.accentGlow : T.accent)
          : (hov && !disabled ? T.surfaceHigh : T.surface),
        color: isPrimary ? "#fff" : T.textPri,
        border: isPrimary ? "none" : `1px solid ${hov && !disabled ? T.accent : T.border}`,
        fontSize: 13, opacity: disabled ? 0.4 : 1,
        display: "flex", flexDirection: "column", alignItems: "center", gap: 6,
        transition: "all .15s",
      }}
    >
      <span style={{ fontSize: 26 }}>{icon}</span>
      <span style={{ fontWeight: 600 }}>{title}</span>
      <span style={{ fontSize: 11, opacity: 0.75, textAlign: "center" }}>{sub}</span>
    </button>
  );
}