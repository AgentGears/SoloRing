/** M12-UI:02 — consequential edit displays reusable set scope. */
import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { Composition, OccurrenceRow } from "@/lib/types";

const listCompositions = vi.fn();
const listOccurrences = vi.fn();
const patchOccurrence = vi.fn();

vi.mock("@/lib/api.client", () => ({
  listCompositions: (...a: unknown[]) => listCompositions(...a),
  listOccurrences: (...a: unknown[]) => listOccurrences(...a),
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
  metadata_version: 0, working_version: 3,
  created_at: "2026-01-01T00:00:00Z", updated_at: "2026-01-01T00:00:00Z",
};
const OCC: OccurrenceRow = {
  occurrence_id: "occ-1", display_name: "Chair 7",
  source_kind: "production_revision", production_revision_id: "pr-1",
  nested_composition_revision_id: null, visible: 1,
  x_mm: 0, y_mm: 0, z_mm: 0, yaw_udeg: 0, pitch_udeg: 0, roll_udeg: 0,
  updated_at: "2026-01-01T00:00:00Z",
};

beforeEach(() => {
  vi.clearAllMocks();
  listCompositions.mockResolvedValue([COMP]);
  listOccurrences.mockResolvedValue([OCC]);
  fetchMock.mockResolvedValue({ json: async () => [] });
  patchOccurrence.mockResolvedValue({
    occurrence_id: OCC.occurrence_id, working_version: 4 });
});

afterEach(cleanup);

describe("WorldSetWorkspace scope", () => {
  it("consequential edit displays reusable set scope", async () => {
    render(<WorldSetWorkspace projectId="p1" />);
    const btn = await screen.findByRole("button", { name: "Lobby" });
    await userEvent.click(btn);
    await screen.findByTestId("occurrence-list");

    // scope banner is visible before any consequential mutation
    const banner = screen.getByTestId("scope-banner");
    expect(banner.textContent).toContain("Reusable set");
    expect(banner.textContent).toContain("occurrence");

    // every occurrence mutation request carries the scope explicitly
    await userEvent.click(screen.getByRole("button", { name: "Update this occurrence" }));
    await vi.waitFor(() => expect(patchOccurrence).toHaveBeenCalled());
    const call = patchOccurrence.mock.calls[0];
    expect(call[2].scope).toBe("composition_working_state");
  });
});
