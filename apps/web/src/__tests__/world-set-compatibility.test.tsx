/** M12-UI:06 — same-lineage update warns identity preserved, not compatibility. */
import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { Composition, OccurrenceRow } from "@/lib/types";

const patchOccurrence = vi.fn();

vi.mock("@/lib/api.client", () => ({
  listCompositions: vi.fn(async () => [COMP]),
  listOccurrences: vi.fn(async () => [OCC]),
  patchOccurrence: (...a: unknown[]) => patchOccurrence(...a),
  createComposition: vi.fn(),
  mintOccurrence: vi.fn(),
  previewIdentityOperation: vi.fn(),
  applyIdentityOperation: vi.fn(),
  publishComposition: vi.fn(),
}));

const fetchMock = vi.fn();
globalThis.fetch = fetchMock as unknown as typeof fetch;

import WorldSetWorkspace from "@/components/WorldSetWorkspace";

const COMP: Composition = {
  id: "comp-1", project_id: "p1", name: "Lobby", description: null,
  metadata_version: 0, working_version: 1,
  created_at: "2026-01-01T00:00:00Z", updated_at: "2026-01-01T00:00:00Z",
};
const OCC: OccurrenceRow = {
  occurrence_id: "occ-7", display_name: "Chair 7",
  source_kind: "production_revision", production_revision_id: "pr-2",
  nested_composition_revision_id: null, visible: 1,
  x_mm: 0, y_mm: 0, z_mm: 0, yaw_udeg: 0, pitch_udeg: 0, roll_udeg: 0,
  updated_at: "2026-01-01T00:00:00Z",
};

beforeEach(() => {
  vi.clearAllMocks();
  fetchMock.mockResolvedValue({ json: async () => [] });
  patchOccurrence.mockResolvedValue({
    occurrence_id: "occ-7", working_version: 2 });
});

afterEach(cleanup);

describe("WorldSetWorkspace compatibility language", () => {
  it("same lineage update warns identity preserved not physical compatibility", async () => {
    render(<WorldSetWorkspace projectId="p1" />);
    const btn = await screen.findByRole("button", { name: "Lobby" });
    await userEvent.click(btn);
    await screen.findByTestId("occurrence-list");

    // the action itself carries the warning
    const updateBtn = screen.getByTestId("update-source-occ-7");
    expect(updateBtn.getAttribute("title")).toContain(
      "Identity is preserved");
    expect(updateBtn.getAttribute("title")).toContain(
      "not certified");

    window.prompt = vi.fn(() => "pr-2");
    await userEvent.click(screen.getByTestId("update-source-occ-7"));
    await vi.waitFor(() =>
      expect(screen.getByTestId("ws-notice").textContent)
        .toContain("Identity is preserved"));
    expect(screen.getByTestId("ws-notice").textContent).toContain(
      "not certified by this milestone");
  });
});
