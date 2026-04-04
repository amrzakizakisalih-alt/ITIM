import { T, COLORS } from "./constants";

export default function ToolBar({ tool, setTool, inkColor, setInkColor, penWidth, setPenWidth,
    onUndo, onRedo, onClear, onAddPage, onImport }) {
   
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
    ];
   
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
   
        {/* Width slider */}
        <div style={{ fontSize: 10, color: T.textHint, marginBottom: 2 }}>╴╴</div>
        <input
          type="range" min={1} max={12} value={penWidth}
          onChange={(e) => setPenWidth(Number(e.target.value))}
          style={{ writingMode: "vertical-lr", direction: "rtl", height: 80, accentColor: T.accent }}
        />
   
        <div style={{ height: 1, width: 40, background: T.border, margin: "8px 0" }} />
   
        {/* Color palette */}
        {COLORS.map((c) => (
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
   
        <div style={{ height: 1, width: 40, background: T.border, margin: "8px 0" }} />
   
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