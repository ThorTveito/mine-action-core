import { describe, expect, it } from "vitest";
import { roleCan } from "../auth";
import { bboxOf } from "../ItemList";

describe("roleCan mirrors the API's permission matrix", () => {
  it("keeps data entry separate from QA and release", () => {
    expect(roleCan("editor", "write")).toBe(true);
    expect(roleCan("editor", "release")).toBe(false);
    expect(roleCan("qa_officer", "release")).toBe(true);
    expect(roleCan("qa_officer", "write")).toBe(false);
  });

  it("gives surveyors only field reporting", () => {
    expect(roleCan("surveyor", "report")).toBe(true);
    expect(roleCan("surveyor", "view_reports")).toBe(false);
    expect(roleCan("surveyor", "write")).toBe(false);
  });

  it("gives anonymous visitors nothing", () => {
    expect(roleCan(undefined, "write")).toBe(false);
  });
});

describe("bboxOf", () => {
  it("covers every ring of a multipolygon", () => {
    const coords = [
      [[[1, 1], [2, 1], [2, 2], [1, 1]]],
      [[[5, -1], [6, 0], [5, 0], [5, -1]]],
    ];
    expect(bboxOf(coords)).toEqual([1, -1, 6, 2]);
  });
});
