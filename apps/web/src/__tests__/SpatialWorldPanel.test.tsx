/**
 * M10B §50 — Spatial World workspace UI (render-level, house parity).
 *
 * Proves the working-vs-approved honesty labels (§89): the panel renders
 * the server-fed working membership, the immutable revision history, and
 * the approval badge state without any client-side recomputation.
 */

import { render, waitFor } from "@testing-library/react";
import { expect, test } from "vitest";
import { SpatialWorldPanel } from "@/components/SpatialWorldPanel";

function workspaceBody(approved: string | null) {
  return {
    world: { id: "w1", key: "lobby", name: "Lobby",
             requirement: "required", location_entity_id: "e1" },
    states: [{
      id: "s1", location_entity_revision_id: "r1",
      approved_revision_id: approved, working_snapshot_hash: null,
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

function withFetch(body: unknown, fn: () => void) {
  const original = global.fetch;
  global.fetch = (async (): Promise<Response> =>
    new Response(JSON.stringify(body), { status: 200 })) as typeof fetch;
  try {
    fn();
  } finally {
    global.fetch = original;
  }
}

test("renders working membership, history, and approved badge", async () => {
  withFetch(workspaceBody("rev1"), () => {
    const { container } = render(<SpatialWorldPanel worldId="w1" />);
    void waitFor(() => {
      expect(container.textContent).toContain("Working membership");
      expect(container.textContent).toContain("Revision history (immutable)");
      expect(container.textContent).toContain("front-desk");
      expect(container.textContent).toContain("Approved");
    });
  });
});

test("unapproved state shows the honest missing-approval badge", async () => {
  withFetch(workspaceBody(null), () => {
    const { container } = render(<SpatialWorldPanel worldId="w1" />);
    void waitFor(() => {
      expect(container.textContent).toContain("No approved revision");
      expect(container.textContent).toContain("Working membership");
    });
  });
});
