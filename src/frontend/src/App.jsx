import { useRef, useEffect, useCallback } from "react";
import { T, Page_H, Page_W } from "./constants";
import { useWebSocket } from "./useWebSockets";
import { useKeyboardShortcuts } from "./hooks/useKeyboardShortcuts";

import { useToolStore } from "./stores/useToolStore";
import { usePageStore } from "./stores/usePageStore";
import { useTutorStore } from "./stores/useTutorStore";
import { useUIStore } from "./stores/useUIStore";

import PageContainer from "./components/canvas/PageContainer";
import ToolBar from "./ToolBar";
import ChatPanel from "./ChatPanel";
import OptionBar from "./OptionBar";
import StatusBar from "./StatusBar";
import ImportModal from "./importModal";
import MathCheckModal from "./MathCheckModal";
import LatexConfirmToast from "./LatexConfirmToast";

export default function App() {
  // ── Stores ────────────────────────────────────────────────────────────────
  const { textStyle } = useToolStore();

  const { pages, textZones, pushPage, setTextZones } = usePageStore();

  const {
    proposedExercises,
    setProposedExercises,
    proposedSource,
    setProposedSource,
    lastLatex,
    setLastLatex,
    pendingLatex,
    setPendingLatex,
    activeExercise,
    setActiveExercise,
    clearProposals,
    addExercise,
    addExercises,
  } = useTutorStore();

  const {
    chatVisible,
    setChatVisible,
    statusMsg,
    setStatusMsg,
    importModal,
    setImportModal,
    importFile,
    setImportFile,
    mathCheckModal,
    setMathCheckModal,
    wsUrl,
    setWsUrl,
  } = useUIStore();

  // ── Imperative refs ───────────────────────────────────────────────────────
  const canvasRefs = useRef([]);

  // ── WebSocket ─────────────────────────────────────────────────────────────
  const {
    connected: wsConnected,
    send: wsSend,
    onMessage: wsOnMessage,
    lastMessage: wsLastMessage,
  } = useWebSocket(wsUrl || null);

  useEffect(() => wsOnMessage((data) => {
    console.log("[WS]", data);
    if (data.type === "latex_update" && data.latex) {
      setPendingLatex(data.latex);
      setStatusMsg(`LaTeX detected: ${data.latex}`);
    }
    if (data.type === "exercises_proposed" && data.exercises) {
      setProposedExercises(data.exercises);
      setProposedSource(data.source || "generated");
      setStatusMsg(`${data.exercises.length} exercise(s) proposed based on document`);
    }
    if (data.type === "exercise" && data.exercise) {
      addExercise(data.exercise);
    }
    if (data.type === "exercises_detected" && data.exercises) {
      addExercises(data.exercises);
      setStatusMsg(`${data.exercises.length} exercise(s) detected in document`);
    }
    if (data.type === "tutor_message" && data.intervention_type === "exercise_started") {
      setActiveExercise(true);
    }
    if (data.type === "step_feedback" && data.status === "completed") {
      setActiveExercise(false);
    }
    if (data.type === "request_ocr_capture") {
      const pageIdx = data.page_index ?? (canvasRefs.current.length - 1);
      const captureFn = canvasRefs.current[pageIdx]?.captureFullPage;
      if (captureFn) {
        // Allow 100ms for the browser to finalize rendering (iOS)
        setTimeout(() => {
          try {
            const imageData = captureFn();
            if (imageData && imageData.length > 1000) {
              wsSend({ type: "ocr_capture", image_data: imageData, page_index: pageIdx });
            } else {
              console.error("[OCR Capture] Image too small or empty, skipping");
            }
          } catch (err) {
            console.error("[OCR Capture] Failed:", err);
          }
        }, 100);
      }
    }
  }), [wsOnMessage]);

  // ── Pages ─────────────────────────────────────────────────────────────────
  const scrollToBottom = () => setTimeout(() => {
    document.getElementById("book-scroll")?.scrollTo({ top: 99999, behavior: "smooth" });
  }, 120);

  const addPageUI = () => {
    pushPage(null);
    setStatusMsg("Page added");
    scrollToBottom();
  };

  // ── Canvas actions ────────────────────────────────────────────────────────
  const undo  = () => canvasRefs.current[canvasRefs.current.length - 1]?.undo?.();
  const redo  = () => canvasRefs.current[canvasRefs.current.length - 1]?.redo?.();
  const clear = () => {
    canvasRefs.current[canvasRefs.current.length - 1]?.clear?.();
    wsSend({ type: "clear" });
  };

  // ── Import ────────────────────────────────────────────────────────────────
  const handleImportClick = () => {
    const input = document.createElement("input");
    input.type = "file";
    input.accept = "image/*,.pdf";
    input.onchange = (e) => {
      const file = e.target.files[0];
      if (file) { setImportFile(file); setImportModal(true); }
    };
    input.click();
  };

  // ── Math Check ────────────────────────────────────────────────────────────
  const handleMathCheckSubmit = (userLatex, correctLatex) => {
    wsSend({
      type: "math_submit",
      user_latex: userLatex,
      correct_latex: correctLatex,
      timestamp: Date.now(),
    });
    setStatusMsg("Answer submitted for evaluation");
  };

  const handleEmbed = useCallback(async (file, dataUrl, pageCount) => {
    const isPdf = file.type === "application/pdf";
    setStatusMsg(`Importing "${file.name}"…`);

    if (!isPdf) {
      pushPage({ type: "image", dataUrl });
      setStatusMsg(`📎 "${file.name}" embedded — 1 page added`);
      wsSend({ type: "document_imported", name: file.name, text: "", timestamp: Date.now() });
      scrollToBottom();
      return;
    }

    try {
      const { getPdfDocument } = await import("./pdfService.js");
      const pdf = await getPdfDocument(dataUrl);
      const numPages = pdf.numPages;

      for (let p = 1; p <= numPages; p++) {
        setStatusMsg(`Rendering page ${p}/${numPages} of "${file.name}"…`);
        const page     = await pdf.getPage(p);
        const vp0      = page.getViewport({ scale: 1 });
        const scale    = Math.min(Page_W / vp0.width, Page_H / vp0.height);
        const viewport = page.getViewport({ scale });

        const offscreen  = document.createElement("canvas");
        offscreen.width  = Page_W;
        offscreen.height = Page_H;
        const ctx = offscreen.getContext("2d");
        ctx.fillStyle = T.pageBg;
        ctx.fillRect(0, 0, Page_W, Page_H);
        const dx = (Page_W - viewport.width)  / 2;
        const dy = (Page_H - viewport.height) / 2;
        await page.render({ canvasContext: ctx, viewport, transform: [1, 0, 0, 1, dx, dy] }).promise;

        const bitmap = await createImageBitmap(offscreen);
        pushPage({ type: "pdf_canvas", imageData: bitmap });
      }

      setStatusMsg(`Extracting text from "${file.name}"…`);
      let fullText = "";
      try {
        for (let p = 1; p <= numPages; p++) {
          const page = await pdf.getPage(p);
          const textContent = await page.getTextContent();
          const pageText = textContent.items.map(item => item.str).join(" ");
          fullText += pageText + "\n";
        }
      } catch (textErr) {
        console.warn("Could not extract PDF text:", textErr);
      }

      wsSend({
        type: "document_imported",
        name: file.name,
        text: fullText,
        timestamp: Date.now(),
      });

      setStatusMsg(`📎 "${file.name}" embedded — ${numPages} page${numPages > 1 ? "s" : ""} added`);
      scrollToBottom();
    } catch (err) {
      console.error(err);
      setStatusMsg(`⚠️ Could not render PDF: ${err.message}`);
    }
  }, [wsSend]);

  const handleFeedAI = useCallback(async (file, dataUrl) => {
    const isPdf = file.type === "application/pdf";
    setStatusMsg(`Analyzing "${file.name}" for AI…`);

    if (!isPdf) {
      wsSend({
        type: "document_imported",
        name: file.name,
        text: "",
        image_data: dataUrl,
        feed_only: true,
        timestamp: Date.now(),
      });
      setStatusMsg(`🧠 "${file.name}" sent to AI for OCR…`);
      return;
    }

    try {
      const { getPdfDocument } = await import("./pdfService.js");
      const pdf = await getPdfDocument(dataUrl);
      const numPages = pdf.numPages;

      setStatusMsg(`Extracting text from "${file.name}"…`);
      let fullText = "";
      try {
        for (let p = 1; p <= numPages; p++) {
          const page = await pdf.getPage(p);
          const textContent = await page.getTextContent();
          const pageText = textContent.items.map(item => item.str).join(" ");
          fullText += pageText + "\n";
        }
      } catch (textErr) {
        console.warn("Could not extract PDF text:", textErr);
      }

      wsSend({
        type: "document_imported",
        name: file.name,
        text: fullText,
        feed_only: true,
        timestamp: Date.now(),
      });

      setStatusMsg(`🧠 "${file.name}" analyzed — ${numPages} page${numPages > 1 ? "s" : ""} fed to AI`);
    } catch (err) {
      console.error(err);
      setStatusMsg(`⚠️ Could not analyze PDF: ${err.message}`);
    }
  }, [wsSend]);

  // ── Stroke → WebSocket ────────────────────────────────────────────────────
  const handleSendStroke = useCallback((stroke) => {
    wsSend({
      type:      "stroke",
      points:    stroke.points,
      color:     stroke.color,
      width:     stroke.width,
      tool:      stroke.tool,
      highlight: stroke.highlight,
      timestamp: Date.now(),
    });
  }, [wsSend]);

  const handleTextZonesChange = useCallback((pageId, zones) => {
    setTextZones(pageId, zones);
  }, [setTextZones]);

  const handleTextZoneSubmit = useCallback((pageId, zoneId, text) => {
    wsSend({
      type: "text_zone_update",
      page_id: pageId,
      zone_id: zoneId,
      text,
      timestamp: Date.now(),
    });
  }, [wsSend]);

  // ── Keyboard shortcuts ────────────────────────────────────────────────────
  useKeyboardShortcuts({ undo, redo });

  return (
    <div style={{ display: "flex", flexDirection: "column", height: "100vh", background: T.darkBg, color: T.textPri, overflow: "hidden", fontFamily: "'DM Sans','Segoe UI',sans-serif" }}>
      <style>{`
        @import url('https://fonts.googleapis.com/css2?family=DM+Sans:wght@400;600&family=DM+Mono:wght@400;500&display=swap');
        * { box-sizing: border-box; margin: 0; padding: 0; }
        ::-webkit-scrollbar { width: 6px; }
        ::-webkit-scrollbar-track { background: ${T.darkBg}; }
        ::-webkit-scrollbar-thumb { background: ${T.border}; border-radius: 3px; }
        ::-webkit-scrollbar-thumb:hover { background: ${T.accent}; }
        input[type=range]::-webkit-slider-thumb { appearance:none; width:14px; height:14px; border-radius:50%; background:${T.accent}; }
        select option { background: ${T.surfaceHigh}; }
        textarea, button { font-family: inherit; outline: none; }

        /* ── Tablet responsive ── */
        @media (max-width: 1024px) {
          #book-scroll { padding: 8px 0 20px !important; }
          .chat-panel { width: 280px !important; }
        }
        @media (max-width: 768px) {
          .chat-panel { width: 240px !important; }
        }
        @media (max-width: 640px) {
          .chat-panel { display: none !important; }
        }
      `}</style>

      <OptionBar wsConnected={wsConnected} />

      <div style={{ display: "flex", flex: 1, overflow: "hidden" }}>
        <ToolBar
          onUndo={undo} onRedo={redo} onClear={clear}
          onAddPage={addPageUI} onImport={handleImportClick}
          onMathCheck={() => setMathCheckModal(true)}
        />

        <div id="book-scroll" style={{ flex: 1, overflowY: "auto", overflowX: "hidden", background: T.darkBg, padding: "20px 0 40px", display: "flex", flexDirection: "column", alignItems: "center" }}>
          {pages.map((page, i) => (
            <PageContainer
              key={`${page.id}`}
              pageNum={i + 1}
              pageId={page.id}
              importedBackground={page.importedBackground}
              onStrokeFinished={() => setStatusMsg(`Stroke on page ${i + 1}`)}
              onSendStroke={handleSendStroke}
              ref={(el) => { canvasRefs.current[i] = el; }}
              textZones={textZones[page.id] || []}
              onTextZonesChange={(zones) => handleTextZonesChange(page.id, zones)}
              onTextZoneSubmit={(zoneId, text) => handleTextZoneSubmit(page.id, zoneId, text)}
            />
          ))}
        </div>

        {chatVisible ? (
          <div style={{ position: "relative", display: "flex", height: "100%" }}>
            {pendingLatex && (
              <div style={{ position: "absolute", top: 12, right: "calc(100% + 12px)", zIndex: 1100 }}>
                <LatexConfirmToast
                  latex={pendingLatex}
                  onYes={() => {
                    if (activeExercise) {
                      wsSend({
                        type: "math_submit",
                        user_latex: pendingLatex,
                        timestamp: Date.now(),
                      });
                      setStatusMsg("Answer submitted for checking");
                      setPendingLatex(null);
                    } else {
                      setLastLatex(pendingLatex);
                      setPendingLatex(null);
                      setMathCheckModal(true);
                    }
                  }}
                  onNo={() => {
                    setLastLatex("");
                    setPendingLatex(null);
                    setMathCheckModal(true);
                  }}
                  onDismiss={() => setPendingLatex(null)}
                />
              </div>
            )}
            <ChatPanel
              visible={true}
              onMessage={(t) => wsSend({ type: "user_message", text: t, timestamp: Date.now() })}
              wsConnected={wsConnected}
              wsLastMessage={wsLastMessage}
              proposedExercises={proposedExercises}
              onRequestExercise={(concept, diff) => wsSend({ type: "exercise_request", concept, difficulty: diff })}
              onStartExercise={(ex) => {
                clearProposals();
                wsSend({ type: "start_exercise", exercise: ex, timestamp: Date.now() });
              }}
              onClearProposals={clearProposals}
            />
          </div>
        ) : (
          <ChatPanel
            visible={false}
            onMessage={(t) => wsSend({ type: "user_message", text: t, timestamp: Date.now() })}
            wsConnected={wsConnected}
            wsLastMessage={wsLastMessage}
            proposedExercises={proposedExercises}
            onRequestExercise={(concept, diff) => wsSend({ type: "exercise_request", concept, difficulty: diff })}
            onStartExercise={(ex) => {
              clearProposals();
              wsSend({ type: "start_exercise", exercise: ex, timestamp: Date.now() });
            }}
            onClearProposals={clearProposals}
          />
        )}
      </div>

      <StatusBar pageCount={pages.length} msg={statusMsg} />

      {importModal && importFile && (
        <ImportModal
          file={importFile}
          onClose={() => { setImportModal(false); setImportFile(null); }}
          onEmbed={handleEmbed}
          onFeedAI={handleFeedAI}
        />
      )}

      {mathCheckModal && (
        <MathCheckModal
          lastLatex={lastLatex}
          onClose={() => setMathCheckModal(false)}
          onSubmit={handleMathCheckSubmit}
        />
      )}

    </div>
  );
}
