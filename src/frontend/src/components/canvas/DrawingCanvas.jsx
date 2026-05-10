import { useRef, useEffect, useCallback, useImperativeHandle } from "react";
import { Page_W, Page_H } from "../../constants";
import { useCanvasHistory } from "../../hooks/useCanvasHistory";

export default function DrawingCanvas({
  tool, inkColor, penWidth, eraserWidth, onStrokeFinished, onSendStroke, ref
}) {
  const canvasRef = useRef(null);
  const drawing = useRef(false);
  const activePointerId = useRef(null);
  const lastPt = useRef(null);
  const currentStroke = useRef([]);
  const drawTimeout = useRef(null);

  const { addStroke, undo, redo, clear, redrawAll } = useCanvasHistory();

  // mirror refs to avoid stale closures in handlers
  const toolRef = useRef(tool);
  const inkColorRef = useRef(inkColor);
  const penWidthRef = useRef(penWidth);
  const eraserWidthRef = useRef(eraserWidth);
  useEffect(() => { toolRef.current = tool; }, [tool]);
  useEffect(() => { inkColorRef.current = inkColor; }, [inkColor]);
  useEffect(() => { penWidthRef.current = penWidth; }, [penWidth]);
  useEffect(() => { eraserWidthRef.current = eraserWidth; }, [eraserWidth]);

  useEffect(() => {
    const c = canvasRef.current;
    c.width = Page_W;
    c.height = Page_H;
    console.log("[DrawingCanvas] mounted, onSendStroke=", typeof onSendStroke);
  }, [onSendStroke]);



  useEffect(() => {
    return () => {
      if (drawTimeout.current) clearTimeout(drawTimeout.current);
    };
  }, []);

  useImperativeHandle(ref, () => ({
    undo: () => {
      const c = canvasRef.current;
      if (c) undo(c.getContext("2d"), Page_W, Page_H);
    },
    redo: () => {
      const c = canvasRef.current;
      if (c) redo(c.getContext("2d"), Page_W, Page_H);
    },
    clear: () => {
      const c = canvasRef.current;
      if (c) clear(c.getContext("2d"), Page_W, Page_H);
    },
    getCanvas: () => canvasRef.current,
  }));

  const getPos = (e) => {
    const rect = canvasRef.current.getBoundingClientRect();
    const scaleX = Page_W / rect.width;
    const scaleY = Page_H / rect.height;
    return {
      x: (e.clientX - rect.left) * scaleX,
      y: (e.clientY - rect.top) * scaleY,
    };
  };

  const renderSegment = useCallback((p1, p2, currentTool, currentColor, currentPenWidth, currentEraserWidth) => {
    const ctx = canvasRef.current.getContext("2d");
    ctx.save();
    ctx.lineCap = "round";
    ctx.lineJoin = "round";
    if (currentTool === "eraser") {
      ctx.globalCompositeOperation = "destination-out";
      ctx.beginPath();
      ctx.arc(p2.x, p2.y, currentEraserWidth / 2, 0, Math.PI * 2);
      ctx.fill();
    } else {
      ctx.globalCompositeOperation = "source-over";
      ctx.strokeStyle = currentColor;
      ctx.lineWidth = currentPenWidth;
      ctx.beginPath();
      ctx.moveTo(p1.x, p1.y);
      ctx.lineTo(p2.x, p2.y);
      ctx.stroke();
    }
    ctx.restore();
  }, []);

  const finalizeStroke = useCallback(() => {
    console.log("[DrawingCanvas] finalizeStroke", currentStroke.current.length);
    if (drawTimeout.current) {
      clearTimeout(drawTimeout.current);
      drawTimeout.current = null;
    }
    if (!drawing.current) return;
    drawing.current = false;
    activePointerId.current = null;

    if (currentStroke.current.length > 1) {
      const stroke = {
        points: [...currentStroke.current],
        color: currentStroke.current._color,
        width: currentStroke.current._width,
        tool: currentStroke.current._tool,
        eraserWidth: currentStroke.current._eraserWidth,
      };
      addStroke(stroke);
      console.log("[DrawingCanvas] sending stroke", stroke.points.length, "points");
      onStrokeFinished?.();
      onSendStroke?.(stroke);
    }
    currentStroke.current = [];
    lastPt.current = null;
  }, [addStroke, onStrokeFinished, onSendStroke]);

  // ── iOS / Apple Pencil safety ───────────────────────────────────────────
  // On iOS WebKit, pointerup/pointercancel may not be fired
  // on the canvas if the stylus leaves the element. We listen on window as a fallback.
  useEffect(() => {
    const onGlobalPointerUp = (e) => {
      if (e.pointerId === activePointerId.current) {
        finalizeStroke();
      }
    };
    const onGlobalPointerCancel = (e) => {
      if (e.pointerId === activePointerId.current) {
        finalizeStroke();
      }
    };
    window.addEventListener("pointerup", onGlobalPointerUp);
    window.addEventListener("pointercancel", onGlobalPointerCancel);
    return () => {
      window.removeEventListener("pointerup", onGlobalPointerUp);
      window.removeEventListener("pointercancel", onGlobalPointerCancel);
    };
  }, [finalizeStroke]);

  const handleDrawStart = useCallback((e) => {
    console.log("[DrawingCanvas] pointerDown", toolRef.current);
    if (toolRef.current === "text") return;
    if (e.pointerType === "touch" && e.width > 50) return;
    if (activePointerId.current !== null && activePointerId.current !== e.pointerId) return;

    e.preventDefault();
    try { e.currentTarget.setPointerCapture(e.pointerId); } catch (_) {}

    activePointerId.current = e.pointerId;
    drawing.current = true;

    const pos = getPos(e);
    currentStroke.current = [pos];
    currentStroke.current._color = inkColorRef.current;
    currentStroke.current._width = penWidthRef.current;
    currentStroke.current._tool = toolRef.current;
    currentStroke.current._eraserWidth = eraserWidthRef.current;

    lastPt.current = pos;
    if (drawTimeout.current) clearTimeout(drawTimeout.current);
    drawTimeout.current = setTimeout(finalizeStroke, 2000);
  }, [finalizeStroke]);

  const handleDrawMove = useCallback((e) => {
    if (e.pointerId !== activePointerId.current) return;
    if (!drawing.current || !lastPt.current) return;

    e.preventDefault();
    const pos = getPos(e);
    renderSegment(
      lastPt.current, pos,
      currentStroke.current._tool,
      currentStroke.current._color,
      currentStroke.current._width,
      currentStroke.current._eraserWidth
    );
    currentStroke.current.push(pos);
    lastPt.current = pos;

    if (drawTimeout.current) clearTimeout(drawTimeout.current);
    drawTimeout.current = setTimeout(finalizeStroke, 2000);
  }, [renderSegment, finalizeStroke]);

  const handleDrawEnd = useCallback((e) => {
    if (e.pointerId !== activePointerId.current) return;
    finalizeStroke();
  }, [finalizeStroke]);

  const cursor = tool === "eraser"
    ? `url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='24' height='24'%3E%3Ccircle cx='12' cy='12' r='10' fill='none' stroke='%23888' stroke-width='2'/%3E%3C/svg%3E") 12 12, crosshair`
    : tool === "text"
    ? "text"
    : "crosshair";

  return (
    <canvas
      ref={canvasRef}
      style={{
        position: "absolute",
        top: 0, left: 0,
        width: "100%", height: "100%",
        zIndex: 2,
        cursor,
        touchAction: "none",
        display: "block",
        WebkitUserSelect: "none",
        WebkitTouchCallout: "none",
      }}
      onPointerDown={handleDrawStart}
      onPointerMove={handleDrawMove}
      onPointerUp={handleDrawEnd}
      onPointerCancel={handleDrawEnd}
    />
  );
}
