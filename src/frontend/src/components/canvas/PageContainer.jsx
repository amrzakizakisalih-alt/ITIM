import { useRef, useState, useEffect, useCallback, forwardRef, useImperativeHandle } from "react";
import { T, Page_W, Page_H, COLORS } from "../../constants";
import { useToolStore } from "../../stores/useToolStore";
import DrawingCanvas from "./DrawingCanvas";
import TextZone from "./TextZone";

const GRID_SIZE = 20;
function snapToGrid(v) {
  return Math.round(v / GRID_SIZE) * GRID_SIZE;
}

const PageContainer = forwardRef(function PageContainer(
  {
    pageNum,
    pageId,
    importedBackground,
    onStrokeFinished,
    onSendStroke,
    textZones,
    onTextZonesChange,
    onTextZoneSubmit,
  },
  ref
) {
  const { tool, inkColor, penWidth, eraserWidth, textStyle } = useToolStore();

  const bgCanvasRef = useRef(null);
  const containerRef = useRef(null);
  const zoneIdCounter = useRef(0);

  useEffect(() => {
    zoneIdCounter.current = 0;
  }, [pageId]);

  // ── Background ────────────────────────────────────────────────────────────
  useEffect(() => {
    const c = bgCanvasRef.current;
    c.width = Page_W;
    c.height = Page_H;
    const ctx = c.getContext("2d");
    ctx.fillStyle = T.pageBg;
    ctx.fillRect(0, 0, Page_W, Page_H);

    if (importedBackground) {
      if (importedBackground.type === "pdf_canvas") {
        ctx.drawImage(importedBackground.imageData, 0, 0);
      } else if (importedBackground.type === "image") {
        const img = new Image();
        img.crossOrigin = "anonymous";
        img.onload = () => {
          ctx.drawImage(img, 0, 0, Page_W, Page_H);
        };
        img.src = importedBackground.dataUrl;
      }
    }
  }, [importedBackground]);

  // ── Drawing canvas ref ────────────────────────────────────────────────────
  const drawingRef = useRef(null);

  useImperativeHandle(ref, () => ({
    undo: () => drawingRef.current?.undo?.(),
    redo: () => drawingRef.current?.redo?.(),
    clear: () => drawingRef.current?.clear?.(),
    captureFullPage: () => {
      const fullCanvas = document.createElement("canvas");
      fullCanvas.width = Page_W;
      fullCanvas.height = Page_H;
      const ctx = fullCanvas.getContext("2d");
      ctx.fillStyle = "#ffffff";
      ctx.fillRect(0, 0, Page_W, Page_H);
      if (bgCanvasRef.current) ctx.drawImage(bgCanvasRef.current, 0, 0);
      if (drawingRef.current?.getCanvas) ctx.drawImage(drawingRef.current.getCanvas(), 0, 0);
      // JPEG is lighter than PNG for mobile network transfer
      return fullCanvas.toDataURL("image/jpeg", 0.85);
    },
  }));

  // ── Text zones state ──────────────────────────────────────────────────────
  const [selectedZoneId, setSelectedZoneId] = useState(null);
  const [draggingZoneId, setDraggingZoneId] = useState(null);
  const dragOffset = useRef({ x: 0, y: 0 });
  const [resizingZoneId, setResizingZoneId] = useState(null);
  const resizeDir = useRef(null);
  const resizeStart = useRef({ x: 0, y: 0, w: 0, h: 0, zx: 0, zy: 0 });

  const handleContainerClick = useCallback((e) => {
    if (tool !== "text") return;
    const rect = containerRef.current.getBoundingClientRect();
    const scaleX = Page_W / rect.width;
    const scaleY = Page_H / rect.height;
    const x = (e.clientX - rect.left) * scaleX;
    const y = (e.clientY - rect.top) * scaleY;

    const newZone = {
      id: `tz-${pageId}-${Date.now()}-${++zoneIdCounter.current}`,
      x: Math.max(0, Math.min(x - 60, Page_W - 120)),
      y: Math.max(0, Math.min(y - 10, Page_H - 30)),
      width: 160,
      height: 40,
      text: "",
      style: { ...textStyle },
    };
    onTextZonesChange?.([...(textZones || []), newZone]);
    setSelectedZoneId(newZone.id);
  }, [tool, textStyle, pageId, textZones, onTextZonesChange]);

  const handleZonePointerDown = useCallback((e, zoneId) => {
    e.stopPropagation();
    const zone = (textZones || []).find((z) => z.id === zoneId);
    if (zone?.locked) return;
    try { e.currentTarget.setPointerCapture(e.pointerId); } catch (_) {}
    setSelectedZoneId(zoneId);
    setDraggingZoneId(zoneId);
    const rect = containerRef.current.getBoundingClientRect();
    if (zone) {
      dragOffset.current = {
        x: e.clientX - rect.left - (zone.x / Page_W) * rect.width,
        y: e.clientY - rect.top - (zone.y / Page_H) * rect.height,
      };
    }
  }, [textZones]);

  const handleContainerPointerMove = useCallback((e) => {
    const rect = containerRef.current.getBoundingClientRect();
    const scaleX = Page_W / rect.width;
    const scaleY = Page_H / rect.height;

    if (draggingZoneId) {
      const newX = (e.clientX - rect.left - dragOffset.current.x) * scaleX;
      const newY = (e.clientY - rect.top - dragOffset.current.y) * scaleY;
      onTextZonesChange?.(
        (textZones || []).map((z) =>
          z.id === draggingZoneId
            ? {
                ...z,
                x: Math.max(0, snapToGrid(Math.min(newX, Page_W - z.width))),
                y: Math.max(0, snapToGrid(Math.min(newY, Page_H - z.height))),
              }
            : z
        )
      );
    }

    if (resizingZoneId) {
      const dx = (e.clientX - resizeStart.current.x) * scaleX;
      const dy = (e.clientY - resizeStart.current.y) * scaleY;
      const dir = resizeDir.current;
      onTextZonesChange?.(
        (textZones || []).map((z) => {
          if (z.id !== resizingZoneId) return z;
          let updates = {};
          if (dir.includes("e")) updates.width = snapToGrid(Math.max(40, resizeStart.current.w + dx));
          if (dir.includes("s")) updates.height = snapToGrid(Math.max(20, resizeStart.current.h + dy));
          if (dir.includes("w")) {
            const newW = snapToGrid(Math.max(40, resizeStart.current.w - dx));
            updates.width = newW;
            updates.x = snapToGrid(resizeStart.current.zx + (resizeStart.current.w - newW));
          }
          if (dir.includes("n")) {
            const newH = snapToGrid(Math.max(20, resizeStart.current.h - dy));
            updates.height = newH;
            updates.y = snapToGrid(resizeStart.current.zy + (resizeStart.current.h - newH));
          }
          return { ...z, ...updates };
        })
      );
    }
  }, [draggingZoneId, resizingZoneId, textZones, onTextZonesChange]);

  const handleContainerPointerUp = useCallback(() => {
    setDraggingZoneId(null);
    setResizingZoneId(null);
    resizeDir.current = null;
  }, []);

  const handleZoneBlur = useCallback((zoneId, text) => {
    // Fallback cleanup for old HTML data
    const clean = String(text || "")
      .replace(/<br\s*\/?>/gi, "\n")
      .replace(/<[^>]+>/g, "");
    onTextZonesChange?.(
      (textZones || []).map((z) => (z.id === zoneId ? { ...z, text: clean } : z))
    );
    onTextZoneSubmit?.(zoneId, clean);
  }, [textZones, onTextZonesChange, onTextZoneSubmit]);

  const handleZoneKeyDown = useCallback((e, zoneId) => {
    if ((e.key === "Delete" || e.key === "Backspace") && e.target.value === "") {
      e.preventDefault();
      onTextZonesChange?.((textZones || []).filter((z) => z.id !== zoneId));
      setSelectedZoneId(null);
    }
  }, [textZones, onTextZonesChange]);

  const handleDeleteZone = useCallback((zoneId) => {
    onTextZonesChange?.((textZones || []).filter((z) => z.id !== zoneId));
    setSelectedZoneId(null);
  }, [textZones, onTextZonesChange]);

  const handleDuplicateZone = useCallback((zoneId) => {
    const zone = (textZones || []).find((z) => z.id === zoneId);
    if (!zone) return;
    const copy = {
      ...zone,
      id: `tz-${pageId}-${Date.now()}-${++zoneIdCounter.current}`,
      x: snapToGrid(Math.min(zone.x + 20, Page_W - zone.width)),
      y: snapToGrid(Math.min(zone.y + 20, Page_H - zone.height)),
    };
    onTextZonesChange?.([...(textZones || []), copy]);
    setSelectedZoneId(copy.id);
  }, [textZones, onTextZonesChange, pageId]);

  const handleZoneColorChange = useCallback((zoneId, color) => {
    onTextZonesChange?.(
      (textZones || []).map((z) =>
        z.id === zoneId ? { ...z, style: { ...z.style, color } } : z
      )
    );
  }, [textZones, onTextZonesChange]);

  const handleRotateZone = useCallback((zoneId, delta) => {
    onTextZonesChange?.(
      (textZones || []).map((z) =>
        z.id === zoneId ? { ...z, rotation: ((z.rotation || 0) + delta) % 360 } : z
      )
    );
  }, [textZones, onTextZonesChange]);

  const handleFontSizeChange = useCallback((zoneId, delta) => {
    onTextZonesChange?.(
      (textZones || []).map((z) => {
        if (z.id !== zoneId) return z;
        const current = z.style?.fontSize || textStyle.fontSize || 16;
        const next = Math.max(8, Math.min(72, current + delta));
        return { ...z, style: { ...z.style, fontSize: next } };
      })
    );
  }, [textZones, onTextZonesChange, textStyle]);

  const handleToggleLock = useCallback((zoneId) => {
    onTextZonesChange?.(
      (textZones || []).map((z) =>
        z.id === zoneId ? { ...z, locked: !z.locked } : z
      )
    );
  }, [textZones, onTextZonesChange]);

  const handleResizePointerDown = useCallback((e, zoneId, dir) => {
    e.stopPropagation();
    e.preventDefault();
    const zone = (textZones || []).find((z) => z.id === zoneId);
    if (zone?.locked) return;
    try { e.currentTarget.setPointerCapture(e.pointerId); } catch (_) {}
    setResizingZoneId(zoneId);
    resizeDir.current = dir;
    if (zone) {
      resizeStart.current = {
        x: e.clientX,
        y: e.clientY,
        w: zone.width,
        h: zone.height,
        zx: zone.x,
        zy: zone.y,
      };
    }
  }, [textZones]);

  return (
    <div style={{
      display: "flex",
      flexDirection: "column",
      alignItems: "center",
      marginBottom: 40,
      width: "100%",
    }}>
      <div style={{ fontSize: 11, color: T.textHint, marginBottom: 8, fontFamily: "'DM Mono', monospace" }}>
        PAGE {pageNum}
      </div>

      <div
        ref={containerRef}
        onClick={handleContainerClick}
        onPointerMove={handleContainerPointerMove}
        onPointerUp={handleContainerPointerUp}
        onPointerLeave={handleContainerPointerUp}
        style={{
          position: "relative",
          width: "90%",
          maxWidth: `${Page_W}px`,
          backgroundColor: T.pageBg,
          boxShadow: "0 10px 30px rgba(0,0,0,0.5)",
          borderRadius: 4,
          overflow: "hidden",
          aspectRatio: `${Page_W} / ${Page_H}`,
          cursor: tool === "text" ? "text" : "default",
          touchAction: "none",
          userSelect: "none",
          WebkitUserSelect: "none",
          WebkitTouchCallout: "none",
        }}
      >
        {/* LAYER 1: BACKGROUND */}
        <canvas
          ref={bgCanvasRef}
          style={{
            position: "absolute",
            top: 0, left: 0,
            width: "100%", height: "100%",
            zIndex: 1,
            display: "block",
          }}
        />

        {/* LAYER 2: DRAWING */}
        <DrawingCanvas
          ref={drawingRef}
          tool={tool}
          inkColor={inkColor}
          penWidth={penWidth}
          eraserWidth={eraserWidth}
          onStrokeFinished={onStrokeFinished}
          onSendStroke={onSendStroke}
        />

        {/* LAYER 3: TEXT ZONES */}
        {(textZones || []).map((zone) => {
          const isSelected = selectedZoneId === zone.id;
          return (
            <TextZone
              key={zone.id}
              zone={zone}
              isSelected={isSelected}
              textStyle={textStyle}
              onPointerDown={(e) => handleZonePointerDown(e, zone.id)}
              onClick={(e) => e.stopPropagation()}
              onBlur={(e) => handleZoneBlur(zone.id, e.currentTarget.innerHTML)}
              onKeyDown={(e) => handleZoneKeyDown(e, zone.id)}
              onFocus={() => setSelectedZoneId(zone.id)}
              onDelete={() => handleDeleteZone(zone.id)}
              onDuplicate={() => handleDuplicateZone(zone.id)}
              onColorChange={(color) => handleZoneColorChange(zone.id, color)}
              onRotate={(delta) => handleRotateZone(zone.id, delta)}
              onFontSizeChange={(delta) => handleFontSizeChange(zone.id, delta)}
              onToggleLock={() => handleToggleLock(zone.id)}
              onResizePointerDown={(e, dir) => handleResizePointerDown(e, zone.id, dir)}
            />
          );
        })}
      </div>
    </div>
  );
});

export default PageContainer;
