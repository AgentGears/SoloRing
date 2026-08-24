/**
 * M10B world editor — end-to-end authoring acceptance paths (P0-4).
 *
 * Mechanically performs: create frame -> select it -> set state value ->
 * appears in working membership; create axis -> bind to two included
 * frames -> appears in working axes. Plus working-hash display and the
 * unapprove DELETE. All assertions genuinely awaited.
 */

import { fireEvent, render, waitFor } from "@testing-library/react";
import { expect, test, vi } from "vitest";
import { SpatialWorldPanel } from "@/components/SpatialWorldPanel";

function body(approved: string | null) {
  return {
    world: { id: "w1", key: "lobby", name: "Lobby",
             requirement: "required", location_entity_id: "e1" },
    stable_frames: [
      { id: "f1", key: "front-desk", name: "Desk",
        parent_spatial_frame_id: null, bound_entity_id: null },
      { id: "f2", key: "sofa", name: "Sofa",
        parent_spatial_frame_id: null, bound_entity_id: null },
    ],
    stable_axes: [],
    states: [{
      id: "s1", location_entity_revision_id: "r1",
      approved_revision_id: approved,
      working_snapshot_hash: "f".repeat(64),
      frames: [
        { spatial_frame_id: "f1", frame_key: "front-desk",
          bound_entity_id: null,
          x_mm: 0, y_mm: 0, z_mm: 4200,
          yaw_udeg: 0, pitch_udeg: 0, roll_udeg: 0,
          half_x_mm: 2200, half_y_mm: 600, half_z_mm: 550 },
        { spatial_frame_id: "f2", frame_key: "sofa",
          bound_entity_id: null,
          x_mm: 900, y_mm: -300, z_mm: -1500,
          yaw_udeg: 0, pitch_udeg: 0, roll_udeg: 0,
          half_x_mm: 350, half_y_mm: 250, half_z_mm: 150 }],
      axes: [],
      revisions: [
        { id: "rev1", revision_number: 1, snapshot_hash: "a".repeat(64),
          created_at: "t1" }],
    }],
  };
}

test("frame authoring: create -> select -> set value -> membership",
     async () => {
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const workspace: any = body("rev1");
  const original = global.fetch;
  const fetchMock = vi.fn(async (input: RequestInfo | URL,
                                  init?: RequestInit) => {
    const url = String(input);
    if (url.endsWith("/frames") && init?.method === "POST") {
      workspace.stable_frames.push(
        { id: "f9", key: "new-frame", name: "New",
          parent_spatial_frame_id: null, bound_entity_id: null });
      return new Response(JSON.stringify({ id: "f9", key: "new-frame" }),
                           { status: 201 });
    }
    if (url.match(/\/frames\/f9$/) && init?.method === "PUT") {
      workspace.states[0].frames.push({
        spatial_frame_id: "f9", frame_key: "new-frame",
        bound_entity_id: null, x_mm: 5, y_mm: 0, z_mm: -100,
        yaw_udeg: 0, pitch_udeg: 0, roll_udeg: 0,
        half_x_mm: undefined, half_y_mm: undefined,
        half_z_mm: undefined });
      return new Response(null, { status: 204 });
    }
    return new Response(JSON.stringify(workspace), { status: 200 });
  });
  global.fetch = fetchMock as unknown as typeof fetch;
  try {
    const { container } = render(<SpatialWorldPanel worldId="w1" />);
    await waitFor(() => {
      expect(container.textContent).toContain("Working membership");
    });
    const keyInput = container.querySelector(
      'input[placeholder="frame key"]')!;
    const nameInput = container.querySelector(
      'input[placeholder="name"]')!;
    fireEvent.change(keyInput, { target: { value: "new-frame" } });
    fireEvent.change(nameInput, { target: { value: "New" } });
    const createBtn = Array.from(container.querySelectorAll("button"))
      .find((b) => b.textContent === "Create frame")!;
    fireEvent.click(createBtn);
    // create returned f9 and selected it for membership
    await waitFor(() => {
      const sel = container.querySelector("select")!;
      expect((sel as HTMLSelectElement).value).toBe("f9");
    });
    // fill value and PUT
    const xInput = container.querySelector('input[placeholder="x mm"]')!;
    fireEvent.change(xInput, { target: { value: "5" } });
    const setBtn = Array.from(container.querySelectorAll("button"))
      .find((b) => b.textContent === "Set membership value")!;
    fireEvent.click(setBtn);
    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        "/api/spatial-world-states/s1/frames/f9",
        expect.objectContaining({ method: "PUT" }));
      expect(container.textContent).toContain("new-frame");
    });
  } finally {
    global.fetch = original;
  }
});

