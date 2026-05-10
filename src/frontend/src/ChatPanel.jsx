import { useState, useRef, useEffect } from "react";
import { T } from "./constants";
import ChatBubble from "./ChatBubble";
import SmartText from "./SmartText";
import { useSpeech, speakText, stopSpeaking, unlockAudio } from "./useSpeech";

export default function ChatPanel({
  visible,
  onMessage,
  wsConnected,
  wsLastMessage,
  proposedExercises,
  proposedSource,
  onRequestExercise,
  onStartExercise,
  onClearProposals,
}) {
  const [messages, setMessages] = useState([
    {
      text: "Hello! I'm your AI tutor. Write a math exercise on the page and I'll help you identify errors and improve. 🎓",
      role: "assistant",
    },
  ]);
  const [input, setInput] = useState("");
  const [activeProgress, setActiveProgress] = useState(null);
  const scrollRef = useRef(null);

  const {
    speechSupported,
    isListening,
    transcript,
    startListening,
    clearTranscript,
  } = useSpeech();

  /* ── Conversation mode (cross-browser VAD) ─────────────────────────────── */
  const convSupported = !!window.navigator.mediaDevices?.getUserMedia;
  const [convMode, setConvMode] = useState(false);
  const [isConvSpeaking, setIsConvSpeaking] = useState(false);
  const [isConvListening, setIsConvListening] = useState(false);
  const convModeRef = useRef(false);
  const isConvSpeakingRef = useRef(false);
  const onMessageRef = useRef(onMessage);
  const lastSpokenRef = useRef(null);

  useEffect(() => { convModeRef.current = convMode; }, [convMode]);
  useEffect(() => { isConvSpeakingRef.current = isConvSpeaking; }, [isConvSpeaking]);
  useEffect(() => { onMessageRef.current = onMessage; }, [onMessage]);

  // Reset states when leaving conversation mode
  useEffect(() => {
    if (!convMode) {
      setIsConvSpeaking(false);
      setIsConvListening(false);
      stopSpeaking();
      lastSpokenRef.current = null;
    }
  }, [convMode]);

  // Recording loop with silence detection (VAD)
  useEffect(() => {
    if (!convMode || isConvSpeaking) return;

    let cancelled = false;
    let currentRecorder = null;
    let currentAudioCtx = null;
    let currentRaf = null;

    const startCycle = async () => {
      if (cancelled || isConvSpeakingRef.current || !convModeRef.current) return;

      try {
        const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
        const audioCtx = new AudioContext();
        currentAudioCtx = audioCtx;
        const source = audioCtx.createMediaStreamSource(stream);
        const analyser = audioCtx.createAnalyser();
        analyser.fftSize = 256;
        source.connect(analyser);

        const mimeType = MediaRecorder.isTypeSupported("audio/webm") ? "audio/webm" : "";
        const recorder = new MediaRecorder(stream, mimeType ? { mimeType } : undefined);
        currentRecorder = recorder;
        const chunks = [];

        recorder.ondataavailable = (e) => {
          if (e.data.size > 0) chunks.push(e.data);
        };

        recorder.onstop = async () => {
          if (currentRaf) cancelAnimationFrame(currentRaf);
          stream.getTracks().forEach((t) => t.stop());
          try { await audioCtx.close(); } catch {}
          currentAudioCtx = null;
          currentRecorder = null;
          setIsConvListening(false);

          if (cancelled || !convModeRef.current) return;
          if (chunks.length === 0) {
            startCycle();
            return;
          }

          const blob = new Blob(chunks, { type: recorder.mimeType || "audio/webm" });
          const formData = new FormData();
          formData.append("file", blob, "recording.webm");

          try {
            const res = await fetch("/api/transcribe", { method: "POST", body: formData });
            if (!res.ok) throw new Error(`HTTP ${res.status}`);
            const data = await res.json();
            if (data.text?.trim()) {
              onMessageRef.current?.(data.text.trim());
              setIsConvSpeaking(true);
            } else {
              startCycle();
            }
          } catch (err) {
            console.error("[Conv] Transcription failed:", err);
            if (!cancelled && convModeRef.current) startCycle();
          }
        };

        // VAD
        const dataArray = new Uint8Array(analyser.frequencyBinCount);
        let silenceStart = null;
        const threshold = 15;
        const silenceDuration = 2000;

        const check = () => {
          if (cancelled || isConvSpeakingRef.current || !currentRecorder) return;
          analyser.getByteFrequencyData(dataArray);
          const avg = dataArray.reduce((a, b) => a + b, 0) / dataArray.length;

          if (avg < threshold) {
            if (!silenceStart) silenceStart = Date.now();
            else if (Date.now() - silenceStart > silenceDuration) {
              recorder.stop();
              return;
            }
          } else {
            silenceStart = null;
          }
          currentRaf = requestAnimationFrame(check);
        };

        recorder.onstart = () => {
          setIsConvListening(true);
          currentRaf = requestAnimationFrame(check);
        };

        recorder.start();
      } catch (err) {
        console.error("[Conv] Start failed:", err);
      }
    };

    startCycle();

    return () => {
      cancelled = true;
      if (currentRaf) cancelAnimationFrame(currentRaf);
      if (currentRecorder) {
        try { currentRecorder.stop(); } catch {}
      }
      if (currentAudioCtx) {
        try { currentAudioCtx.close(); } catch {}
      }
    };
  }, [convMode, isConvSpeaking]);

  // Auto TTS on assistant response
  useEffect(() => {
    if (!convMode || !isConvSpeaking || !wsLastMessage) return;
    if (wsLastMessage.type !== "tutor_message") return;
    // Avoid re-speaking the same message when isConvSpeaking changes
    // without wsLastMessage having changed (e.g., new question asked
    // before the backend response arrived)
    if (lastSpokenRef.current === wsLastMessage) return;

    lastSpokenRef.current = wsLastMessage;
    speakText(wsLastMessage.text, () => {
      setIsConvSpeaking(false);
    });
  }, [wsLastMessage, convMode, isConvSpeaking]);

  useEffect(() => {
    if (transcript) {
      setInput(transcript);
    }
  }, [transcript]);

  useEffect(() => {
    if (scrollRef.current)
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
  }, [messages]);

  useEffect(() => {
    if (!wsLastMessage) return;

    if (wsLastMessage.type === "tutor_message") {
      setMessages((m) => [...m, { text: wsLastMessage.text, role: "assistant" }]);
    }

    if (wsLastMessage.type === "latex_update" && wsLastMessage.latex) {
      setMessages((m) => [
        ...m,
        { text: `📐 LaTeX detected: ${wsLastMessage.latex}`, role: "assistant" },
      ]);
    }

    if (wsLastMessage.type === "exercise" && wsLastMessage.exercise) {
      const ex = wsLastMessage.exercise;
      setMessages((m) => [
        ...m,
        {
          text: `**New exercise**${ex.difficulty ? ` (${ex.difficulty})` : ""}\n\nProblem: ${ex.problem_latex}`,
          role: "assistant",
          exercise: ex,
        },
      ]);
    }

    if (wsLastMessage.type === "step_feedback") {
      const meta = wsLastMessage.metadata || {};
      setActiveProgress({
        current: meta.step_index ?? 0,
        total: meta.total_steps ?? 1,
        status: wsLastMessage.status,
      });
      setMessages((m) => [
        ...m,
        {
          text: wsLastMessage.text,
          role: "assistant",
          step_status: wsLastMessage.status,
        },
      ]);
    }

  }, [wsLastMessage]);

  const addMessage = (text, role = "assistant") => {
    setMessages((m) => [...m, { text, role }]);
  };

  const send = () => {
    const t = input.trim();
    if (!t) return;
    setInput("");
    clearTranscript();
    addMessage(t, "user");
    onMessage?.(t);
  };

  const handleExerciseClick = (ex) => {
    onStartExercise?.(ex);
    setActiveProgress({ current: 0, total: ex.steps?.length || 1, status: "started" });
    setMessages((m) => [
      ...m,
      {
        text: `**Starting exercise:** ${ex.concept.replace(/_/g, " ")}${ex.difficulty ? ` (${ex.difficulty})` : ""}`,
        role: "assistant",
      },
    ]);
  };

  const handleShowAnswer = (ex) => {
    setMessages((m) => [
      ...m,
      {
        text: `**Answer:** ${ex.correct_latex}\n\n💡 *Hint:* ${ex.hint}`,
        role: "assistant",
      },
    ]);
  };

  if (!visible) return null;

  return (
    <div
      className="chat-panel"
      style={{
        width: 320,
        flexShrink: 0,
        display: "flex",
        flexDirection: "column",
        background: T.panelBg,
        borderLeft: `1px solid ${T.border}`,
      }}
    >
      {/* Header */}
      <div
        style={{
          padding: "10px 14px",
          background: T.surface,
          borderBottom: `1px solid ${T.border}`,
          display: "flex",
          alignItems: "center",
          gap: 8,
        }}
      >
        <span style={{ color: T.textPri, fontWeight: 600, fontSize: 13, flex: 1 }}>
          🧠 ITIM Tutor
        </span>
        <span style={{ display: "flex", alignItems: "center", gap: 8 }}>
          <button
            onClick={() => {
              if (!convSupported) {
                alert("Voice conversation is not supported in this browser. Try Chrome or Edge.");
                return;
              }
              unlockAudio(); // required on iOS/WebKit to unlock TTS
              setConvMode((v) => !v);
            }}
            title={convMode ? "Disable conversation mode" : "Enable conversation mode"}
            style={{
              fontSize: 11,
              background: convMode ? T.greenOk : "transparent",
              color: convMode ? "#fff" : convSupported ? T.textSec : T.textHint,
              border: `1px solid ${convMode ? T.greenOk : convSupported ? T.border : T.textHint}`,
              borderRadius: 6,
              padding: "2px 8px",
              cursor: convSupported ? "pointer" : "not-allowed",
              opacity: convSupported ? 1 : 0.5,
              transition: "background .2s, border-color .2s, color .2s",
            }}
          >
            {convMode ? "🔴 Conversation" : "🎙️ Conversation"}
          </button>
          <span style={{ fontSize: 11, color: wsConnected ? T.greenOk : T.amberWarn }}>
            {wsConnected ? "● connected" : "○ offline"}
          </span>
        </span>
      </div>

      {/* Messages */}
      <div
        ref={scrollRef}
        style={{
          flex: 1,
          overflowY: "auto",
          padding: "12px 8px",
          background: T.panelBg,
          display: "flex",
          flexDirection: "column",
        }}
      >
        {messages.map((m, i) => (
          <div key={i}>
            <ChatBubble
              text={m.text}
              role={m.role}
              accent={
                m.step_status === "completed"
                  ? T.greenOk
                  : m.step_status === "buggy_detected"
                  ? T.amberWarn
                  : m.step_status === "incorrect"
                  ? T.redHint
                  : undefined
              }
            />
            {m.exercise && (
              <div style={{ paddingLeft: 32, marginBottom: 8 }}>
                <button
                  onClick={() => handleShowAnswer(m.exercise)}
                  style={{
                    background: T.accent,
                    color: "#fff",
                    border: "none",
                    borderRadius: 6,
                    padding: "4px 10px",
                    fontSize: 11,
                    cursor: "pointer",
                  }}
                >
                  Show answer
                </button>
              </div>
            )}
          </div>
        ))}
      </div>

      {/* Active step progress */}
      {activeProgress && (
        <div
          style={{
            padding: "8px 12px",
            background: T.darkBg,
            borderTop: `1px solid ${T.border}`,
          }}
        >
          <div style={{ display: "flex", justifyContent: "space-between", fontSize: 10, color: T.textHint, marginBottom: 4 }}>
            <span>Progress</span>
            <span>{activeProgress.current} / {activeProgress.total}</span>
          </div>
          <div style={{ height: 4, background: T.border, borderRadius: 2, overflow: "hidden" }}>
            <div
              style={{
                height: "100%",
                width: `${(activeProgress.current / activeProgress.total) * 100}%`,
                background:
                  activeProgress.status === "completed"
                    ? T.greenOk
                    : activeProgress.status === "buggy_detected"
                    ? T.amberWarn
                    : T.accent,
                transition: "width .3s ease",
              }}
            />
          </div>
        </div>
      )}

      {/* Proposed exercises */}
      {proposedExercises && proposedExercises.length > 0 && (
        <div
          style={{
            padding: "10px 12px",
            background: T.surface,
            borderTop: `1px solid ${T.border}`,
            maxHeight: 180,
            overflowY: "auto",
          }}
        >
          <div style={{ fontSize: 11, fontWeight: 600, color: T.accentGlow, marginBottom: 8 }}>
            📚 Proposed exercises
          </div>
          <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
            {proposedExercises.map((ex, i) => (
              <button
                key={i}
                onClick={() => handleExerciseClick(ex)}
                style={{
                  textAlign: "left",
                  background: T.darkBg,
                  border: `1px solid ${T.border}`,
                  borderRadius: 8,
                  padding: "8px 10px",
                  color: T.textPri,
                  fontSize: 12,
                  cursor: "pointer",
                  transition: "border .15s",
                }}
                onMouseEnter={(e) => { e.currentTarget.style.borderColor = T.accent; }}
                onMouseLeave={(e) => { e.currentTarget.style.borderColor = T.border; }}
              >
                <span style={{ color: T.accentGlow, fontWeight: 600 }}>
                  {ex.concept.replace(/_/g, " ")}
                </span>
                {ex.difficulty && (
                  <span style={{ color: T.textHint, fontSize: 10, marginLeft: 6 }}>
                    {ex.difficulty}
                  </span>
                )}
                <div
                  style={{
                    color: T.textSec,
                    fontSize: 11,
                    marginTop: 4,
                    overflow: "hidden",
                    textOverflow: "ellipsis",
                    whiteSpace: "nowrap",
                  }}
                >
                  <SmartText text={ex.problem_latex} />
                </div>
              </button>
            ))}
          </div>

          <div style={{ display: "flex", gap: 6, marginTop: 10, alignItems: "center" }}>
            {proposedSource === "generated" && ["easy", "medium", "hard"].map((d) => (
              <button
                key={d}
                onClick={() => onRequestExercise?.("generic", d)}
                style={{
                  flex: 1,
                  background: T.surfaceHigh,
                  border: `1px solid ${T.border}`,
                  borderRadius: 6,
                  padding: "4px 0",
                  color: T.textSec,
                  fontSize: 10,
                  cursor: "pointer",
                }}
              >
                {d}
              </button>
            ))}
            <button
              onClick={() => onClearProposals?.()}
              style={{
                padding: "4px 10px",
                borderRadius: 6,
                background: "transparent",
                border: `1px solid ${T.border}`,
                color: T.textHint,
                fontSize: 10,
                cursor: "pointer",
                marginLeft: "auto",
              }}
            >
              ✕ Clear
            </button>
          </div>
        </div>
      )}

      {/* Input */}
      <div style={{ padding: 10, background: T.surface, borderTop: `1px solid ${T.border}` }}>
        <textarea
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault();
              send();
            }
          }}
          placeholder="Ask your math question…"
          rows={3}
          style={{
            width: "100%",
            boxSizing: "border-box",
            resize: "none",
            background: T.surface,
            color: T.textPri,
            border: `1px solid ${T.border}`,
            borderRadius: 10,
            padding: "8px 12px",
            fontSize: 13,
            fontFamily: "inherit",
            outline: "none",
          }}
        />
        <div style={{ display: "flex", justifyContent: "flex-end", alignItems: "center", marginTop: 6, gap: 8 }}>
          {speechSupported && (
            <button
              onClick={startListening}
              title={isListening ? "Listening…" : "Voice input"}
              style={{
                background: isListening ? T.redHint : T.surfaceHigh,
                color: isListening ? "#fff" : T.textSec,
                border: `1px solid ${isListening ? T.redHint : T.border}`,
                borderRadius: 8,
                padding: "6px 10px",
                fontSize: 12,
                cursor: "pointer",
                display: "flex",
                alignItems: "center",
                gap: 4,
                transition: "background .2s, border-color .2s",
              }}
            >
              <span style={{ fontSize: 14 }}>{isListening ? "🎙️" : "🎤"}</span>
              <span style={{ fontSize: 11 }}>{isListening ? "Listening…" : "Voice"}</span>
            </button>
          )}
          <button
            onClick={send}
            style={{
              background: T.accent,
              color: "#fff",
              border: "none",
              borderRadius: 8,
              padding: "6px 16px",
              fontSize: 12,
              fontWeight: 600,
              cursor: "pointer",
            }}
          >
            Send ↵
          </button>
        </div>
      </div>
    </div>
  );
}
