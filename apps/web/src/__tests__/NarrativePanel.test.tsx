/**
 * M6B — narrative full-set ordering interactions.
 *
 * Every reorder/membership action must send the COMPLETE ordered id set
 * (the full-set contract); these tests pin the payloads for sequence
 * reorder and scene shot membership (remove / move / assign).
 */
import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { Scene, Sequence, ShotListItem } from "@/lib/types";

const reorderSequences = vi.fn();
const putSceneShots = vi.fn();
const reorderScenes = vi.fn();

vi.mock("@/lib/api.client", () => ({
  reorderSequences: (...args: unknown[]) => reorderSequences(...args),
  putSceneShots: (...args: unknown[]) => putSceneShots(...args),
  reorderScenes: (...args: unknown[]) => reorderScenes(...args),
  createSequence: vi.fn(),
  patchSequence: vi.fn(),
  deleteSequence: vi.fn(),
  createScene: vi.fn(),
  patchScene: vi.fn(),
  deleteScene: vi.fn(),
}));

vi.mock("next/navigation", () => ({
  useRouter: () => ({ refresh: vi.fn() }),
}));

import { NarrativePanel } from "@/components/NarrativePanel";

const SEQ_A: Sequence = {
  id: "seq-a",
  project_id: "p1",
  title: "Act I",
  position: 0,
  created_at: "2026-01-01T00:00:00Z",
  updated_at: "2026-01-01T00:00:00Z",
};
const SEQ_B: Sequence = { ...SEQ_A, id: "seq-b", title: "Act II", position: 1 };
const SCENE_1: Scene = {
  id: "scene-1",
  sequence_id: "seq-a",
  title: "Lobby",
  description: null,
  position: 0,
  created_at: "2026-01-01T00:00:00Z",
  updated_at: "2026-01-01T00:00:00Z",
};
const SCENE_2: Scene = { ...SCENE_1, id: "scene-2", position: 1 };

function shot(n: number, sceneId: string | null, pos: number | null): ShotListItem {
  return {
    id: `shot-${n}`,
    project_id: "p1",
    shot_number: n,
    title: null,
    subject: `s${n}`,
    scene_id: sceneId,
    scene_position: pos,
    created_at: "2026-01-01T00:00:00Z",
    updated_at: "2026-01-01T00:00:00Z",
  };
}

const SHOTS = [
  shot(2, "scene-1", 0),
  shot(5, "scene-1", 1),
  shot(7, null, null),
  shot(9, "scene-2", 0),
];

describe("NarrativePanel (M6B full-set payloads)", () => {
  beforeEach(() => {
    reorderSequences.mockReset().mockResolvedValue(undefined);
    reorderScenes.mockReset().mockResolvedValue(undefined);
    putSceneShots.mockReset().mockResolvedValue(undefined);
  });
  afterEach(cleanup);

  it("sequence move-down sends the complete reordered id set", async () => {
    render(
      <NarrativePanel
        projectId="p1"
        sequences={[SEQ_A, SEQ_B]}
        scenes={[]}
        shots={[]}
      />,
    );
    // First sequence's move-down button.
    await userEvent.click(screen.getAllByLabelText("Move down")[0]);
    expect(reorderSequences).toHaveBeenCalledWith("p1", ["seq-b", "seq-a"]);
  });

  it("scene move-up sends the complete reordered scene set", async () => {
    render(
      <NarrativePanel
        projectId="p1"
        sequences={[SEQ_A]}
        scenes={[SCENE_1, SCENE_2]}
        shots={[]}
      />,
    );
    // Move-up buttons in DOM order: sequence (disabled), scene 1 (disabled,
    // first), scene 2 — the third one is the enabled mover.
    await userEvent.click(screen.getAllByLabelText("Move up")[2]);
    expect(reorderScenes).toHaveBeenCalledWith("seq-a", ["scene-2", "scene-1"]);
  });

  it("removing a member sends the remaining full membership set", async () => {
    render(
      <NarrativePanel
        projectId="p1"
        sequences={[SEQ_A]}
        scenes={[SCENE_1]}
        shots={SHOTS}
      />,
    );
    await userEvent.click(screen.getByLabelText("Remove shot 2"));
    expect(putSceneShots).toHaveBeenCalledWith("scene-1", ["shot-5"]);
  });

  it("moving a member within the scene sends the reordered full set", async () => {
    render(
      <NarrativePanel
        projectId="p1"
        sequences={[SEQ_A]}
        scenes={[SCENE_1]}
        shots={SHOTS}
      />,
    );
    // Move-down buttons in DOM order: sequence (disabled), scene (disabled,
    // only one), member shot 2 — the third one is the enabled mover.
    await userEvent.click(screen.getAllByLabelText("Move down")[2]);
    expect(putSceneShots).toHaveBeenCalledWith("scene-1", ["shot-5", "shot-2"]);
  });

  it("assigning an unassigned shot appends to the full membership set", async () => {
    render(
      <NarrativePanel
        projectId="p1"
        sequences={[SEQ_A]}
        scenes={[SCENE_1]}
        shots={SHOTS}
      />,
    );
    const select = screen.getByLabelText("Assign shot");
    await userEvent.selectOptions(select, "shot-7");
    expect(putSceneShots).toHaveBeenCalledWith("scene-1", ["shot-2", "shot-5", "shot-7"]);
  });
});