test("axis authoring: create -> bind endpoints -> working axes",
     async () => {
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const workspace: any = body(null);
  const original = global.fetch;
  const fetchMock = vi.fn(async (input: RequestInfo | URL,
                                  init?: RequestInit) => {
    const url = String(input);
    if (url.endsWith("/axes") && init?.method === "POST") {
      workspace.stable_axes.push({ id: "ax9", key: "ax", name: "ax" });
      return new Response(JSON.stringify({ id: "ax9", key: "ax" }),
                           { status: 201 });
    }
    if (url.match(/\/axes\/ax9$/) && init?.method === "PUT") {
      workspace.states[0].axes.push({
        spatial_axis_id: "ax9", axis_key: "ax",
        a_frame_id: "f1", b_frame_id: "f2" });
      return new Response(null, { status: 204 });
    }
    return new Response(JSON.stringify(workspace), { status: 200 });
  });
  global.fetch = fetchMock as unknown as typeof fetch;
  try {
    const { container } = render(<SpatialWorldPanel worldId="w1" />);
    await waitFor(() => {
      expect(container.textContent).toContain("Working membership");
    });
    const keyInput = container.querySelector(
      'input[placeholder="axis key"]')!;
    fireEvent.change(keyInput, { target: { value: "ax" } });
    const selects = Array.from(container.querySelectorAll("select"));
    fireEvent.change(selects[1], { target: { value: "f1" } });
    fireEvent.change(selects[2], { target: { value: "f2" } });
    const bindBtn = Array.from(container.querySelectorAll("button"))
      .find((b) => b.textContent === "Create + bind axis")!;
    fireEvent.click(bindBtn);
    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        "/api/spatial-world-states/s1/axes/ax9",
        expect.objectContaining({
          method: "PUT",
          body: JSON.stringify({ a_frame_id: "f1", b_frame_id: "f2" }) }));
      expect(container.textContent).toContain("ax:");
    });
  } finally {
    global.fetch = original;
  }
});

test("axis endpoint selectors list ONLY state-member frames", async () => {
  // stable_frames includes f3 which is NOT a member of states[0];
  // the endpoint selectors must not offer it (backend would reject)
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const workspace: any = body(null);
  workspace.stable_frames.push(
    { id: "f3", key: "unmembered", name: "U",
      parent_spatial_frame_id: null, bound_entity_id: null });
  const original = global.fetch;
  const fetchMock = vi.fn(async () =>
    new Response(JSON.stringify(workspace), { status: 200 }));
  global.fetch = fetchMock as unknown as typeof fetch;
  try {
    const { container } = render(<SpatialWorldPanel worldId="w1" />);
    await waitFor(() => {
      expect(container.textContent).toContain("Working membership");
    });
    // selects: [0] membership (stable), [1] endpoint A, [2] endpoint B
    const selects = Array.from(container.querySelectorAll("select"));
    const endpointA = Array.from(
      selects[1].querySelectorAll("option")).map((o) => o.value);
    const endpointB = Array.from(
      selects[2].querySelectorAll("option")).map((o) => o.value);
    for (const options of [endpointA, endpointB]) {
      expect(options).toContain("f1");
      expect(options).toContain("f2");
      expect(options).not.toContain("f3");
    }
    // the membership selector (stable identities) DOES offer f3
    const memberOptions = Array.from(
      selects[0].querySelectorAll("option")).map((o) => o.value);
    expect(memberOptions).toContain("f3");
  } finally {
    global.fetch = original;
  }
});

test("working hash displayed and unapprove fires DELETE", async () => {
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const workspace: any = body("rev1");
  const original = global.fetch;
  const fetchMock = vi.fn(async () =>
    new Response(JSON.stringify(workspace), { status: 200 }));
  global.fetch = fetchMock as unknown as typeof fetch;
  try {
    const { container } = render(<SpatialWorldPanel worldId="w1" />);
    await waitFor(() => {
      expect(container.textContent).toContain("ffffffffffffffff");
      expect(container.textContent).toContain("Approved");
    });
    const unapprove = Array.from(container.querySelectorAll("button"))
      .find((b) => b.textContent === "Unapprove")!;
    expect(unapprove).toBeTruthy();
    fireEvent.click(unapprove);
    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        "/api/spatial-world-states/s1/approval",
        expect.objectContaining({ method: "DELETE" }));
    });
  } finally {
    global.fetch = original;
  }
});
