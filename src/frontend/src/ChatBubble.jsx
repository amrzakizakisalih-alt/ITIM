import { useState, useRef, useEffect } from "react";
import { T } from "./constants";

export default function ChatBubble({ text, role }) {
    const isUser = role === "user";
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
        }}>
          {text}
        </div>
      </div>
    );
  }