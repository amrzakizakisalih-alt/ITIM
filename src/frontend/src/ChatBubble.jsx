import { useState } from "react";
import { T } from "./constants";
import SmartText from "./SmartText";
import { speakText, stopSpeaking } from "./useSpeech";

export default function ChatBubble({ text, role, accent }) {
  const isUser = role === "user";
  const [speaking, setSpeaking] = useState(false);

  const handleSpeak = () => {
    if (speaking) {
      stopSpeaking();
      setSpeaking(false);
      return;
    }
    setSpeaking(true);
    speakText(text, () => setSpeaking(false));
  };

  return (
    <div style={{
      display: "flex", alignItems: "flex-end", gap: 6,
      flexDirection: isUser ? "row-reverse" : "row",
      marginBottom: 8,
    }}>
      {!isUser && (
        <div style={{ fontSize: 18, flexShrink: 0 }}>🤖</div>
      )}
      <div style={{
        maxWidth: 240, padding: "8px 12px", borderRadius: 12,
        background: isUser ? "#2e2e42" : T.surfaceHigh,
        color: T.textPri, fontSize: 12, lineHeight: 1.5,
        fontFamily: "'DM Sans', sans-serif",
        boxShadow: "0 1px 4px #0003",
        borderLeft: accent ? `3px solid ${accent}` : "none",
        position: "relative",
      }}>
        <SmartText text={text} />
        {!isUser && (
          <button
            onClick={handleSpeak}
            title={speaking ? "Stop" : "Read aloud"}
            style={{
              position: "absolute",
              bottom: 2,
              right: 2,
              background: "transparent",
              border: "none",
              color: speaking ? T.accentGlow : T.textHint,
              fontSize: 10,
              cursor: "pointer",
              padding: 2,
              lineHeight: 1,
              opacity: 0.7,
              transition: "opacity .15s, color .15s",
            }}
            onMouseEnter={(e) => { e.currentTarget.style.opacity = "1"; }}
            onMouseLeave={(e) => { e.currentTarget.style.opacity = "0.7"; }}
          >
            {speaking ? "⏹" : "🔊"}
          </button>
        )}
      </div>
    </div>
  );
}
