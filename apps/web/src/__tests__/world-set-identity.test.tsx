/** M12-UI:03 — update source and replace as new are distinct actions. */
import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { Composition, OccurrenceRow } from "@/lib/types";

const patchOccurrence = vi.fn();
const previewIdentityOperation = vi.fn();
const applyIdentityOperation = vi.fn();

vi.mock("@/lib/api.client", () => ({
  listCompositions: vi.fn(async () => [COMP]),
  listOccurrences: vi.fn(async () => [OCC]),
  patchOccurrence: (...a: unknown[]) => patchOccurrence(...a),
  previewIdentityOperation: (...a: unknown[]) => previewIdentityOperation(...a),
  applyIdentityOperation: (...a: unknown[]) => applyIdentityOperation(...a),
  createComposition: vi.fn(),
  mintOccurrence: vi.fn(),
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
});

afterEach(cleanup);

describe("WorldSetWorkspace identity actions", () => {
  it("update source and replace as new are distinct actions", async () => {
    patchOccurrence.mockResolvedValue({
      occurrence_id: "occ-7", working_version: 2 });
    previewIdentityOperation.mockResolvedValue({
      allowed: true, working_version: 1,
      normalized_request: {}, request_fingerprint: "f".repeat(64),
      impact_fingerprint: "e".repeat(64),
      source_occurrence_summaries: [],
      historical_reference_counts: {}, live_blocking_references: [],
    });
    applyIdentityOperation.mockResolvedValue({
      operation_id: "op-1", kind: "replace_as_new", working_version: 2,
      target_occurrence_ids: ["occ-8"],
    });

    render(<WorldSetWorkspace projectId="p1" />);
    const btn = await screen.findByRole("button", { name: "Lobby" });
    await userEvent.click(btn);
    await screen.findByTestId("occurrence-list");

    // same-identity source update goes through PATCH with the same id
    await userEvent.click(
      screen.getByRole("button", { name: /Update source/ }));
    await vi.waitFor(() => expect(patchOccurrence).toHaveBeenCalled());
    expect(patchOccurrence.mock.calls[0][1]).toBe("occ-7");

    // replace-as-new goes through identity preview/apply — a distinct path
    await userEvent.click(screen.getByTestId("replace-occ-7"));
    await vi.waitFor(() =>
      expect(previewIdentityOperation).toHaveBeenCalledWith(
        COMP.id,
        expect.objectContaining({ kind: "replace_as_new" })));
    await vi.waitFor(() => expect(applyIdentityOperation).toHaveBeenCalled());
    const applyBody = applyIdentityOperation.mock.calls[0][1];
    expect(applyBody.request.kind).toBe("replace_as_new");
    // distinct UI labels
    expect(
      screen.getByRole("button", { name: "Update this occurrence" }),
    ).toBeTruthy();
    expect(
      screen.getByRole("button", { name: "Replace as new occurrence" }),
    ).toBeTruthy();
  });
});
