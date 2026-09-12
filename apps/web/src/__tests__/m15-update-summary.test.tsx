import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import M15UpdateSummary from "@/components/M15UpdateSummary";

afterEach(cleanup);

const uses = [
  { compositionId: "c-1111", occurrenceId: "o-aaaa", verdict: "COMPATIBLE_AS_IS" as const },
  { compositionId: "c-1112", occurrenceId: "o-bbbb", verdict: "COMPATIBLE_VIA_DETERMINISTIC_TRANSLATION" as const },
  { compositionId: "c-1113", occurrenceId: "o-cccc", verdict: "REQUIRES_REVIEW" as const },
  { compositionId: "c-1114", occurrenceId: "o-dddd", verdict: "INCOMPATIBLE" as const },
];

describe("shows exact four-verdict impact groups", () => {
  it("renders all four groups with counts and per-row identity", () => {
    render(<M15UpdateSummary uses={uses} />);
    expect(
      screen.getByText(/Compatible as-is/i).textContent,
    ).toContain("1");
    expect(
      screen.getByText(/Compatible via deterministic translation/i)
        .textContent,
    ).toContain("1");
    expect(screen.getByText(/Requires review/i).textContent).toContain("1");
    expect(screen.getByText(/Incompatible/i).textContent).toContain("1");
    const rows = screen.getAllByTestId("m15-use-row");
    expect(rows).toHaveLength(4);
    for (const row of rows) {
      expect(row.getAttribute("data-occurrence")).toMatch(/^o-/);
    }
  });

  it("hides groups with zero uses", () => {
    render(
      <M15UpdateSummary
        uses={uses.filter((u) => u.verdict !== "INCOMPATIBLE")}
      />,
    );
    expect(screen.queryAllByTestId("m15-use-row")).toHaveLength(3);
    expect(screen.queryByText(/Cannot be selected/i)).toBeNull();
  });
});

describe("requires explicit review acceptance and disables incompatible uses", () => {
  it("selects only accepted review rows; unreviewed review rows are excluded", () => {
    const onApply = vi.fn();
    render(<M15UpdateSummary uses={uses} onApply={onApply} />);
    const apply = screen.getByTestId("apply-selected") as HTMLButtonElement;
    // review use NOT accepted → only the two automatic rows are
    // eligible; the button is enabled (2 > 0)
    expect(apply.disabled).toBe(false);
    fireEvent.click(apply);
    expect(onApply).toHaveBeenCalledTimes(1);
    expect(onApply.mock.calls[0][0]).toHaveLength(2);
    // accept the review use → the apply selection grows to 3
    fireEvent.click(screen.getByTestId("accept-o-cccc"));
    fireEvent.click(apply);
    expect(onApply.mock.calls[1][0]).toHaveLength(3);
    expect(
      onApply.mock.calls[1][0].some(
        (u: { occurrenceId: string }) => u.occurrenceId === "o-cccc",
      ),
    ).toBe(true);
  });

  it("renders the incompatible use as unselectable and never in apply output", () => {
    const onApply = vi.fn();
    render(<M15UpdateSummary uses={uses} onApply={onApply} />);
    expect(screen.getByTestId("incompatible-disabled").textContent).toContain(
      "Cannot be selected",
    );
    fireEvent.click(screen.getByTestId("accept-o-cccc"));
    fireEvent.click(screen.getByTestId("apply-selected"));
    const applied = onApply.mock.calls[0][0] as { occurrenceId: string }[];
    expect(
      applied.some((u) => u.occurrenceId === "o-dddd"),
    ).toBe(false);
  });

  it("disables apply when nothing is selectable", () => {
    render(
      <M15UpdateSummary
        uses={[{ compositionId: "c-x", occurrenceId: "o-y", verdict: "REQUIRES_REVIEW" }]}
        onApply={() => {}}
      />,
    );
    expect(
      (screen.getByTestId("apply-selected") as HTMLButtonElement).disabled,
    ).toBe(true);
  });
});

describe(
  "compatibility_does_not_claim_geometric_fit_or_visual_identity",
  () => {
  it("shows the product-honesty boundary and the history-unchanged scope", () => {
    render(<M15UpdateSummary uses={uses} />);
    expect(
      screen.getByTestId("compatibility-honesty").textContent,
    ).toContain(
      "Compatibility did not certify geometric fit or visual identity",
    );
    expect(screen.getByTestId("history-message").textContent).toContain(
      "current working Composition uses only",
    );
    expect(screen.getByTestId("history-message").textContent).toContain(
      "remain unchanged",
    );
  });
});
