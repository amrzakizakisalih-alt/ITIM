import { useState, useRef, useEffect, useCallback } from "react";
import { T,Page_H,Page_W } from "./constants";
import { useWebSocket } from "./useWebSockets";
import PageCanvas from "./Page";
import ToolBar from "./ToolBar";
import ChatPanel from "./ChatPanel";
import OptionBar from "./OptionBar";
import StatusBar from "./StatusBar";
import ImportModal from "./importModal";



export default function App() {
  const [tool, setTool]           = useState("pen");
  const [inkColor, setInkColor]   = useState("#1a1a2e");
  const [penWidth, setPenWidth]   = useState(2);
  const [chatVisible, setChatVisible] = useState(true);
  const [statusMsg, setStatusMsg] = useState("ITIM ready · Draw on the page · Ctrl+Z undo · Ctrl+Y redo");
  const [wsUrl, setWsUrl]         = useState("");
  const [pages, setPages]         = useState([{ id: 1, importedBackground: null }]);
  const [importFile, setImportFile]   = useState(null);
  const [importModal, setImportModal] = useState(false);
  const canvasRefs  = useRef([]);
  const pageCounter = useRef(1);

  const { connected: wsConnected, send: wsSend, onMessage: wsOnMessage } = useWebSocket(wsUrl || null);
  useEffect(() => wsOnMessage((data) => console.log("[WS]", data)), [wsOnMessage]);

  const scrollToBottom = () => setTimeout(() => {
    document.getElementById("book-scroll")?.scrollTo({ top: 99999, behavior: "smooth" });
  }, 120);

  // Add one or many pages
  const pushPage = (bg = null) => {
    pageCounter.current += 1;
    setPages(prev => [...prev, { id: pageCounter.current, importedBackground: bg }]);
  };

  const addPageUI = () => { pushPage(null); setStatusMsg("Page added"); scrollToBottom(); };

  const undo  = () => canvasRefs.current[canvasRefs.current.length - 1]?._undo?.();
  const redo  = () => canvasRefs.current[canvasRefs.current.length - 1]?._redo?.();
  const clear = () => canvasRefs.current[canvasRefs.current.length - 1]?._clear?.();

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

  /**
   * Embed handler:
   *  - Image → 1 new page with image centered as background
   *  - PDF   → N new pages, each rendered from pdf.js at PAGE_W×PAGE_H
   */
  const handleEmbed = useCallback(async (file, dataUrl, pageCount) => {
    const isPdf = file.type === "application/pdf";
    setStatusMsg(`Importing "${file.name}"…`);

    if (!isPdf) {
      pushPage({ type: "image", dataUrl });
      setStatusMsg(`📎 "${file.name}" embedded — 1 page added`);
      scrollToBottom();
      return;
    }
    

    // PDF path: render via pdf.js
    try {
      if (!window.pdfjsLib) {
        await new Promise((res, rej) => {
          const s = document.createElement("script");
          s.src = "https://cdnjs.cloudflare.com/ajax/libs/pdf.js/3.11.174/pdf.min.js";
          s.onload = res; s.onerror = rej;
          document.head.appendChild(s);
        });
        window.pdfjsLib.GlobalWorkerOptions.workerSrc =
          "https://cdnjs.cloudflare.com/ajax/libs/pdf.js/3.11.174/pdf.worker.min.js";
      }

      const base64 = dataUrl.split(",")[1];
      const binary = atob(base64);
      const bytes  = new Uint8Array(binary.length);
      for (let i = 0; i < binary.length; i++) bytes[i] = binary.charCodeAt(i);

      const pdf      = await window.pdfjsLib.getDocument({ data: bytes }).promise;
      const numPages = pdf.numPages;

      // Render pages sequentially, push one canvas page per PDF page
      for (let p = 1; p <= numPages; p++) {page
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
        // Center the rendered page
        const dx = (Page_W - viewport.width)  / 2;
        const dy = (Page_H - viewport.height) / 2;
        await page.render({ canvasContext: ctx, viewport, transform: [1, 0, 0, 1, dx, dy] }).promise;

        const bitmap = await createImageBitmap(offscreen);
        pushPage({ type: "pdf_canvas", imageData: bitmap });
      }

      setStatusMsg(`📎 "${file.name}" embedded — ${numPages} page${numPages > 1 ? "s" : ""} added`);
      scrollToBottom();
    } catch (err) {
      console.error(err);
      setStatusMsg(`⚠️ Could not render PDF: ${err.message}`);
    }
  }, []);

  const handleSendStroke = useCallback((stroke) => {
    wsSend({ type: "stroke", points: stroke.points, color: stroke.color, width: stroke.width, highlight: stroke.highlight, timestamp: Date.now() });
  }, [wsSend]);

  useEffect(() => {
    const handler = (e) => {
      if (e.ctrlKey && e.key === "z") { e.preventDefault(); undo(); }
      if (e.ctrlKey && (e.key === "y" || (e.shiftKey && e.key === "Z"))) { e.preventDefault(); redo(); }
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, []);

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
      `}</style>

      <OptionBar chatVisible={chatVisible} setChatVisible={setChatVisible} wsConnected={wsConnected} wsUrl={wsUrl} setWsUrl={setWsUrl} />

      <div style={{ display: "flex", flex: 1, overflow: "hidden" }}>
        <ToolBar tool={tool} setTool={setTool} inkColor={inkColor} setInkColor={setInkColor}
          penWidth={penWidth} setPenWidth={setPenWidth}
          onUndo={undo} onRedo={redo} onClear={clear} onAddPage={addPageUI} onImport={handleImportClick}
        />

        <div id="book-scroll" style={{ flex: 1, overflowY: "auto", overflowX: "hidden", background: T.darkBg, padding: "20px 0 40px", display: "flex", flexDirection: "column", alignItems: "center" }}>
          {pages.map((page, i) => (
            <PageCanvas
              key={`${page.id}`}
              pageNum={i + 1}
              tool={tool} inkColor={inkColor} penWidth={penWidth} eraserWidth={20}
              importedBackground={page.importedBackground}
              onStrokeFinished={() => setStatusMsg(`Stroke on page ${i + 1}`)}
              onSendStroke={handleSendStroke}
              canvasRefCb={(el) => { canvasRefs.current[i] = el; }}
            />
          ))}
        </div>

        <ChatPanel visible={chatVisible} onMessage={(t) => wsSend({ type: "user_message", text: t, timestamp: Date.now() })} wsConnected={wsConnected} />
      </div>

      <StatusBar pageCount={pages.length} msg={statusMsg} />

      {importModal && importFile && (
        <ImportModal
          file={importFile}
          onClose={() => { setImportModal(false); setImportFile(null); }}
          onEmbed={handleEmbed}
        />
      )}
    </div>
  );
}