import { useRef, useCallback } from "react";

export function useCanvasHistory() {
  const strokesRef = useRef([]);
  const redoStackRef = useRef([]);

  const addStroke = useCallback((stroke) => {
    strokesRef.current.push(stroke);
    redoStackRef.current = [];
  }, []);

  const undo = useCallback((ctx, width, height) => {
    if (!strokesRef.current.length) return false;
    redoStackRef.current.push(strokesRef.current.pop());
    redrawAll(ctx, width, height);
    return true;
  }, []);

  const redo = useCallback((ctx, width, height) => {
    if (!redoStackRef.current.length) return false;
    strokesRef.current.push(redoStackRef.current.pop());
    redrawAll(ctx, width, height);
    return true;
  }, []);

  const clear = useCallback((ctx, width, height) => {
    strokesRef.current = [];
    redoStackRef.current = [];
    ctx.clearRect(0, 0, width, height);
  }, []);

  const redrawAll = useCallback((ctx, width, height) => {
    ctx.clearRect(0, 0, width, height);
    strokesRef.current.forEach((s) => {
      ctx.save();
      ctx.lineCap = "round";
      ctx.lineJoin = "round";
      if (s.tool === "eraser") {
        const ew = s.eraserWidth ?? 20;
        ctx.globalCompositeOperation = "destination-out";
        ctx.beginPath();
        s.points.forEach((pt) => ctx.arc(pt.x, pt.y, ew / 2, 0, Math.PI * 2));
        ctx.fill();
      } else {
        ctx.globalCompositeOperation = "source-over";
        ctx.strokeStyle = s.color;
        ctx.lineWidth = s.width;
        ctx.beginPath();
        s.points.forEach((pt, i) => {
          if (i === 0) ctx.moveTo(pt.x, pt.y);
          else ctx.lineTo(pt.x, pt.y);
        });
        ctx.stroke();
      }
      ctx.restore();
    });
  }, []);

  return {
    strokesRef,
    redoStackRef,
    addStroke,
    undo,
    redo,
    clear,
    redrawAll,
  };
}
