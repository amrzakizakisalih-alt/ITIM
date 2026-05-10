import { describe, it, expect } from "vitest";
import { usePageStore } from "../usePageStore";

describe("usePageStore", () => {
  it("has a default page", () => {
    expect(usePageStore.getState().pages.length).toBe(1);
  });

  it("adds a page", () => {
    const initial = usePageStore.getState().pages.length;
    usePageStore.getState().pushPage(null);
    expect(usePageStore.getState().pages.length).toBe(initial + 1);
  });

  it("adds and retrieves text zones", () => {
    const pageId = 1;
    const zone = { id: "z1", x: 10, y: 20, text: "hello" };
    usePageStore.getState().addTextZone(pageId, zone);
    expect(usePageStore.getState().getTextZones(pageId)).toContainEqual(zone);
  });

  it("updates a text zone", () => {
    const pageId = 1;
    usePageStore.getState().updateTextZone(pageId, "z1", { text: "world" });
    const z = usePageStore.getState().getTextZones(pageId).find((zz) => zz.id === "z1");
    expect(z.text).toBe("world");
  });

  it("deletes a text zone", () => {
    const pageId = 1;
    usePageStore.getState().removeTextZone(pageId, "z1");
    expect(usePageStore.getState().getTextZones(pageId).find((zz) => zz.id === "z1")).toBeUndefined();
  });
});
