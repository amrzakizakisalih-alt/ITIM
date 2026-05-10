import { useEffect } from "react";

export function useKeyboardShortcuts({ undo, redo }) {
  useEffect(() => {
    const handler = (e) => {
      if (e.ctrlKey && e.key === "z") {
        e.preventDefault();
        undo?.();
      }
      if (e.ctrlKey && (e.key === "y" || (e.shiftKey && e.key === "Z"))) {
        e.preventDefault();
        redo?.();
      }
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [undo, redo]);
}
