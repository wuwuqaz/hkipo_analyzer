import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { ScoreBadge } from "@/components/results/ScoreBadge";

describe("ScoreBadge", () => {
  it("renders the label text", () => {
    render(<ScoreBadge label="积极申购" />);
    expect(screen.getByText("积极申购")).toBeDefined();
  });

  it("applies success tone for positive labels", () => {
    const { container } = render(<ScoreBadge label="积极申购" />);
    expect(container.firstElementChild?.className).toContain("success");
  });

  it("applies danger tone for negative labels", () => {
    const { container } = render(<ScoreBadge label="建议跳过" />);
    expect(container.firstElementChild?.className).toContain("danger");
  });

  it("applies accent tone for neutral labels", () => {
    const { container } = render(<ScoreBadge label="中性试水" />);
    expect(container.firstElementChild?.className).toContain("accent");
  });

  it("renders unknown label gracefully", () => {
    const { container } = render(<ScoreBadge label="未知标签" />);
    expect(container.firstElementChild?.className).toContain("foreground");
  });
});
