/** M12-UI:04 — identity history renders old→new without retargeting. */
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { Composition, OccurrenceRow } from "@/lib/types";

const getJson = vi.fn();

vi.mock("@/lib/api.client", () => ({
  listCompositionRevisionsPublic: vi.fn(async () => []),
  getCapturedProductionWorld: vi.fn(async () => ({
    captured: false })),
  listProductionInstanceTracks: vi.fn(async () => []),
  createProductionInstanceTrack: vi.fn(),
  createProductionInstanceSpatialTransition: vi.fn(),
  listCompositions: vi.fn(async () => [COMP]),
  listOccurrences: vi.fn(async () => [OCC]),
  createComposition: vi.fn(),
  mintOccurrence: vi.fn(),
  patchOccurrence: vi.fn(),
  previewIdentityOperation: vi.fn(),
  applyIdentityOperation: vi.fn(),
  publishComposition: vi.fn(),
  getJson: (...a: unknown[]) => getJson(...a),
}));

import WorldSetWorkspace from "@/components/WorldSetWorkspace";

const COMP: Composition = {
  id: "comp-1", project_id: "p1", name: "Lobby", description: null,
  metadata_version: 0, working_version: 9,
  created_at: "2026-01-01T00:00:00Z", updated_at: "2026-01-01T00:00:00Z",
};
const OCC: OccurrenceRow = {
  occurrence_id: "occ-old", display_name: "Chair 7",
  source_kind: "production_revision", production_revision_id: "pr-1",
  nested_composition_revision_id: null, visible: 1,
  x_mm: 0, y_mm: 0, z_mm: 0, yaw_udeg: 0, pitch_udeg: 0, roll_udeg: 0,
  updated_at: "2026-01-01T00:00:00Z",
};

beforeEach(() => {
  vi.clearAllMocks();
});

afterEach(cleanup);

describe("WorldSetWorkspace lineage", () => {
  it("identity history renders old to new without retargeting", async () => {
    // the real history fetch renders mint then replace_as_new with the
    // OLD id in sources and a NEW distinct id in targets — never a rename
    getJson.mockImplementation(async (url: string) => {
      if (url.includes("identity-history")) {
        return [
          { operation_id: "op-1", kind: "mint",
            working_version_before: 0, working_version_after: 1,
            sources: [], targets: ["occ-old"] },
          { operation_id: "op-2", kind: "replace_as_new",
            working_version_before: 8, working_version_after: 9,
            sources: [{ occurrence_id: "occ-old", terminates_identity: 1 }],
            targets: ["occ-new"] },
        ];
      }
      if (url.includes("revisions")) {
        return [
          { revision_id: "rev-1", revision_number: 1, snapshot_hash: "h",
            created_at: "2026-01-01T00:00:00Z" },
        ];
      }
      if (url.includes("publication-readiness")) {
        return { ready: true, issues: [], working_version: 9,
                 occurrence_count: 1 };
      }
      return [];
    });

    render(<WorldSetWorkspace projectId="p1" />);
    const lobby = await screen.findByRole("button", { name: "Lobby" });
    await userEvent.click(lobby);

    const historyPanel = await screen.findByTestId("identity-history");
    expect(historyPanel.textContent).toContain("mint");
    expect(historyPanel.textContent).toContain("replace_as_new");

    // the rendered replace operation keeps occ-old in SOURCES and mints
    // occ-new as TARGET — two distinct stable ids, not a retargeted rename
    const replaceRow = screen.getByTestId("history-op-2");
    expect(replaceRow.textContent).toContain("occ-old");
    expect(replaceRow.textContent).toContain("occ-new");
    expect(replaceRow.textContent).not.toMatch(
      /occ-old → occ-old/);
    // order is old→new by version
    const rows = [screen.getByTestId("history-op-1"),
                  screen.getByTestId("history-op-2")];
    expect(rows[0].textContent).toContain("v0→1");
    expect(rows[1].textContent).toContain("v8→9");
  });
});
