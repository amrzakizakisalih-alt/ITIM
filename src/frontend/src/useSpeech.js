import { useState, useRef, useCallback, useEffect } from "react";

/* ── Text-to-speech via Groq Orpheus backend ───────────────────────────── */

let currentAudio = null;
let currentRequestId = 0;
let audioContext = null;
let isAudioUnlocked = false;

/**
 * Unlocks the audio context on iOS/WebKit.
 * MUST be called inside a user gesture (e.g., button click).
 */
export const unlockAudio = () => {
  if (isAudioUnlocked) return;
  isAudioUnlocked = true;

  // Unlock AudioContext for Web Audio API
  if (!audioContext) {
    audioContext = new (window.AudioContext || window.webkitAudioContext)();
  }
  if (audioContext.state === "suspended") {
    audioContext.resume();
  }

  // Unlock speechSynthesis (iOS blocks it until we speak inside a gesture)
  if (window.speechSynthesis) {
    const dummy = new SpeechSynthesisUtterance("");
    dummy.volume = 0;
    window.speechSynthesis.speak(dummy);
    window.speechSynthesis.cancel();
  }

  // Unlock HTMLAudioElement (play a silence)
  const silent = new Audio("data:audio/wav;base64,UklGRigAAABXQVZFZm10IBIAAAABAAEARKwAAIhYAQACABAAAABkYXRhAgAAAAEA");
  silent.play().catch(() => {});
};

const isIOS = () => {
  return /iPad|iPhone|iPod/.test(navigator.userAgent) ||
    (navigator.platform === "MacIntel" && navigator.maxTouchPoints > 1);
};

export const speakText = async (text, onEnd) => {
  const requestId = ++currentRequestId;
  stopSpeaking();
  if (!text) {
    onEnd?.();
    return;
  }

  // On iOS, speechSynthesis is more reliable than fetch+Audio outside a user gesture
  // We still try the backend first (unless we know it won't work)
  const tryBackendFirst = !isIOS();

  if (tryBackendFirst) {
    try {
      const res = await fetch("/api/tts", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ text }),
      });
      if (requestId !== currentRequestId) return;
      if (!res.ok) throw new Error(`HTTP ${res.status}`);

      const blob = await res.blob();
      if (requestId !== currentRequestId) return;

      const url = URL.createObjectURL(blob);
      const audio = new Audio(url);
      currentAudio = audio;

      audio.onended = () => {
        if (requestId === currentRequestId) {
          currentAudio = null;
          URL.revokeObjectURL(url);
          onEnd?.();
        }
      };

      audio.onerror = (e) => {
        console.error("[TTS] Audio playback error:", e);
        if (requestId === currentRequestId) {
          currentAudio = null;
          URL.revokeObjectURL(url);
          onEnd?.();
        }
      };

      await audio.play();
      return; // success
    } catch (err) {
      if (requestId !== currentRequestId) return;
      console.error("[TTS] Backend failed, falling back to native:", err);
    }
  }

  // Native fallback (Web Speech API) — essential on iOS
  if (!window.speechSynthesis) {
    console.warn("[TTS] speechSynthesis not available");
    onEnd?.();
    return;
  }

  const utter = new SpeechSynthesisUtterance(text);
  utter.lang = "en-US";
  utter.rate = 1;
  utter.pitch = 1;
  utter.onend = () => {
    if (requestId === currentRequestId) onEnd?.();
  };
  utter.onerror = (e) => {
    console.error("[TTS] speechSynthesis error:", e);
    if (requestId === currentRequestId) onEnd?.();
  };

  // On iOS, we sometimes need to wait for voices to be loaded
  const voices = window.speechSynthesis.getVoices();
  if (voices.length === 0) {
    await new Promise((resolve) => {
      const handler = () => {
        window.speechSynthesis.removeEventListener("voiceschanged", handler);
        resolve();
      };
      window.speechSynthesis.addEventListener("voiceschanged", handler);
      // Fallback timeout
      setTimeout(resolve, 500);
    });
  }

  window.speechSynthesis.cancel(); // Cancel any ongoing utterance
  window.speechSynthesis.speak(utter);
};

export const stopSpeaking = () => {
  if (currentAudio) {
    currentAudio.pause();
    currentAudio.currentTime = 0;
    currentAudio = null;
  }
  if (window.speechSynthesis) window.speechSynthesis.cancel();
};

/* ── Hook Speech-to-Text via Groq Whisper backend ──────────────────────── */

export function useSpeech() {
  const [isListening, setIsListening] = useState(false);
  const [transcript, setTranscript] = useState("");
  const [speechSupported, setSpeechSupported] = useState(false);
  const mediaRecorderRef = useRef(null);
  const chunksRef = useRef([]);

  useEffect(() => {
    const supported =
      !!window.navigator.mediaDevices?.getUserMedia;
    setSpeechSupported(supported);
  }, []);

  const clearTranscript = useCallback(() => {
    setTranscript("");
  }, []);

  const startListening = useCallback(async () => {
    if (
      mediaRecorderRef.current &&
      mediaRecorderRef.current.state === "recording"
    ) {
      console.log("[STT] Stopping recorder…");
      try {
        mediaRecorderRef.current.stop();
      } catch (e) {
        console.error("[STT] Error stopping recorder:", e);
      }
      return;
    }

    try {
      console.log("[STT] Requesting microphone…");
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });

      const mimeType = MediaRecorder.isTypeSupported("audio/webm")
        ? "audio/webm"
        : MediaRecorder.isTypeSupported("audio/mp4")
        ? "audio/mp4"
        : "";

      const recorder = new MediaRecorder(
        stream,
        mimeType ? { mimeType } : undefined
      );
      mediaRecorderRef.current = recorder;
      chunksRef.current = [];
      setTranscript("");
      setIsListening(true);

      recorder.ondataavailable = (e) => {
        if (e.data.size > 0) {
          chunksRef.current.push(e.data);
          console.log("[STT] Chunk received", e.data.size, "bytes");
        }
      };

      recorder.onstop = async () => {
        console.log("[STT] Recorder stopped, processing…");
        setIsListening(false);
        stream.getTracks().forEach((t) => t.stop());

        if (chunksRef.current.length === 0) {
          console.warn("[STT] No audio chunks collected");
          return;
        }

        const blob = new Blob(chunksRef.current, {
          type: recorder.mimeType || "audio/webm",
        });
        console.log("[STT] Blob ready", blob.size, "bytes", "type:", blob.type);

        const formData = new FormData();
        formData.append("file", blob, "recording.webm");

        try {
          const res = await fetch("/api/transcribe", {
            method: "POST",
            body: formData,
          });
          console.log("[STT] HTTP response", res.status);
          if (!res.ok) {
            const txt = await res.text();
            throw new Error(`HTTP ${res.status}: ${txt}`);
          }
          const data = await res.json();
          console.log("[STT] Transcription:", data.text);
          setTranscript(data.text || "");
        } catch (err) {
          console.error("[STT] Transcription request failed:", err);
        }
      };

      recorder.onerror = (e) => {
        console.error("[STT] Recorder error:", e);
        setIsListening(false);
        stream.getTracks().forEach((t) => t.stop());
      };

      console.log("[STT] Starting recorder…");
      recorder.start();
    } catch (err) {
      console.error("[STT] Failed to start:", err);
      setIsListening(false);
    }
  }, []);

  return {
    speechSupported,
    isListening,
    transcript,
    startListening,
    clearTranscript,
    speakText,
    stopSpeaking,
    unlockAudio,
  };
}
