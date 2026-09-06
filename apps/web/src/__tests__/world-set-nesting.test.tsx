/** M12-UI:05 — nested internal occurrences require context switch. */
import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { Composition, OccurrenceRow } from "@/lib/types";

vi.mock("@/lib/api.client", () => ({
  listCompositions: vi.fn(async () => [PARENT, NESTED]),
  listOccurrences: vi.fn(),
  createComposition: vi.fn(),
  mintOccurrence: vi.fn(),
  patchOccurrence: vi.fn(),
  previewIdentityOperation: vi.fn(),
  applyIdentityOperation: vi.fn(),
  publishComposition: vi.fn(),
}));

const fetchMock = vi.fn();
globalThis.fetch = fetchMock as unknown as typeof fetch;

import WorldSetWorkspace from "@/components/WorldSetWorkspace";

const PARENT: Composition = {
  id: "comp-parent", project_id: "p1", name: "Lobby", description: null,
  metadata_version: 0, working_version: 2,
  created_at: "2026-01-01T00:00:00Z", updated_at: "2026-01-01T00:00:00Z",
};
const NESTED: Composition = {
  id: "comp-module", project_id: "p1", name: "ReceptionModule",
  description: null, metadata_version: 0, working_version: 1,
  created_at: "2026-01-01T00:00:00Z", updated_at: "2026-01-01T00:00:00Z",
};

const PARENT_OCC: OccurrenceRow = {
  occurrence_id: "occ-r1", display_name: "Reception",
  source_kind: "composition_revision",
  production_revision_id: null,
  nested_composition_revision_id: "rev-module-4", visible: 1,
  x_mm: 0, y_mm: 0, z_mm: 0, yaw_udeg: 0, pitch_udeg: 0, roll_udeg: 0,
  updated_at: "2026-01-01T00:00:00Z",
};
const INTERNAL_OCC: OccurrenceRow = {
  occurrence_id: "occ-chair-internal", display_name: "Chair inside module",
  source_kind: "production_revision",
  production_revision_id: "pr-1",
  nested_composition_revision_id: null, visible: 1,
  x_mm: 0, y_mm: 0, z_mm: 0, yaw_udeg: 0, pitch_udeg: 0, roll_udeg: 0,
  updated_at: "2026-01-01T00:00:00Z",
};

beforeEach(() => {
  vi.clearAllMocks();
  fetchMock.mockResolvedValue({ json: async () => [] });
});

afterEach(cleanup);

describe("WorldSetWorkspace nesting", () => {
  it("nested internal occurrences require context switch", async () => {
    const { listOccurrences } = await import("@/lib/api.client");
    vi.mocked(listOccurrences).mockImplementation(
      async (cid: string) =>
        cid === PARENT.id ? [PARENT_OCC] : [INTERNAL_OCC]);

    render(<WorldSetWorkspace projectId="p1" />);
    const lobby = await screen.findByRole("button", { name: "Lobby" });
    await userEvent.click(lobby);
    await screen.findByTestId("occurrence-list");

    // Parent view shows ONLY the nested assembly occurrence — not the
    // nested module's internal chair row.
    const list = screen.getByTestId("occurrence-list");
    expect(list.textContent).toContain("occ-r1");
    expect(list.textContent).not.toContain("occ-chair-internal");

    // editing internals requires switching context to the nested set
    const module = screen.getByRole("button", { name: "ReceptionModule" });
    await userEvent.click(module);
    await vi.waitFor(() => {
      expect(screen.getByTestId("occurrence-list").textContent)
        .toContain("occ-chair-internal");
    });
  });
});
