import { T } from "./constants";
import { useUIStore } from "./stores/useUIStore";

export default function OptionBar({ wsConnected }) {
  const { chatVisible, setChatVisible } = useUIStore();

  const toggleFullscreen = () => {
    if (!document.fullscreenElement) {
      document.documentElement.requestFullscreen?.();
    } else {
      document.exitFullscreen?.();
    }
  };

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

      {/* Connection status */}
      <span style={{
        fontSize: 11,
        color: wsConnected ? T.greenOk : "#e74c3c",
        display: "flex",
        alignItems: "center",
        gap: 4,
      }}>
        {wsConnected ? "● Online" : "● Offline"}
      </span>

      <div style={{ flex: 1 }} />

      {/* Fullscreen toggle */}
      <button
        onClick={toggleFullscreen}
        title="Fullscreen"
        style={{
          background: T.surfaceHigh,
          color: T.textPri,
          border: `1px solid ${T.border}`,
          borderRadius: 8, padding: "5px 10px", fontSize: 12, cursor: "pointer",
          transition: "all .15s",
        }}
      >⛶</button>

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
