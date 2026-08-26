/**
 * M10C §10 — temporal staging UI acceptance (matrix 59-66 UI items).
 *
 * Mechanically performs real-shaped server requests through the actual
 * components: track creation, requirement PATCH, transition set/clear
 * authoring, and the staging inspector's server-resolved preview with
 * exact EntityRevision + provenance and distinct honest absence states.
 * The preview is labeled CURRENT staging, never captured history.
 */

import {
  cleanup, fireEvent, render, waitFor,
} from "@testing-library/react";
import { afterEach, expect, test, vi } from "vitest";

afterEach(cleanup);
import { SpatialWorldPanel } from "@/components/SpatialWorldPanel";
import { StagingInspector } from "@/components/StagingInspector";

const shot20 = "11111111-1111-1111-1111-111111111111";
const shot21 = "22222222-2222-2222-2222-222222222222";
const eva = "eeeeeeee-eeee-eeee-eeee-eeeeeeeeeeee";
const car = "cccccccc-cccc-cccc-cccc-cccccccccccc";
const track1 = "tttttttt-tttt-tttt-tttt-tttttttttttt";
const seq = "ssssssss-ssss-ssss-ssss-ssssssssssss";

function workspaceBody() {
  return {
    world: { id: "w1", key: "lobby", name: "Lobby",
             requirement: "optional", location_entity_id: "loc" },
    stable_frames: [],
    stable_axes: [],
    tracks: [
      { id: track1, entity_id: eva, requirement: "optional",
        transitions: [] as Array<Record<string, unknown>> },
    ],
    narrative: {
      entities: [
        { id: eva, kind: "character", name: "Eva" },
        { id: car, kind: "prop", name: "Car" },
      ],
      sequences: [{ id: seq, title: "Seq", position: 0 }],
      scenes: [],
      shots: [
        { id: shot20, title: "Shot 20", subject: "s20", scene_id: "c1" },
        { id: shot21, title: "Shot 21", subject: "s21", scene_id: "c1" },
      ],
    },
    states: [],
  };
}

function stagingBody() {
  return {
    shot_id: shot21,
    spatial_world_id: "w1",
    assigned: true,
    relevant_transition_data: true,
    narrative_context_required: false,
    states: [{
      spatial_track_id: track1,
      entity_id: eva,
      entity_name: "Eva",
      entity_revision_id: "rev-eva-12",
      requirement: "optional",
      transform: { translation_mm: [-1200, 0, -2400],
                   rotation_udeg: [0, 90000000, 0] },
      source_transition_id: "trn-1234",
      source_anchor_type: "shot",
      source_anchor_id: shot20,
      source_boundary: "end",
    }],
    absent: [
      { spatial_track_id: "tk-car", entity_id: car, entity_name: "Car",
        entity_revision_id: "rev-car-3", requirement: "required",
        reason: "no_eligible_transition" },
      { spatial_track_id: "tk-set", entity_id: "a", entity_name: "Prop",
        entity_revision_id: "rev-9", requirement: "optional",
        reason: "clear" },
    ],
  };
}

test("track creation and requirement PATCH issue real-shaped requests",
     async () => {
  const workspace: ReturnType<typeof workspaceBody> = workspaceBody();
  const calls: Array<{ url: string; init?: RequestInit }> = [];
  const original = global.fetch;
  global.fetch = vi.fn(async (input: RequestInfo | URL,
                              init?: RequestInit) => {
    const url = String(input);
    calls.push({ url, init });
    if (url.endsWith("/workspace")) {
      return new Response(JSON.stringify(workspace));
    }
    if (url.endsWith(`/tracks`) && init?.method === "POST" &&
        url.includes("/spatial-worlds/")) {
      workspace.tracks.push(
        { id: "tk-car", entity_id: car, requirement: "required",
          transitions: [] });
      return new Response(JSON.stringify({ id: "tk-car" }),
                          { status: 201 });
    }
    if (url.includes("/spatial-tracks/") && init?.method === "PATCH") {
      return new Response(null, { status: 204 });
    }
    return new Response(JSON.stringify({}), { status: 404 });
  });
  try {
    const { getByLabelText, getByText, findByText } = render(
      <SpatialWorldPanel worldId="w1" />);
    await findByText("Temporal staging tracks (M10C)");

    // matrix 59: real-shaped track creation request
    fireEvent.change(getByLabelText("track entity"),
                     { target: { value: car } });
    fireEvent.change(getByLabelText("track requirement"),
                     { target: { value: "required" } });
    fireEvent.click(getByText("Create track"));
    await waitFor(() => {
      const create = calls.find(
        (c) => c.url === "/api/spatial-worlds/w1/tracks" &&
          c.init?.method === "POST");
      expect(create).toBeDefined();
      expect(JSON.parse(String(create!.init!.body))).toEqual(
        { entity_id: car, requirement: "required" });
    });
    await findByText("Car (prop)");

    // matrix 60: real-shaped requirement PATCH
    fireEvent.click(getByText("Make required"));
    await waitFor(() => {
      const patch = calls.find(
        (c) => c.url === `/api/spatial-tracks/${track1}` &&
          c.init?.method === "PATCH");
      expect(patch).toBeDefined();
      expect(JSON.parse(String(patch!.init!.body))).toEqual(
        { requirement: "required" });
    });
  } finally {
    global.fetch = original;
  }
});

