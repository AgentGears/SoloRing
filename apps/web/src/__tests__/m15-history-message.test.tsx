import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import M15HistoryMessage from "@/components/M15HistoryMessage";

afterEach(cleanup);

describe("states_current_only_and_history_unchanged", () => {
  it("states current-working-only scope with every immutable class named", () => {
    render(<M15HistoryMessage updatedCount={3} />);
    const message = screen.getByTestId("m15-history-message").textContent;
    expect(message).toContain("3 current working uses updated");
    expect(message).toContain("Occurrence identity preserved");
    expect(message).toContain(
      "Persistent state/spatial subjects unchanged",
    );
    expect(message).toContain("Published and captured history unchanged");
  });

  it("states the honesty boundary and the publish next action", () => {
    render(<M15HistoryMessage updatedCount={1} />);
    const message = screen.getByTestId("m15-history-message").textContent;
    expect(message).toContain(
      "Compatibility did not certify geometric fit or visual identity",
    );
    expect(message).toContain(
      "Publish a new Composition Revision to make this reusable-set change publishable",
    );
  });

  it("reports stale same-composition remainder when reassessment is required", () => {
    render(
      <M15HistoryMessage
        updatedCount={1}
        staleRemaining={[{ compositionId: "c-9", occurrenceId: "o-9" }]}
      />,
    );
    const message = screen.getByTestId("m15-history-message").textContent;
    expect(message).toContain("1 remaining use is now stale");
    expect(message).toContain("reassessment required before continuing");
  });
});
