import { describe, expect, it } from "vitest";
import { fillMonths, fmtArea } from "../format";

describe("fmtArea", () => {
  it("switches to km² at one square kilometre", () => {
    expect(fmtArea(999_999)).toBe("999,999 m²");
    expect(fmtArea(2_500_000)).toBe("2.50 km²");
  });
});

describe("fillMonths", () => {
  const m = (month: string, area: number) => ({ month, cleared_area_m2: area, items_destroyed: 0, items_found: 0 });

  it("zero-fills gaps so the time axis is continuous, across a year boundary", () => {
    const filled = fillMonths([m("2025-11", 5), m("2026-02", 7)]);
    expect(filled.map((x) => x.month)).toEqual(["2025-11", "2025-12", "2026-01", "2026-02"]);
    expect(filled.map((x) => x.cleared_area_m2)).toEqual([5, 0, 0, 7]);
  });

  it("handles empty input", () => {
    expect(fillMonths([])).toEqual([]);
  });
});
