import { T, COLORS } from "./constants";
import { useState } from "react";
export default function OptionBar({chatVisible, setChatVisible, wsConnected, wsUrl, setWsUrl }) {
    const [editing, setEditing] = useState(false);
    const [tmpUrl, setTmpUrl] = useState(wsUrl);
   
    return (
      <div style={{
        height: 48, background: T.panelBg, borderBottom: `1px solid ${T.border}`,
        display: "flex", alignItems: "center", padding: "0 16px", gap: 8, flexShrink: 0,
      }}>
        {/* Logo */}
        <span style={{
          color: T.accentGlow, fontSize: 16, fontWeight: 700, letterSpacing: 1,
          fontFamily: "'DM Mono', monospace",
        }}> ITIM</span>
   
        <div style={{ width: 1, height: 24, background: T.border }} />
   

   
        {/* WS URL config */}
        <div style={{ display: "flex", alignItems: "center", gap: 4 }}>
          {editing ? (
            <>
              <input
                value={tmpUrl}
                onChange={(e) => setTmpUrl(e.target.value)}
                placeholder="ws://localhost:8000/ws"
                style={{
                  background: T.surface, color: T.textPri, border: `1px solid ${T.border}`,
                  borderRadius: 6, padding: "4px 8px", fontSize: 11, width: 200,
                }}
              />
              <button
                onClick={() => { setWsUrl(tmpUrl); setEditing(false); }}
                style={{
                  background: T.accent, color: "#fff", border: "none",
                  borderRadius: 6, padding: "4px 8px", fontSize: 11, cursor: "pointer",
                }}
              >Connect</button>
            </>
          ) : (
            <button
              onClick={() => setEditing(true)}
              title={wsUrl || "Set WebSocket URL"}
              style={{
                background: T.surfaceHigh, color: wsConnected ? T.greenOk : T.textHint,
                border: `1px solid ${T.border}`, borderRadius: 6, padding: "4px 10px",
                fontSize: 11, cursor: "pointer",
              }}
            >
              {wsConnected ? "🔌 WS connected" : "⚡ Set WS URL"}
            </button>
          )}
        </div>
   
        {/* Chat toggle */}
        <button
          onClick={() => setChatVisible(!chatVisible)}
          style={{
            background: chatVisible ? T.accent : T.surfaceHigh,
            color: chatVisible ? "#fff" : T.textPri,
            border: `1px solid ${chatVisible ? T.accent : T.border}`,
            borderRadius: 8, padding: "5px 14px", fontSize: 12, cursor: "pointer",
            transition: "all .15s",
          }}
        >🧠 Tutor</button>
      </div>
    );
  }