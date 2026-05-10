import { T, COLORS } from "./constants";
import { useToolStore } from "./stores/useToolStore";

export default function ToolBar({
  onUndo, onRedo, onClear,
  onAddPage, onImport, onMathCheck,
}) {
  const {
    tool, setTool,
    inkColor, setInkColor,
    penWidth, setPenWidth,
    textStyle, setTextStyle,
  } = useToolStore();

  const tools = [
    { id: "pen",       icon: "✏️", label: "Pen" },
    { id: "eraser",    icon: "◻",  label: "Eraser" },
    { id: "text",      icon: "T",  label: "Text" },
  ];

  const actions = [
    { icon: "↩", tip: "Undo (Ctrl+Z)", fn: onUndo },
    { icon: "↪", tip: "Redo (Ctrl+Y)", fn: onRedo },
    { icon: "🗑", tip: "Clear page",    fn: onClear },
    { icon: "＋", tip: "New page",      fn: onAddPage },
    { icon: "📁", tip: "Import file",   fn: onImport },
    { icon: "🧮", tip: "Check answer",  fn: onMathCheck },
  ];

  const isTextTool = tool === "text";

  return (
    <div style={{
      width: 72, background: T.panelBg, borderRight: `1px solid ${T.border}`,
      display: "flex", flexDirection: "column", alignItems: "center",
      padding: "16px 0", gap: 4, flexShrink: 0,
    }}>
      {/* Tool buttons */}
      {tools.map((t) => (
        <button
          key={t.id}
          title={t.label}
          onClick={() => setTool(t.id)}
          style={{
            width: 52, height: 52, borderRadius: 10, border: "none",
            background: tool === t.id ? T.accent : "transparent",
            color: tool === t.id ? "#fff" : T.textSec,
            fontSize: 20, cursor: "pointer", transition: "all .15s",
          }}
        >{t.icon}</button>
      ))}

      <div style={{ height: 1, width: 40, background: T.border, margin: "8px 0" }} />

      {/* ── Text formatting panel (visible only when text tool active) ── */}
      {isTextTool ? (
        <>
          <div style={{ fontSize: 10, color: T.textHint, marginBottom: 4 }}>Aa</div>

          {/* Font size */}
          <select
            value={textStyle.fontSize}
            onChange={(e) => setTextStyle(s => ({ ...s, fontSize: Number(e.target.value) }))}
            style={{
              width: 56, background: T.darkBg, color: T.textPri,
              border: `1px solid ${T.border}`, borderRadius: 6,
              padding: "3px 2px", fontSize: 10, marginBottom: 6,
            }}
          >
            {[10, 12, 14, 16, 18, 20, 24, 28, 32, 40, 48].map(s => (
              <option key={s} value={s}>{s}px</option>
            ))}
          </select>

          {/* Font family */}
          <select
            value={textStyle.fontFamily}
            onChange={(e) => setTextStyle(s => ({ ...s, fontFamily: e.target.value }))}
            style={{
              width: 56, background: T.darkBg, color: T.textPri,
              border: `1px solid ${T.border}`, borderRadius: 6,
              padding: "3px 2px", fontSize: 9, marginBottom: 6,
            }}
          >
            <option value="'DM Sans', sans-serif">Sans</option>
            <option value="'DM Mono', monospace">Mono</option>
            <option value="'Times New Roman', serif">Serif</option>
          </select>

          {/* Bold / Italic */}
          <div style={{ display: "flex", gap: 4, marginBottom: 6 }}>
            <button
              onClick={() => setTextStyle(s => ({ ...s, fontWeight: s.fontWeight === "bold" ? "normal" : "bold" }))}
              style={{
                width: 26, height: 26, borderRadius: 6,
                background: textStyle.fontWeight === "bold" ? T.accent : T.darkBg,
                color: textStyle.fontWeight === "bold" ? "#fff" : T.textSec,
                border: `1px solid ${T.border}`, fontSize: 12, fontWeight: "bold",
                cursor: "pointer",
              }}
            >B</button>
            <button
              onClick={() => setTextStyle(s => ({ ...s, fontStyle: s.fontStyle === "italic" ? "normal" : "italic" }))}
              style={{
                width: 26, height: 26, borderRadius: 6,
                background: textStyle.fontStyle === "italic" ? T.accent : T.darkBg,
                color: textStyle.fontStyle === "italic" ? "#fff" : T.textSec,
                border: `1px solid ${T.border}`, fontSize: 12, fontStyle: "italic",
                cursor: "pointer",
              }}
            >I</button>
          </div>

          {/* Text color */}
          <div style={{ fontSize: 10, color: T.textHint, marginBottom: 4 }}>Color</div>
          <div style={{ display: "flex", flexWrap: "wrap", justifyContent: "center", gap: 4, width: 56 }}>
            {COLORS.map((c) => (
              <button
                key={c.hex}
                title={c.name}
                onClick={() => setTextStyle(s => ({ ...s, color: c.hex }))}
                style={{
                  width: 18, height: 18, borderRadius: "50%", border: "none",
                  background: c.hex, cursor: "pointer",
                  outline: textStyle.color === c.hex ? `2px solid ${T.accentGlow}` : "2px solid transparent",
                  outlineOffset: 1, transition: "outline .1s",
                }}
              />
            ))}
          </div>
        </>
      ) : (
        <>
          {/* Width slider (pen/eraser only) */}
          <div style={{ fontSize: 10, color: T.textHint, marginBottom: 2 }}>╴╴</div>
          <input
            type="range" min={1} max={12} value={penWidth}
            onChange={(e) => setPenWidth(Number(e.target.value))}
            style={{ writingMode: "vertical-lr", direction: "rtl", height: 80, accentColor: T.accent }}
          />
        </>
      )}

      <div style={{ height: 1, width: 40, background: T.border, margin: "8px 0" }} />

      {/* Color palette (for pen only) */}
      {!isTextTool && COLORS.map((c) => (
        <button
          key={c.hex}
          title={c.name}
          onClick={() => setInkColor(c.hex)}
          style={{
            width: 24, height: 24, borderRadius: "50%", border: "none",
            background: c.hex, cursor: "pointer", marginBottom: 4,
            outline: inkColor === c.hex ? `2px solid ${T.accentGlow}` : "2px solid transparent",
            outlineOffset: 2, transition: "outline .1s",
          }}
        />
      ))}

      {!isTextTool && <div style={{ height: 1, width: 40, background: T.border, margin: "8px 0" }} />}

      {/* Actions */}
      {actions.map((a) => (
        <button
          key={a.tip}
          title={a.tip}
          onClick={a.fn}
          style={{
            width: 42, height: 42, borderRadius: 8, border: "none",
            background: "transparent", color: T.textSec,
            fontSize: 18, cursor: "pointer", transition: "all .15s",
          }}
          onMouseEnter={(e) => { e.currentTarget.style.background = T.surfaceHigh; e.currentTarget.style.color = T.textPri; }}
          onMouseLeave={(e) => { e.currentTarget.style.background = "transparent"; e.currentTarget.style.color = T.textSec; }}
        >{a.icon}</button>
      ))}
    </div>
  );
}
