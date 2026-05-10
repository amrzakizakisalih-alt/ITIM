import { create } from "zustand";

export const useUIStore = create((set) => ({
  chatVisible: true,
  setChatVisible: (chatVisible) => set({ chatVisible }),

  statusMsg: "ITIM ready · Draw on the page · Ctrl+Z undo · Ctrl+Y redo",
  setStatusMsg: (statusMsg) => set({ statusMsg }),

  importModal: false,
  setImportModal: (importModal) => set({ importModal }),

  importFile: null,
  setImportFile: (importFile) => set({ importFile }),

  mathCheckModal: false,
  setMathCheckModal: (mathCheckModal) => set({ mathCheckModal }),

  wsUrl: (() => {
    const proto = window.location.protocol === "https:" ? "wss:" : "ws:";
    const port =
      window.location.port ||
      (window.location.protocol === "https:" ? "443" : "80");
    const portSuffix = port === "443" || port === "80" ? "" : `:${port}`;
    return `${proto}//${window.location.hostname}${portSuffix}/ws`;
  })(),
  setWsUrl: (wsUrl) => set({ wsUrl }),
}));
