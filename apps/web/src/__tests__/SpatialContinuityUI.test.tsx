/**
 * M10D §44-47 UI acceptance — spatial continuity panel and plan editor.
 *
 * Mechanically performs real-shaped server requests through the actual
 * component: the panel renders the server-resolved CURRENT projection
 * (world/staging/axis/hash/issues, current-not-captured labeling), and
 * the plan editor sends exact CAS PUT/DELETE bodies carrying the last
 * server-returned plan_hash. A conflict instructs reconciliation —
 * never auto-overwrite.
 */

import {
  cleanup, fireEvent, render, waitFor,
} from "@testing-library/react";
import { afterEach, expect, test, vi } from "vitest";
import SpatialContinuityPanel from "@/components/SpatialContinuityPanel";
import SpatialProvenanceBlock, {
  type CapturedSpatial,
} from "@/components/SpatialProvenanceBlock";
import { ApiError } from "@/lib/api.shared";

afterEach(cleanup);

const shotId = "s-1";
const trackId = "t-1";
const worldId = "w-1";
const planHash = "a".repeat(64);

function spatialBody(ready = true) {
  return {
    shot_id: shotId,
    ready,
    spatial_continuity_hash: ready ? "b".repeat(64) : null,
    issues: ready ? [] : [
      { code: "SPATIAL_WORLD_APPROVAL_REQUIRED", layer: "world_approval",
        message: "no approval", details: {} },
    ],
    spatial_continuity: {
      selected_world: {
        spatial_world_id: worldId, requirement: "required",
        location_entity_id: "loc",
      },
      location_entity_revision_id: "rev-9",
      approved_world_revision: {
        id: "wr-1", revision_number: 3, snapshot_hash: "c".repeat(64),
      },
      staging: [{
        spatial_track_id: trackId, entity_id: "e-1",
        entity_revision_id: "er-7", requirement: "optional",
        transform: {
          translation_mm: [500, 0, -1200], rotation_udeg: [0, 0, 0],
        },
        source_transition: {
          id: "tr-1", anchor_type: "sequence", anchor_id: "q-1",
          boundary: "start",
        },
      }],
      plan: {
        schema_version: 1, spatial_world_id: worldId,
        camera: {
          projection: "perspective", focal_length_um: 50000,
          sensor_width_um: 36000, sensor_height_um: 20250,
          keyframes: [{
            time_ms: 0,
            transform: {
              translation_mm: [-3000, 1650, 4200], rotation_udeg: [0, 0, 0],
            },
          }],
        },
        blocking: [{
          spatial_track_id: trackId, screen_direction: "left_to_right",
          keyframes: [{
            time_ms: 0,
            transform: {
              translation_mm: [500, 0, -1200], rotation_udeg: [0, 0, 0],
            },
          }],
        }],
        axis_constraint: {
          spatial_axis_id: "ax-1", camera_side: "positive",
        },
      },
      plan_hash: planHash,
      axis_status: {
        spatial_axis_id: "ax-1", camera_side: "positive",
        violating_keyframe_times_ms: [],
      },
    },
  };
}

test("panel renders the server-resolved CURRENT projection with " +
     "current-only labeling", async () => {
  const original = global.fetch;
  global.fetch = vi.fn(async () =>
    new Response(JSON.stringify(spatialBody())));
  try {
    const { findByText, getByText, getAllByText } = render(
      <SpatialContinuityPanel shotId={shotId} />);
    await findByText("Current spatial continuity");
    // current-not-captured disclaimer is explicit
    expect(getByText(/captured authority lives in/i)).toBeDefined();
    // server values, not client recomputation
    expect(getByText(/w-1/)).toBeDefined();
    const stagings = await waitFor(() =>
      getAllByText(/500 \/ 0 \/ -1200/));
    expect(stagings.length).toBeGreaterThanOrEqual(1);
    expect(getByText(/sequence\/start/)).toBeDefined();
    expect(getByText(/all camera keyframes on the declared side/i))
      .toBeDefined();
    expect(getByText(/not ready|ready/)).toBeDefined();
  } finally {
    global.fetch = original;
  }
});

