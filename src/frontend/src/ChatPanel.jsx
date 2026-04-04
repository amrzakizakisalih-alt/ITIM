import { useState, useRef, useEffect } from "react";
import { T } from "./constants";
import ChatBubble from "./ChatBubble"

export default function ChatPanel({ visible, onMessage, wsConnected }) {
    const [messages, setMessages] = useState([
      { text: "Hello! I'm your AI tutor. Write a math exercise on the page and I'll help you identify errors and improve. 🎓", role: "assistant" },
    ]);
    const [input, setInput] = useState("");
    const scrollRef = useRef(null);
  
    useEffect(() => {
      if (scrollRef.current) scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }, [messages]);
  
    const addMessage = (text, role = "assistant") => {
      setMessages((m) => [...m, { text, role }]);
    };
  
    const send = () => {
      const t = input.trim();
      if (!t) return;
      setInput("");
      addMessage(t, "user");
      onMessage?.(t);
      setTimeout(() => addMessage("📌 Analysing your input… (ACT-R engine will be connected here)", "assistant"), 800);
    };
  
    if (!visible) return null;
  
    return (
      <div style={{
        width: 320, flexShrink: 0, display: "flex", flexDirection: "column",
        background: T.panelBg, borderLeft: `1px solid ${T.border}`,
      }}>
        {/* Header */}
        <div style={{
          padding: "10px 14px", background: T.surface, borderBottom: `1px solid ${T.border}`,
          display: "flex", alignItems: "center", gap: 8,
        }}>
          <span style={{ color: T.textPri, fontWeight: 600, fontSize: 13, flex: 1 }}>🧠 ITIM Tutor</span>
          <span style={{ fontSize: 11, color: wsConnected ? T.greenOk : T.amberWarn }}>
            {wsConnected ? "● connected" : "○ offline"}
          </span>
        </div>
  
        {/* Messages */}
        <div ref={scrollRef} style={{
          flex: 1, overflowY: "auto", padding: "12px 8px",
          background: T.panelBg, display: "flex", flexDirection: "column",
        }}>
          {messages.map((m, i) => <ChatBubble key={i} {...m} />)}
        </div>
  
        {/* Input */}
        <div style={{ padding: 10, background: T.surface, borderTop: `1px solid ${T.border}` }}>
          <textarea
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); send(); } }}
            placeholder="Ask your math question…"
            rows={3}
            style={{
              width: "100%", boxSizing: "border-box", resize: "none",
              background: T.surface, color: T.textPri,
              border: `1px solid ${T.border}`, borderRadius: 10,
              padding: "8px 12px", fontSize: 13, fontFamily: "inherit",
              outline: "none",
            }}
          />
          <div style={{ display: "flex", justifyContent: "flex-end", marginTop: 6 }}>
            <button
              onClick={send}
              style={{
                background: T.accent, color: "#fff", border: "none",
                borderRadius: 8, padding: "6px 16px", fontSize: 12,
                fontWeight: 600, cursor: "pointer",
              }}
            >Send ↵</button>
          </div>
        </div>
      </div>
    );
  }
  