test("transition set and clear authoring issue real-shaped requests",
     async () => {
  const workspace = workspaceBody();
  const calls: Array<{ url: string; init?: RequestInit }> = [];
  const original = global.fetch;
  global.fetch = vi.fn(async (input: RequestInfo | URL,
                              init?: RequestInit) => {
    const url = String(input);
    calls.push({ url, init });
    if (url.endsWith("/workspace")) {
      return new Response(JSON.stringify(workspace));
    }
    if (url.endsWith("/transitions") && init?.method === "POST") {
      const body = JSON.parse(String(init!.body));
      workspace.tracks[0].transitions.push(
        { id: "tr-" + body.operation, anchor_type: body.anchor_type,
          anchor_id: body.anchor_id, boundary: body.boundary,
          operation: body.operation,
          x_mm: body.translation_mm?.[0] ?? null,
          y_mm: body.translation_mm?.[1] ?? null,
          z_mm: body.translation_mm?.[2] ?? null,
          yaw_udeg: body.rotation_udeg?.[0] ?? null,
          pitch_udeg: body.rotation_udeg?.[1] ?? null,
          roll_udeg: body.rotation_udeg?.[2] ?? null });
      return new Response(JSON.stringify({ id: "tr-x" }),
                          { status: 201 });
    }
    return new Response(JSON.stringify({}), { status: 404 });
  });
  try {
    const { getByLabelText, getByText, findByText } = render(
      <SpatialWorldPanel worldId="w1" />);
    await findByText("Author transition");

    // matrix 61 (set): six transform values, all six coordinate classes
    // available; shot/end selected
    fireEvent.change(getByLabelText("transition track"),
                     { target: { value: track1 } });
    fireEvent.change(getByLabelText("anchor type"),
                     { target: { value: "shot" } });
    fireEvent.change(getByLabelText("anchor"),
                     { target: { value: shot20 } });
    fireEvent.change(getByLabelText("boundary"),
                     { target: { value: "end" } });
    fireEvent.change(getByLabelText("translation x"),
                     { target: { value: "-1200" } });
    fireEvent.change(getByLabelText("translation y"),
                     { target: { value: "0" } });
    fireEvent.change(getByLabelText("translation z"),
                     { target: { value: "-2400" } });
    fireEvent.change(getByLabelText("rotation pitch"),
                     { target: { value: "90000000" } });
    fireEvent.click(getByText("Add transition"));
    await waitFor(() => {
      const post = calls.find(
        (c) => c.url === `/api/spatial-tracks/${track1}/transitions` &&
          c.init?.method === "POST");
      expect(post).toBeDefined();
      expect(JSON.parse(String(post!.init!.body))).toEqual(
        { anchor_type: "shot", anchor_id: shot20, boundary: "end",
          operation: "set",
          translation_mm: [-1200, 0, -2400],
          rotation_udeg: [0, 90000000, 0] });
    });
    await findByText(/shot: Shot 20/);

    // matrix 61 (clear): no transform fields in the request
    fireEvent.change(getByLabelText("anchor type"),
                     { target: { value: "sequence" } });
    fireEvent.change(getByLabelText("anchor"),
                     { target: { value: seq } });
    fireEvent.change(getByLabelText("operation"),
                     { target: { value: "clear" } });
    fireEvent.click(getByText("Add transition"));
    await waitFor(() => {
      const posts = calls.filter(
        (c) => c.url === `/api/spatial-tracks/${track1}/transitions` &&
          c.init?.method === "POST");
      expect(posts).toHaveLength(2);
      expect(JSON.parse(String(posts[1].init!.body))).toEqual(
        { anchor_type: "sequence", anchor_id: seq, boundary: "end",
          operation: "clear" });
    });
  } finally {
    global.fetch = original;
  }
});

test("staging inspector shows exact revision, provenance, distinct " +
     "absence, current-only labeling", async () => {
  const original = global.fetch;
  const preview = stagingBody();
  global.fetch = vi.fn(async (input: RequestInfo | URL) => {
    const url = String(input);
    if (url.endsWith("/workspace")) {
      return new Response(JSON.stringify(workspaceBody()));
    }
    if (url.includes("/staging?shot_id=")) {
      return new Response(JSON.stringify(preview));
    }
    return new Response(JSON.stringify({}), { status: 404 });
  });
  try {
    const { getByLabelText, getByText, findByText } = render(
      <StagingInspector worldId="w1" />);
    await findByText("Current effective staging for this world");

    fireEvent.change(getByLabelText("target shot"),
                     { target: { value: shot21 } });
    fireEvent.click(getByText("Resolve current staging"));

    // matrix 63: exact EntityRevision displayed
    await waitFor(() => {
      expect(getByText(/rev-eva-12/)).toBeDefined();
    });
    // matrix 64: winning-transition provenance displayed
    expect(getByText(/shot\/end/)).toBeDefined();
    expect(getByText(/trn-1234/)).toBeDefined();
    // matrix 65: required vs optional absence are distinct
    expect(getByText(/required track has no effective state/))
      .toBeDefined();
    expect(getByText(/optional track absent/)).toBeDefined();
    // matrix 66: current-staging labeling, never captured history
    expect(getByText(/not captured ShotRevision/)).toBeDefined();
  } finally {
    global.fetch = original;
  }
});