test("plan editor sends exact CAS bodies and surfaces conflicts " +
     "without auto-overwrite", async () => {
  const calls: Array<{ url: string; init?: RequestInit }> = [];
  const original = global.fetch;
  let planPresent = true;
  global.fetch = vi.fn(async (input: RequestInfo | URL,
                              init?: RequestInit) => {
    const url = String(input);
    calls.push({ url, init });
    if (url.endsWith("/spatial-continuity")) {
      return new Response(JSON.stringify(
        spatialBody(planPresent)));
    }
    if (url.endsWith("/spatial-plan") && init?.method === "PUT") {
      return new Response(
        JSON.stringify({ error_code: "SPATIAL_SHOT_PLAN_CONFLICT",
                         message: "stale",
                         details: {} }),
        { status: 409 });
    }
    if (url.endsWith("/spatial-plan") && init?.method === "DELETE") {
      planPresent = false;
      return new Response(null, { status: 204 });
    }
    return new Response(JSON.stringify({}), { status: 404 });
  });
  try {
    const { findByText, findByDisplayValue, getByText } = render(
      <SpatialContinuityPanel shotId={shotId} />);
    await findByDisplayValue("50000");

    fireEvent.click(getByText("Save plan (CAS)"));
    await waitFor(() => {
      const put = calls.find(
        (c) => c.url === `/api/shots/${shotId}/spatial-plan` &&
          c.init?.method === "PUT");
      expect(put).toBeDefined();
      const body = JSON.parse(String(put!.init!.body));
      // exact CAS: the LAST server-returned hash rides the request
      expect(body.expected_plan_hash).toBe(planHash);
      expect(body.plan.schema_version).toBe(1);
      expect(body.plan.camera.keyframes[0].transform.translation_mm)
        .toEqual([-3000, 1650, 4200]);
    });
    // conflict instructs reconciliation, never overwrites
    await findByText(/refresh and\s+reconcile/i);

    // DELETE carries the exact hash too
    fireEvent.click(getByText("Delete plan"));
    await waitFor(() => {
      const del = calls.filter(
        (c) => c.url === `/api/shots/${shotId}/spatial-plan` &&
          c.init?.method === "DELETE");
      expect(del).toHaveLength(1);
      expect(JSON.parse(String(del[0].init!.body))).toEqual(
        { expected_plan_hash: planHash });
    });
  } finally {
    global.fetch = original;
  }
});

test("captured provenance block renders immutable history labeled " +
     "Captured, and honest null/error states", async () => {
  const spatial: CapturedSpatial = {
    spatial_continuity_hash: "d".repeat(64),
    world: {
      spatial_world_id: worldId, requirement: "required",
      spatial_world_revision_id: "wr-9",
      spatial_world_revision_hash: "e".repeat(64),
      location_entity_id: "loc", location_entity_revision_id: "rev-3",
    },
    staging: [{
      spatial_track_id: trackId, entity_id: "e-1",
      entity_revision_id: "er-7", requirement: "optional",
      transform: {
        translation_mm: [500, 0, -1200], rotation_udeg: [0, 0, 0],
      },
      source_transition: {
        spatial_transition_id: "tr-2", anchor_type: "shot",
        anchor_id: "s-9", boundary: "end",
      },
    }],
    shot_plan: {
      camera: {
        focal_length_um: 50000,
        keyframes: [{ time_ms: 0, transform: {
          translation_mm: [0, 0, 0] } }],
      },
      blocking: [{ spatial_track_id: trackId,
                   screen_direction: "unspecified" }],
    },
  };
  const { getByText } = render(
    <SpatialProvenanceBlock spatial={spatial} />);
  expect(getByText("Captured spatial continuity")).toBeDefined();
  expect(getByText(/used by this captured revision/i)).toBeDefined();
  expect(getByText(/shot\/end/)).toBeDefined();

  const { getByText: g2 } = render(<SpatialProvenanceBlock
    spatial={null} />);
  expect(g2(/No captured spatial authority/i)).toBeDefined();

  const { getByText: g3 } = render(<SpatialProvenanceBlock
    spatial={new ApiError(
      "INTERNAL_INVARIANT_VIOLATION", "corrupt", 500, {})} />);
  expect(g3(/ERROR/)).toBeDefined();
  expect(g3(/corrupt/)).toBeDefined();
});
