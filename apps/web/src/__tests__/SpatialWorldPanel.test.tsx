/**
 * M10B section 50 - Spatial World workspace UI (render + action level).
 *
 * Assertions are GENUINELY awaited (house correction: await waitFor),
 * covering the editor labels, the server-computed working hash, the
 * authoring forms, and the unapprove action.
 */

import { fireEvent, render, waitFor } from "@testing-library/react";
import { expect, test, vi } from "vitest";
import { SpatialWorldPanel } from "@/components/SpatialWorldPanel";

function workspaceBody(approved: string | null) {
  return {
    world: { id: "w1", key: "lobby", name: "Lobby",
             requirement: "required", location_entity_id: "e1" },
    states: [{
      id: "s1", location_entity_revision_id: "r1",
      approved_revision_id: approved,
      working_snapshot_hash: "f".repeat(64),
      frames: [{
        spatial_frame_id: "f1", frame_key: "front-desk",
        bound_entity_id: null,
        x_mm: 0, y_mm: 0, z_mm: 4200,
        yaw_udeg: 0, pitch_udeg: 0, roll_udeg: 0,
        half_x_mm: 2200, half_y_mm: 600, half_z_mm: 550 }],
      axes: [],
      revisions: [
        { id: "rev2", revision_number: 2, snapshot_hash: "b".repeat(64),
          created_at: "t2" },
        { id: "rev1", revision_number: 1, snapshot_hash: "a".repeat(64),
          created_at: "t1" }],
    }],
  };
}

function mockFetch(body: unknown) {
  return vi.fn(async () =>
    new Response(JSON.stringify(body), { status: 200 }));
}

test("renders working hash, history, labels, and authoring forms",
     async () => {
  const fetchMock = mockFetch(workspaceBody("rev1"));
  const original = global.fetch;
  global.fetch = fetchMock as unknown as typeof fetch;
  try {
    const { container } = render(<SpatialWorldPanel worldId="w1" />);
    await waitFor(() => {
      expect(container.textContent).toContain("Working membership");
      expect(container.textContent).toContain(
        "Revision history (immutable)");
      expect(container.textContent).toContain("front-desk");
      expect(container.textContent).toContain("ffffffffffffffff");
      expect(container.textContent).toContain("Approved");
      expect(container.textContent).toContain("Author frame");
      expect(container.textContent).toContain("Author axis");
    });
  } finally {
    global.fetch = original;
  }
});

test("unapprove action fires the real DELETE", async () => {
  const fetchMock = mockFetch(workspaceBody("rev1"));
  const original = global.fetch;
  global.fetch = fetchMock as unknown as typeof fetch;
  try {
    const { container } = render(<SpatialWorldPanel worldId="w1" />);
    await waitFor(() => {
      expect(container.textContent).toContain("Working membership");
    });
    const unapprove = Array.from(
      container.querySelectorAll("button"))
      .find((b) => b.textContent === "Unapprove");
    expect(unapprove).toBeTruthy();
    fireEvent.click(unapprove!);
    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        "/api/spatial-world-states/s1/approval",
        expect.objectContaining({ method: "DELETE" }));
    });
  } finally {
    global.fetch = original;
  }
});

test("unapproved world shows the missing-approval badge", async () => {
  const fetchMock = mockFetch(workspaceBody(null));
  const original = global.fetch;
  global.fetch = fetchMock as unknown as typeof fetch;
  try {
    const { container } = render(<SpatialWorldPanel worldId="w1" />);
    await waitFor(() => {
      expect(container.textContent).toContain("No approved revision");
      expect(container.textContent).toContain("Working membership");
    });
  } finally {
    global.fetch = original;
  }
});
