import { create } from "zustand";

export const useTutorStore = create((set) => ({
  proposedExercises: [],
  proposedSource: null,
  lastLatex: "",
  pendingLatex: null,
  activeExercise: false,

  setProposedExercises: (updater) =>
    set((state) => ({
      proposedExercises:
        typeof updater === "function"
          ? updater(state.proposedExercises)
          : updater,
    })),

  setProposedSource: (proposedSource) => set({ proposedSource }),

  setLastLatex: (lastLatex) => set({ lastLatex }),
  setPendingLatex: (pendingLatex) => set({ pendingLatex }),
  setActiveExercise: (activeExercise) => set({ activeExercise }),

  clearProposals: () =>
    set({ proposedExercises: [], proposedSource: null }),

  addExercise: (exercise) =>
    set((state) => ({
      proposedExercises: [...state.proposedExercises, exercise],
    })),

  addExercises: (exercises) =>
    set((state) => ({
      proposedExercises: [...state.proposedExercises, ...exercises],
    })),
}));
