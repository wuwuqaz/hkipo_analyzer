import { describe, expect, it } from "vitest";
import { formatDate, formatDateTime } from "@/lib/utils";

describe("date formatting", () => {
  it("returns fallback for empty or invalid dates", () => {
    expect(formatDate("")).toBe("--");
    expect(formatDate("--")).toBe("--");
    expect(formatDate(undefined)).toBe("--");
    expect(formatDateTime("")).toBe("--");
    expect(formatDateTime("not-a-date")).toBe("--");
  });
});
