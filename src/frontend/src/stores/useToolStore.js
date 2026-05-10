import { create } from "zustand";

export const useToolStore = create((set) => ({
  tool: "pen",
  setTool: (tool) => set({ tool }),

  inkColor: "#1a1a2e",
  setInkColor: (inkColor) => set({ inkColor }),

  penWidth: 2,
  setPenWidth: (penWidth) => set({ penWidth }),

  eraserWidth: 20,
  setEraserWidth: (eraserWidth) => set({ eraserWidth }),

  textStyle: {
    fontSize: 16,
    fontFamily: "'DM Sans', sans-serif",
    color: "#1a1a2e",
    fontWeight: "normal",
    fontStyle: "normal",
  },
  setTextStyle: (updater) =>
    set((state) => ({
      textStyle:
        typeof updater === "function"
          ? updater(state.textStyle)
          : { ...state.textStyle, ...updater },
    })),
}));
