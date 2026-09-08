/**
 * F8 final: nested Replace-as-new must carry
 *   source.kind = composition_revision
 *   revision_id = the exact nested Composition Revision UUID
 * through BOTH Preview and Apply — never a Production-Revision-labeled
 * Composition UUID. Also proves nested insertion mints with the
 * composition_revision kind.
 */
import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { Composition, OccurrenceRow } from "@/lib/types";

const mintOccurrence = vi.fn();
const patchOccurrence = vi.fn();
const previewIdentityOperation = vi.fn();
const applyIdentityOperation = vi.fn();

vi.mock("@/lib/api.client", () => ({
  listCompositionRevisionsPublic: vi.fn(async () => []),
  getCapturedProductionWorld: vi.fn(async () => ({
    captured: false })),
  listProductionInstanceTracks: vi.fn(async () => []),
  createProductionInstanceTrack: vi.fn(),
  createProductionInstanceSpatialTransition: vi.fn(),
  listCompositions: vi.fn(async () => [COMP]),
  listOccurrences: vi.fn(async () => [NESTED_OCC]),
  mintOccurrence: (...a: unknown[]) => mintOccurrence(...a),
  patchOccurrence: (...a: unknown[]) => patchOccurrence(...a),
  previewIdentityOperation: (...a: unknown[]) => previewIdentityOperation(...a),
  applyIdentityOperation: (...a: unknown[]) => applyIdentityOperation(...a),
  createComposition: vi.fn(),
  publishComposition: vi.fn(),
  getJson: vi.fn(async (url: string) => {
    if (url.includes("publication-readiness")) {
      return { ready: true, issues: [], working_version: 1,
               occurrence_count: 1 };
    }
    return [];
  }),
}));

import WorldSetWorkspace from "@/components/WorldSetWorkspace";

const COMP: Composition = {
  id: "comp-lobby", project_id: "p1", name: "Lobby", description: null,
  metadata_version: 0, working_version: 1,
  created_at: "2026-01-01T00:00:00Z", updated_at: "2026-01-01T00:00:00Z",
};
// a NESTED occurrence: sources a published Composition Revision
const NESTED_OCC: OccurrenceRow = {
  occurrence_id: "occ-r1", display_name: "Reception Module",
  source_kind: "composition_revision",
  production_revision_id: null,
  nested_composition_revision_id: "44444444-4444-4444-4444-444444444444",
  visible: 1, x_mm: 0, y_mm: 0, z_mm: 0,
  yaw_udeg: 0, pitch_udeg: 0, roll_udeg: 0,
  updated_at: "2026-01-01T00:00:00Z",
};

beforeEach(() => {
  vi.clearAllMocks();
  previewIdentityOperation.mockResolvedValue({
    allowed: true, working_version: 1,
    normalized_request: {}, request_fingerprint: "f".repeat(64),
    impact_fingerprint: "e".repeat(64),
    source_occurrence_summaries: [
      { occurrence_id: "occ-r1", active: true, in_working_state: true }],
    historical_reference_counts: { "occ-r1": 2 },
    live_blocking_references: [],
  });
  applyIdentityOperation.mockResolvedValue({
    operation_id: "op-9", kind: "replace_as_new", working_version: 2,
    target_occurrence_ids: ["occ-r2"],
  });
  mintOccurrence.mockResolvedValue({
    occurrence_id: "occ-new-nested", working_version: 2 });
});

afterEach(cleanup);

describe("WorldSetWorkspace nested identity", () => {
  it("nested insertion and replace carry composition_revision source kind", async () => {
    render(<WorldSetWorkspace projectId="p1" />);
    const lobby = await screen.findByRole("button", { name: "Lobby" });
    await userEvent.click(lobby);
    await screen.findByTestId("occurrence-list");

    // --- nested INSERTION mints with the composition_revision kind ---
    const kindSelect = screen.getByTestId("source-kind-select") as
      HTMLSelectElement;
    await userEvent.selectOptions(kindSelect, "composition_revision");
    const input = screen.getByLabelText("Composition Revision ID");
    await userEvent.type(input, "55555555-5555-5555-5555-555555555555");
    await userEvent.click(screen.getByRole("button", { name: "Add occurrence" }));
    await vi.waitFor(() => expect(mintOccurrence).toHaveBeenCalled());
    const mintBody = mintOccurrence.mock.calls[0][1];
    expect(mintBody.source.kind).toBe("composition_revision");
    expect(mintBody.source.revision_id).toBe("55555555-5555-5555-5555-555555555555");

    // --- nested REPLACE keeps the composition_revision kind ---
    await userEvent.click(screen.getByTestId("replace-occ-r1"));
    await screen.findByTestId("replace-dialog");
    await userEvent.click(screen.getByTestId("replace-confirm"));
    await screen.findByTestId("impact-review");
    await userEvent.click(screen.getByTestId("impact-confirm"));

    await vi.waitFor(() =>
      expect(previewIdentityOperation).toHaveBeenCalled());
    const previewBody = previewIdentityOperation.mock.calls[0][1];
    expect(previewBody.scope).toBe("composition_working_state");
    expect(previewBody.request.target_working_specs).toHaveLength(1);
    const spec = previewBody.request.target_working_specs[0];
    expect(spec.source.kind).toBe("composition_revision");  // NOT production
    expect(spec.source.revision_id).toBe("44444444-4444-4444-4444-444444444444");  // exact nested UUID

    await vi.waitFor(() =>
      expect(applyIdentityOperation).toHaveBeenCalled());
    const applyBody = applyIdentityOperation.mock.calls[0][1];
    expect(applyBody.request.target_working_specs[0].source.kind)
      .toBe("composition_revision");
    expect(applyBody.request.target_working_specs[0].source.revision_id)
      .toBe("44444444-4444-4444-4444-444444444444");
  });
});
