/**
 * M12-UI:01 — same occurrence survives revision publication.
 */
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { Composition, OccurrenceRow } from "@/lib/types";

const listCompositions = vi.fn();
const createComposition = vi.fn();
const listOccurrences = vi.fn();
const mintOccurrence = vi.fn();
const patchOccurrence = vi.fn();
const previewIdentityOperation = vi.fn();
const applyIdentityOperation = vi.fn();
const publishComposition = vi.fn();

vi.mock("@/lib/api.client", () => ({
  listCompositionRevisionsPublic: vi.fn(async () => []),
  getCapturedProductionWorld: vi.fn(async () => ({
    captured: false })),
  listProductionInstanceTracks: vi.fn(async () => []),
  createProductionInstanceTrack: vi.fn(),
  createProductionInstanceSpatialTransition: vi.fn(),
  getJson: vi.fn(async (url: string) =>
    // readiness must stay null (the guarded panel) while
    // revisions/history resolve to empty lists
    url.includes("publication-readiness") ? null : []),
  getAuthoritySubject: vi.fn(async () => ({
    composition_id: "c", occurrence_id: "o",
    subject_kind: "composition_local", subject_id: null,
    creative_entity_id: null, created_at: null })),
  listCompositions: (...a: unknown[]) => listCompositions(...a),
  createComposition: (...a: unknown[]) => createComposition(...a),
  listOccurrences: (...a: unknown[]) => listOccurrences(...a),
  mintOccurrence: (...a: unknown[]) => mintOccurrence(...a),
  patchOccurrence: (...a: unknown[]) => patchOccurrence(...a),
  previewIdentityOperation: (...a: unknown[]) => previewIdentityOperation(...a),
  applyIdentityOperation: (...a: unknown[]) => applyIdentityOperation(...a),
  publishComposition: (...a: unknown[]) => publishComposition(...a),
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
  occurrence_id: "occ-7", display_name: "Chair 7", source_kind: "production_revision",
  production_revision_id: "pr-2", nested_composition_revision_id: null,
  visible: 1, x_mm: 0, y_mm: 0, z_mm: 0,
  yaw_udeg: 0, pitch_udeg: 0, roll_udeg: 0, updated_at: "2026-01-01T00:00:00Z",
};

beforeEach(() => {
  vi.clearAllMocks();
  listCompositions.mockResolvedValue([COMP]);
  listOccurrences.mockResolvedValue([OCC]);
  fetchMock.mockResolvedValue({
    json: async () => [
      { revision_id: "rev-1", revision_number: 1, snapshot_hash: "h",
        created_at: "2026-01-01T00:00:00Z" },
    ],
  });
});

afterEach(cleanup);

describe("WorldSetWorkspace", () => {
  it("same occurrence survives revision publication", async () => {
    publishComposition.mockResolvedValue({
      created: true,
      revision: {
        revision_id: "rev-2", composition_id: COMP.id, revision_number: 2,
        snapshot_json: "{}", snapshot_hash: "h2",
        created_at: "2026-01-01T00:00:00Z",
      },
    });
    render(<WorldSetWorkspace projectId="p1" />);
    const lobbyBtn = await screen.findByRole("button", { name: "Lobby" });
    await userEvent.click(lobbyBtn);
    await waitFor(() =>
      expect(screen.getByTestId("composition-detail")).toBeTruthy());
    await waitFor(() =>
      expect(screen.getByTestId("occurrence-list")).toBeTruthy());
    // occurrence identity row is displayed with its stable id
    expect(screen.getByTestId("occ-occ-7").textContent).toContain("occ-7");

    await userEvent.click(screen.getByTestId("publish-composition"));
    await waitFor(() =>
      expect(publishComposition).toHaveBeenCalledWith(COMP.id, 1));
    await waitFor(() => expect(screen.getByTestId("ws-notice")).toBeTruthy());
    // the same occurrence row remains after publication
    expect(screen.getByTestId("occ-occ-7").textContent).toContain("occ-7");
    expect(screen.getByTestId("occ-occ-7").textContent).toContain("Chair 7");
  });
});
