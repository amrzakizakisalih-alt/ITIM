import { useRef, useEffect } from "react";
import { T, Page_H, Page_W } from "./constants";

export default function PageCanvas({
    pageNum, tool, inkColor, penWidth, eraserWidth, importedBackground,
    onStrokeFinished, onSendStroke, canvasRefCb
}) {
    const bgCanvasRef = useRef(null);      
    const drawingCanvasRef = useRef(null); 
    
    const drawing = useRef(false);
    const lastPt = useRef(null);
    const currentStroke = useRef([]);
    const strokes = useRef([]);
    const redoStack = useRef([]);

    // ─── 1. GESTION DU FOND (PDF ou IMAGE) ───
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
                img.onload = () => {
                    ctx.drawImage(img, 0, 0, Page_W, Page_H);
                };
                img.src = importedBackground.dataUrl;
            }
        }
    }, [importedBackground]);

    // ─── 2. INITIALISATION DU CALQUE DE DESSIN ───
    useEffect(() => {
        const c = drawingCanvasRef.current;
        c.width = Page_W;
        c.height = Page_H;
        if (canvasRefCb) canvasRefCb(c);
    }, []);

    const getPos = (e) => {
        const rect = drawingCanvasRef.current.getBoundingClientRect();
        // Calcul du ratio entre la taille réelle du canvas et sa taille affichée à l'écran
        const scaleX = Page_W / rect.width;
        const scaleY = Page_H / rect.height;
        const src = e.touches ? e.touches[0] : e;
        return {
            x: (src.clientX - rect.left) * scaleX,
            y: (src.clientY - rect.top) * scaleY,
        };
    };

    const renderSegment = (p1, p2) => {
        const ctx = drawingCanvasRef.current.getContext("2d");
        ctx.save();
        ctx.lineCap = "round";
        ctx.lineJoin = "round";

        if (tool === "eraser") {
            ctx.globalCompositeOperation = "destination-out";
            ctx.beginPath();
            ctx.arc(p2.x, p2.y, eraserWidth / 2, 0, Math.PI * 2);
            ctx.fill();
        } else {
            ctx.globalCompositeOperation = "source-over";
            ctx.strokeStyle = inkColor;
            ctx.lineWidth = penWidth;
            ctx.beginPath();
            ctx.moveTo(p1.x, p1.y);
            ctx.lineTo(p2.x, p2.y);
            ctx.stroke();
        }
        ctx.restore();
    };

    const onPointerDown = (e) => {
        e.preventDefault();
        drawing.current = true;
        const pos = getPos(e);
        currentStroke.current = [pos];
        lastPt.current = pos;
        redoStack.current = [];
    };

    const onPointerMove = (e) => {
        e.preventDefault();
        if (!drawing.current || !lastPt.current) return;
        const pos = getPos(e);
        renderSegment(lastPt.current, pos);
        currentStroke.current.push(pos);
        lastPt.current = pos;
    };

    const onPointerUp = (e) => {
        e.preventDefault();
        if (!drawing.current) return;
        drawing.current = false;

        if (currentStroke.current.length > 1) {
            const stroke = {
                points: [...currentStroke.current],
                color: inkColor,
                width: penWidth,
                tool: tool 
            };
            strokes.current.push(stroke);
            onStrokeFinished?.();
            onSendStroke?.(stroke);
        }
        currentStroke.current = [];
        lastPt.current = null;
    };

    // ─── 3. ACTIONS UNDO / REDO ───
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
    }, []);

    const redrawAll = () => {
        const c = drawingCanvasRef.current;
        const ctx = c.getContext("2d");
        ctx.clearRect(0, 0, Page_W, Page_H);
        
        strokes.current.forEach((s) => {
            ctx.save();
            ctx.lineCap = "round";
            ctx.lineJoin = "round";
            if (s.tool === "eraser") {
                ctx.globalCompositeOperation = "destination-out";
                ctx.beginPath();
                s.points.forEach(pt => ctx.arc(pt.x, pt.y, eraserWidth / 2, 0, Math.PI * 2));
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
    };

    const cursor = tool === "eraser"
        ? `url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='24' height='24'%3E%3Ccircle cx='12' cy='12' r='10' fill='none' stroke='%23888' stroke-width='2'/%3E%3C/svg%3E") 12 12, crosshair`
        : "crosshair";

    return (
        <div style={{ 
            display: "flex", 
            flexDirection: "column", 
            alignItems: "center", 
            marginBottom: 40,
            width: "100%" // Prend toute la largeur du scrollarea
        }}>
            <div style={{ fontSize: 11, color: T.textHint, marginBottom: 8, fontFamily: "'DM Mono', monospace" }}>
                PAGE {pageNum}
            </div>
            
            {/* Le conteneur de la page */}
            <div style={{
                position: "relative",
                width: "90%",           // Largeur relative pour tablette
                maxWidth: `${Page_W}px`, // Largeur max réelle (794px)
                backgroundColor: T.pageBg,
                boxShadow: "0 10px 30px rgba(0,0,0,0.5)",
                borderRadius: 4,
                overflow: "hidden",
                // On force le ratio A4
                aspectRatio: `${Page_W} / ${Page_H}`
            }}>
                {/* CALQUE 1 : FOND */}
                <canvas
                    ref={bgCanvasRef}
                    style={{
                        position: "absolute",
                        top: 0, left: 0,
                        width: "100%", height: "100%",
                        zIndex: 1,
                        display: "block"
                    }}
                />

                {/* CALQUE 2 : DESSIN */}
                <canvas
                    ref={drawingCanvasRef}
                    style={{
                        position: "absolute",
                        top: 0, left: 0,
                        width: "100%", height: "100%",
                        zIndex: 2,
                        cursor,
                        touchAction: "none",
                        display: "block"
                    }}
                    onMouseDown={onPointerDown}
                    onMouseMove={onPointerMove}
                    onMouseUp={onPointerUp}
                    onMouseLeave={onPointerUp}
                    onTouchStart={onPointerDown}
                    onTouchMove={onPointerMove}
                    onTouchEnd={onPointerUp}
                />
            </div>
        </div>
    );
}