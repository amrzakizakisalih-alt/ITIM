import React from "react";
import { T, COLORS, Page_W, Page_H } from "../../constants";

export default function TextZone({
  zone,
  isSelected,
  textStyle,
  onPointerDown,
  onClick,
  onBlur,
  onKeyDown,
  onFocus,
  onDelete,
  onDuplicate,
  onColorChange,
  onRotate,
  onFontSizeChange,
  onToggleLock,
  onResizePointerDown,
}) {
  const [editText, setEditText] = React.useState(zone.text || "");

  React.useEffect(() => {
    setEditText(zone.text || "");
  }, [zone.text]);

  return (
    <div
      style={{
        position: "absolute",
        left: `${(zone.x / Page_W) * 100}%`,
        top: `${(zone.y / Page_H) * 100}%`,
        width: zone.width,
        height: zone.height,
        zIndex: 3,
        cursor: zone.locked ? "default" : "grab",
        transform: `rotate(${zone.rotation || 0}deg)`,
        transformOrigin: "center center",
      }}
    >
      {/* Editable text zone */}
      <textarea
        value={editText}
        onChange={(e) => setEditText(e.target.value)}
        onPointerDown={onPointerDown}
        onClick={onClick}
        onBlur={(e) => onBlur?.(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === "Escape") {
            e.currentTarget.blur();
            return;
          }
          onKeyDown?.(e);
        }}
        onFocus={onFocus}
        readOnly={zone.locked}
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
          resize: "none",
          cursor: zone.locked ? "default" : "text",
        }}
      />

      {/* Controls (visible unless locked) */}
      {isSelected && !zone.locked && (
        <>
          <div
            onClick={onDuplicate}
            title="Duplicate zone"
            style={ctrlBtnStyle(T.accentGlow, { top: -10, left: -10 })}
          >⧉</div>

          <div
            onClick={() => onRotate(-15)}
            title="Rotate left"
            style={ctrlBtnStyle(T.surfaceHigh, { top: -10, left: 14 })}
          >↺</div>

          <div
            onClick={() => onRotate(15)}
            title="Rotate right"
            style={ctrlBtnStyle(T.surfaceHigh, { top: -10, left: 36 })}
          >↻</div>

          <div
            onClick={() => onFontSizeChange(-2)}
            title="Decrease font size"
            style={ctrlBtnStyle(T.surfaceHigh, { top: -10, right: 58, fontSize: 9 })}
          >A⁻</div>

          <div
            onClick={() => onFontSizeChange(2)}
            title="Increase font size"
            style={ctrlBtnStyle(T.surfaceHigh, { top: -10, right: 36, fontSize: 11 })}
          >A⁺</div>

          <div
            onClick={onDelete}
            title="Delete zone"
            style={ctrlBtnStyle(T.redHint || "#ef4444", { top: -10, right: -10, fontSize: 12 })}
          >×</div>
        </>
      )}

      {/* Lock button */}
      {isSelected && (
        <div
          onClick={onToggleLock}
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
              onClick={() => onColorChange(c.hex)}
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

      {/* Resize handles */}
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
          onPointerDown={(e) => onResizePointerDown(e, dir)}
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
}

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
