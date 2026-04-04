import { T, COLORS } from "./constants";
export default function StatusBar({ pageCount, msg }) {
    return (
      <div style={{
        height: 28, background: T.panelBg, borderTop: `1px solid ${T.border}`,
        display: "flex", alignItems: "center", padding: "0 16px",
        color: T.textHint, fontSize: 11, gap: 12, flexShrink: 0,
        fontFamily: "'DM Mono', monospace",
      }}>
        <span>Pages: {pageCount}</span>
        <span style={{ color: T.border }}>│</span>
        {msg && <>
          <span style={{ color: T.border }}>│</span>
          <span style={{ color: T.textSec }}>{msg}</span>
        </>}
      </div>
    );
  }