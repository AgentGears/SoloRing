/**
 * M7B — null-safe working-state panels.
 *
 * continuity_state_ready = false must render "unresolved" states: never a
 * fabricated hash, never a misleading matches/differs verdict.
 */
import { cleanup, render } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import ApprovedTakePanel from "@/components/ApprovedTakePanel";
import WorkingStatePanel from "@/components/WorkingStatePanel";

describe("WorkingStatePanel null-safety (M7B)", () => {
  afterEach(cleanup);

  it("renders an unresolved state, not a fabricated hash, when null", () => {
    const { container } = render(
      <WorkingStatePanel workingSnapshotHash={null} updatedAt="2026-01-01" />,
    );
    expect(container.textContent).toContain(
      "Continuity state unresolved",
    );
    expect(container.querySelector(".hash")).toBeNull();
  });

  it("renders the hash normally when present", () => {
    const { container } = render(
      <WorkingStatePanel
        workingSnapshotHash={"a".repeat(64)}
        updatedAt="2026-01-01"
      />,
    );
    expect(container.querySelector(".hash")?.textContent).toBe("a".repeat(64));
  });
});

describe("ApprovedTakePanel null-safety (M7B)", () => {
  afterEach(cleanup);

  it("renders neither matches nor differs when comparison is null", () => {
    const { container } = render(
      <ApprovedTakePanel approvedTakeId="take-1" differs={null} />,
    );
    const text = container.textContent ?? "";
    expect(text).toContain("unresolved");
    expect(text).not.toContain("matches approved canon");
    expect(text).not.toContain("differs from approved canon");
  });

  it("keeps the honest no-canon state", () => {
    const { container } = render(
      <ApprovedTakePanel approvedTakeId={null} differs={null} />,
    );
    expect(container.textContent).toContain("No approved Take yet.");
  });

  it("renders verdicts normally when boolean", () => {
    const { container } = render(
      <ApprovedTakePanel approvedTakeId="take-1" differs={true} />,
    );
    expect(container.textContent).toContain(
      "Working state differs from approved canon",
    );
  });
});
