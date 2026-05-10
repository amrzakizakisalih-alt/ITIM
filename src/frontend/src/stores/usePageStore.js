import { create } from "zustand";

let _pageCounter = 1;

export const usePageStore = create((set, get) => ({
  pages: [{ id: 1, importedBackground: null }],
  textZones: {}, // { pageId: [zone, ...] }

  pushPage: (bg = null) => {
    _pageCounter += 1;
    const newId = _pageCounter;
    set((state) => ({
      pages: [...state.pages, { id: newId, importedBackground: bg }],
      textZones: { ...state.textZones, [newId]: [] },
    }));
    return newId;
  },

  setPageBackground: (pageId, bg) =>
    set((state) => ({
      pages: state.pages.map((p) =>
        p.id === pageId ? { ...p, importedBackground: bg } : p
      ),
    })),

  // ── Text zones helpers ──────────────────────────────────────────────────
  setTextZones: (pageId, zones) =>
    set((state) => ({
      textZones: { ...state.textZones, [pageId]: zones },
    })),

  updateTextZone: (pageId, zoneId, updates) =>
    set((state) => {
      const zones = state.textZones[pageId] || [];
      return {
        textZones: {
          ...state.textZones,
          [pageId]: zones.map((z) =>
            z.id === zoneId ? { ...z, ...updates } : z
          ),
        },
      };
    }),

  addTextZone: (pageId, zone) =>
    set((state) => ({
      textZones: {
        ...state.textZones,
        [pageId]: [...(state.textZones[pageId] || []), zone],
      },
    })),

  removeTextZone: (pageId, zoneId) =>
    set((state) => ({
      textZones: {
        ...state.textZones,
        [pageId]: (state.textZones[pageId] || []).filter(
          (z) => z.id !== zoneId
        ),
      },
    })),

  getTextZones: (pageId) => get().textZones[pageId] || [],
}));
