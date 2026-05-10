import { useRef, useEffect, useState, useCallback } from "react";
import { T, Page_H, Page_W, COLORS } from "./constants";
import { useToolStore } from "./stores/useToolStore";

const GRID_SIZE = 20;
function snapToGrid(v) {
    return Math.round(v / GRID_SIZE) * GRID_SIZE;
}

/** Normalizes pointer / touch coordinates for dragging text zones */
function pointerPos(e) {
    if (e.touches && e.touches.length > 0) {
        return { clientX: e.touches[0].clientX, clientY: e.touches[0].clientY };
    }
    return { clientX: e.clientX, clientY: e.clientY };
}

export default function PageCanvas({
    pageNum, importedBackground,
    onStrokeFinished, onSendStroke, canvasRefCb,
    pageId, textZones, onTextZonesChange, onTextZoneSubmit,
}) {
    const { tool, inkColor, penWidth, eraserWidth, textStyle } = useToolStore();
    const bgCanvasRef = useRef(null);
    const drawingCanvasRef = useRef(null);
    const containerRef = useRef(null);
    const zoneIdCounter = useRef(0);

    // Store current values in refs to avoid stale closures
    const toolRef = useRef(tool);
    const inkColorRef = useRef(inkColor);
    const penWidthRef = useRef(penWidth);
    const eraserWidthRef = useRef(eraserWidth);
    useEffect(() => { toolRef.current = tool; }, [tool]);
    useEffect(() => { inkColorRef.current = inkColor; }, [inkColor]);
    useEffect(() => { penWidthRef.current = penWidth; }, [penWidth]);
    useEffect(() => { eraserWidthRef.current = eraserWidth; }, [eraserWidth]);

    const drawing = useRef(false);
    const activePointerId = useRef(null);
    const lastPt = useRef(null);
    const currentStroke = useRef([]);
    const strokes = useRef([]);
    const redoStack = useRef([]);
    const drawTimeout = useRef(null);

    useEffect(() => {
        zoneIdCounter.current = 0;
    }, [pageId]);

    // ── Text zones state ────────────────────────────────────────────────────
    const [selectedZoneId, setSelectedZoneId] = useState(null);
    const [draggingZoneId, setDraggingZoneId] = useState(null);
    const dragOffset = useRef({ x: 0, y: 0 });
    const [resizingZoneId, setResizingZoneId] = useState(null);
    const resizeDir = useRef(null);
    const resizeStart = useRef({ x: 0, y: 0, w: 0, h: 0, zx: 0, zy: 0 });

    // ─── 1. BACKGROUND MANAGEMENT (PDF or IMAGE) ───
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

    // ─── 2. DRAWING LAYER INITIALIZATION ───
    useEffect(() => {
        const c = drawingCanvasRef.current;
        c.width = Page_W;
        c.height = Page_H;
        if (canvasRefCb) canvasRefCb(c);
    }, []);

    // Cleanup timeout on unmount
    useEffect(() => {
        return () => {
            if (drawTimeout.current) clearTimeout(drawTimeout.current);
        };
    }, []);

    const getPos = (e) => {
        const rect = drawingCanvasRef.current.getBoundingClientRect();
        const scaleX = Page_W / rect.width;
        const scaleY = Page_H / rect.height;
        // Pointer Events have clientX/clientY directly — no need for .touches
        return {
            x: (e.clientX - rect.left) * scaleX,
            y: (e.clientY - rect.top) * scaleY,
        };
    };

    const renderSegment = useCallback((p1, p2, currentTool, currentColor, currentPenWidth, currentEraserWidth) => {
        const ctx = drawingCanvasRef.current.getContext("2d");
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

    // ── Stroke finalization ─────────────────────────────────────────────
    const finalizeStroke = useCallback(() => {
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
            strokes.current.push(stroke);
            onStrokeFinished?.();
            onSendStroke?.(stroke);
        }
        currentStroke.current = [];
        lastPt.current = null;
    }, [onStrokeFinished, onSendStroke]);

    // ── Drawing handlers — Pointer Events ONLY ─────────────────────────
    const handleDrawStart = useCallback((e) => {
        if (toolRef.current === "text") return;

        // Palm rejection: ignore touches that are too large (palm)
        if (e.pointerType === "touch" && e.width > 50) return;

        // Only one active pointer at a time
        if (activePointerId.current !== null && activePointerId.current !== e.pointerId) return;

        e.preventDefault();

        // setPointerCapture ensures pointerup/cancel are delivered even if the stylus leaves the canvas
        try { e.currentTarget.setPointerCapture(e.pointerId); } catch (_) {}

        activePointerId.current = e.pointerId;
        drawing.current = true;

        const pos = getPos(e);

        // Store values at the start of the stroke to avoid stale closures
        currentStroke.current = [pos];
        currentStroke.current._color = inkColorRef.current;
        currentStroke.current._width = penWidthRef.current;
        currentStroke.current._tool = toolRef.current;
        currentStroke.current._eraserWidth = eraserWidthRef.current;

        lastPt.current = pos;
        redoStack.current = [];

        // Fallback timer if pointerup does not fire (rare iOS Safari bug)
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

        // Reset the timer on every move
        if (drawTimeout.current) clearTimeout(drawTimeout.current);
        drawTimeout.current = setTimeout(finalizeStroke, 2000);
    }, [renderSegment, finalizeStroke]);

    const handleDrawEnd = useCallback((e) => {
        if (e.pointerId !== activePointerId.current) return;
        finalizeStroke();
    }, [finalizeStroke]);

    // ─── 3. UNDO / REDO ACTIONS ───
    const redrawAll = useCallback(() => {
        const c = drawingCanvasRef.current;
        const ctx = c.getContext("2d");
        ctx.clearRect(0, 0, Page_W, Page_H);

        strokes.current.forEach((s) => {
            ctx.save();
            ctx.lineCap = "round";
            ctx.lineJoin = "round";
            if (s.tool === "eraser") {
                // Use the eraserWidth stored in the stroke, not the current value
                const ew = s.eraserWidth ?? eraserWidthRef.current;
                ctx.globalCompositeOperation = "destination-out";
                ctx.beginPath();
                s.points.forEach(pt => ctx.arc(pt.x, pt.y, ew / 2, 0, Math.PI * 2));
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

    useEffect(() => {
        const el = drawingCanvasRef.current;
        el._undo = () => {
            if (!strokes.current.length) return;
            redoStack.current.push(strokes.current.pop());
            redrawAll();
        };
        el._redo = () => {
            if (!redoStack.current.length) return;
            strokes.current.push(redoStack.current.pop());
            redrawAll();
        };
        el._clear = () => {
            strokes.current = [];
            redoStack.current = [];
            const ctx = el.getContext("2d");
            ctx.clearRect(0, 0, Page_W, Page_H);
        };
        el._captureFullPage = () => {
            const fullCanvas = document.createElement("canvas");
            fullCanvas.width = Page_W;
            fullCanvas.height = Page_H;
            const ctx = fullCanvas.getContext("2d");
            ctx.fillStyle = "#ffffff";
            ctx.fillRect(0, 0, Page_W, Page_H);
            if (bgCanvasRef.current) ctx.drawImage(bgCanvasRef.current, 0, 0);
            if (drawingCanvasRef.current) ctx.drawImage(drawingCanvasRef.current, 0, 0);
            return fullCanvas.toDataURL("image/png");
        };
    }, [redrawAll]);

    // ── Text zone: create on container click ────────────────────────────────
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

    // ── Text zone: drag handlers — Pointer Events ────────────────────────────
    const handleZonePointerDown = useCallback((e, zoneId) => {
        e.stopPropagation();
        const zone = (textZones || []).find(z => z.id === zoneId);
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
                (textZones || []).map(z =>
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
                (textZones || []).map(z => {
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

    // ── Text zone: edit & delete ────────────────────────────────────────────
    const handleZoneBlur = useCallback((zoneId, html) => {
        const text = html.replace(/<br\s*\/?>/gi, "\n").replace(/<[^>]+>/g, "");
        onTextZonesChange?.(
            (textZones || []).map(z => z.id === zoneId ? { ...z, text } : z)
        );
        onTextZoneSubmit?.(zoneId, text);
    }, [textZones, onTextZonesChange, onTextZoneSubmit]);

    const handleZoneKeyDown = useCallback((e, zoneId) => {
        if ((e.key === "Delete" || e.key === "Backspace") && e.target.innerText === "") {
            e.preventDefault();
            onTextZonesChange?.((textZones || []).filter(z => z.id !== zoneId));
            setSelectedZoneId(null);
        }
    }, [textZones, onTextZonesChange]);

    const handleDeleteZone = useCallback((zoneId) => {
        onTextZonesChange?.((textZones || []).filter(z => z.id !== zoneId));
        setSelectedZoneId(null);
    }, [textZones, onTextZonesChange]);

    const handleDuplicateZone = useCallback((zoneId) => {
        const zone = (textZones || []).find(z => z.id === zoneId);
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
            (textZones || []).map(z =>
                z.id === zoneId ? { ...z, style: { ...z.style, color } } : z
            )
        );
    }, [textZones, onTextZonesChange]);

    const handleRotateZone = useCallback((zoneId, delta) => {
        onTextZonesChange?.(
            (textZones || []).map(z =>
                z.id === zoneId ? { ...z, rotation: ((z.rotation || 0) + delta) % 360 } : z
            )
        );
    }, [textZones, onTextZonesChange]);

    const handleFontSizeChange = useCallback((zoneId, delta) => {
        onTextZonesChange?.(
            (textZones || []).map(z => {
                if (z.id !== zoneId) return z;
                const current = z.style?.fontSize || textStyle.fontSize || 16;
                const next = Math.max(8, Math.min(72, current + delta));
                return { ...z, style: { ...z.style, fontSize: next } };
            })
        );
    }, [textZones, onTextZonesChange, textStyle]);

    const handleToggleLock = useCallback((zoneId) => {
        onTextZonesChange?.(
            (textZones || []).map(z =>
                z.id === zoneId ? { ...z, locked: !z.locked } : z
            )
        );
    }, [textZones, onTextZonesChange]);

    const handleResizePointerDown = useCallback((e, zoneId, dir) => {
        e.stopPropagation();
        e.preventDefault();
        const zone = (textZones || []).find(z => z.id === zoneId);
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

    const cursor = tool === "eraser"
        ? `url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='24' height='24'%3E%3Ccircle cx='12' cy='12' r='10' fill='none' stroke='%23888' stroke-width='2'/%3E%3C/svg%3E") 12 12, crosshair`
        : tool === "text"
        ? "text"
        : "crosshair";

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

                {/* LAYER 2: DRAWING — Pointer Events ONLY (no Mouse/Touch) */}
                <canvas
                    ref={drawingCanvasRef}
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

                {/* LAYER 3: TEXT ZONES */}
                {(textZones || []).map((zone) => {
                    const isSelected = selectedZoneId === zone.id;
                    return (
                        <div
                            key={zone.id}
                            style={{
                                position: "absolute",
                                left: `${(zone.x / Page_W) * 100}%`,
                                top: `${(zone.y / Page_H) * 100}%`,
                                width: zone.width,
                                height: zone.height,
                                zIndex: 3,
                                cursor: zone.locked ? "default" : (draggingZoneId === zone.id ? "grabbing" : "grab"),
                                transform: `rotate(${zone.rotation || 0}deg)`,
                                transformOrigin: "center center",
                            }}
                        >
                            {/* Editable text zone */}
                            <div
                                contentEditable
                                suppressContentEditableWarning
                                // dangerouslySetInnerHTML avoids React reconciliation on a contentEditable
                                dangerouslySetInnerHTML={{ __html: zone.text }}
                                onPointerDown={(e) => handleZonePointerDown(e, zone.id)}
                                onClick={(e) => e.stopPropagation()}
                                onBlur={(e) => handleZoneBlur(zone.id, e.currentTarget.innerHTML)}
                                onKeyDown={(e) => handleZoneKeyDown(e, zone.id)}
                                onFocus={() => setSelectedZoneId(zone.id)}
                                style={{
                                    width: "100%",
                                    height: "100%",
                                    fontSize: zone.style?.fontSize || textStyle.fontSize,
                                    fontFamily: zone.style?.fontFamily || textStyle.fontFamily,
                                    color: zone.style?.color || textStyle.color,
                                    fontWeight: zone.style?.fontWeight || textStyle.fontWeight,
                                    fontStyle: zone.style?.fontStyle || textStyle.fontStyle,
                                    background: isSelected ? "rgba(124, 106, 247, 0.08)" : "transparent",
                                    border: isSelected ? `1.5px dashed ${T.accent}` : "1.5px dashed transparent",
                                    borderRadius: 4,
                                    padding: "4px 6px",
                                    outline: "none",
                                    whiteSpace: "pre-wrap",
                                    wordBreak: "break-word",
                                    lineHeight: 1.4,
                                    overflow: "auto",
                                    boxSizing: "border-box",
                                }}
                            />

                            {/* Controls (visible unless locked) */}
                            {isSelected && !zone.locked && (
                                <>
                                    {/* Duplicate button */}
                                    <div
                                        onClick={(e) => { e.stopPropagation(); handleDuplicateZone(zone.id); }}
                                        title="Duplicate zone"
                                        style={ctrlBtnStyle(T.accentGlow, { top: -10, left: -10 })}
                                    >⧉</div>

                                    {/* Rotate left ↺ */}
                                    <div
                                        onClick={(e) => { e.stopPropagation(); handleRotateZone(zone.id, -15); }}
                                        title="Rotate left"
                                        style={ctrlBtnStyle(T.surfaceHigh, { top: -10, left: 14 })}
                                    >↺</div>

                                    {/* Rotate right ↻ */}
                                    <div
                                        onClick={(e) => { e.stopPropagation(); handleRotateZone(zone.id, 15); }}
                                        title="Rotate right"
                                        style={ctrlBtnStyle(T.surfaceHigh, { top: -10, left: 36 })}
                                    >↻</div>

                                    {/* A- */}
                                    <div
                                        onClick={(e) => { e.stopPropagation(); handleFontSizeChange(zone.id, -2); }}
                                        title="Decrease font size"
                                        style={ctrlBtnStyle(T.surfaceHigh, { top: -10, right: 58, fontSize: 9 })}
                                    >A⁻</div>

                                    {/* A+ */}
                                    <div
                                        onClick={(e) => { e.stopPropagation(); handleFontSizeChange(zone.id, 2); }}
                                        title="Increase font size"
                                        style={ctrlBtnStyle(T.surfaceHigh, { top: -10, right: 36, fontSize: 11 })}
                                    >A⁺</div>

                                    {/* Delete button */}
                                    <div
                                        onClick={(e) => { e.stopPropagation(); handleDeleteZone(zone.id); }}
                                        title="Delete zone"
                                        style={ctrlBtnStyle(T.redHint || "#ef4444", { top: -10, right: -10, fontSize: 12 })}
                                    >×</div>
                                </>
                            )}

                            {/* Lock button (always visible if selected) */}
                            {isSelected && (
                                <div
                                    onClick={(e) => { e.stopPropagation(); handleToggleLock(zone.id); }}
                                    title={zone.locked ? "Unlock zone" : "Lock zone"}
                                    style={ctrlBtnStyle(
                                        zone.locked ? T.amberWarn : T.greenOk,
                                        { top: -10, right: zone.locked ? -10 : 14 }
                                    )}
                                >
                                    {zone.locked ? "🔒" : "🔓"}
                                </div>
                            )}

                            {/* Color palette */}
                            {isSelected && !zone.locked && (
                                <div style={{
                                    position: "absolute",
                                    bottom: -22,
                                    left: "50%",
                                    transform: "translateX(-50%)",
                                    display: "flex",
                                    gap: 4,
                                    zIndex: 10,
                                    background: T.surface,
                                    padding: "2px 6px",
                                    borderRadius: 12,
                                    boxShadow: "0 2px 6px rgba(0,0,0,0.3)",
                                }}>
                                    {COLORS.map((c) => (
                                        <div
                                            key={c.hex}
                                            onClick={(e) => { e.stopPropagation(); handleZoneColorChange(zone.id, c.hex); }}
                                            title={c.name}
                                            style={{
                                                width: 14,
                                                height: 14,
                                                borderRadius: "50%",
                                                background: c.hex,
                                                cursor: "pointer",
                                                border: (zone.style?.color || textStyle.color) === c.hex
                                                    ? "2px solid #fff"
                                                    : "2px solid transparent",
                                                boxShadow: "inset 0 0 0 1px rgba(0,0,0,0.2)",
                                            }}
                                        />
                                    ))}
                                </div>
                            )}

                            {/* Resize handles — Pointer Events */}
                            {isSelected && !zone.locked && [
                                { dir: "nw", style: { top: -4, left: -4, cursor: "nw-resize" } },
                                { dir: "n",  style: { top: -4, left: "50%", transform: "translateX(-50%)", cursor: "n-resize" } },
                                { dir: "ne", style: { top: -4, right: -4, cursor: "ne-resize" } },
                                { dir: "w",  style: { top: "50%", left: -4, transform: "translateY(-50%)", cursor: "w-resize" } },
                                { dir: "e",  style: { top: "50%", right: -4, transform: "translateY(-50%)", cursor: "e-resize" } },
                                { dir: "sw", style: { bottom: -4, left: -4, cursor: "sw-resize" } },
                                { dir: "s",  style: { bottom: -4, left: "50%", transform: "translateX(-50%)", cursor: "s-resize" } },
                                { dir: "se", style: { bottom: -4, right: -4, cursor: "se-resize" } },
                            ].map(({ dir, style }) => (
                                <div
                                    key={dir}
                                    onPointerDown={(e) => handleResizePointerDown(e, zone.id, dir)}
                                    style={{
                                        position: "absolute",
                                        width: 8,
                                        height: 8,
                                        background: T.accent,
                                        borderRadius: "50%",
                                        zIndex: 10,
                                        ...style,
                                    }}
                                />
                            ))}
                        </div>
                    );
                })}
            </div>
        </div>
    );
}

/** Helper for text zone control buttons */
function ctrlBtnStyle(bg, overrides = {}) {
    return {
        position: "absolute",
        width: 18,
        height: 18,
        borderRadius: "50%",
        background: bg,
        color: "#fff",
        fontSize: 10,
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        cursor: "pointer",
        zIndex: 10,
        boxShadow: "0 1px 3px rgba(0,0,0,0.3)",
        userSelect: "none",
        ...overrides,
    };
}
