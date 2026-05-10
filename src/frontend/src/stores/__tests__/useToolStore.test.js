import { describe, it, expect } from "vitest";
import { useToolStore } from "../useToolStore";

describe("useToolStore", () => {
  it("has the default tool 'pen'", () => {
    expect(useToolStore.getState().tool).toBe("pen");
  });

  it("switches tool", () => {
    useToolStore.getState().setTool("eraser");
    expect(useToolStore.getState().tool).toBe("eraser");
    useToolStore.getState().setTool("pen"); // reset
  });

  it("updates the color", () => {
    useToolStore.getState().setInkColor("#ff0000");
    expect(useToolStore.getState().inkColor).toBe("#ff0000");
  });

  it("updates the text style", () => {
    useToolStore.getState().setTextStyle({ fontSize: 24 });
    expect(useToolStore.getState().textStyle.fontSize).toBe(24);
    expect(useToolStore.getState().textStyle.fontFamily).toBe("'DM Sans', sans-serif");
  });
});
