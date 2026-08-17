"use client";

// Narrative surface (M6B plan §28/§42): Sequence → Scene → ordered Shots.
// Explicit ordering only; shot_number is production identity and never
// changes here. All reorder/membership operations send the COMPLETE
// ordered set (full-set contract).

import { useRouter } from "next/navigation";
import { useState } from "react";

import {
  createScene,
  createSequence,
  deleteScene,
  deleteSequence,
  patchScene,
  patchSequence,
  putSceneShots,
  reorderScenes,
  reorderSequences,
} from "@/lib/api.client";
import { asApiError, type ApiError } from "@/lib/api.shared";
import type { Scene, Sequence, ShotListItem } from "@/lib/types";
import ErrorBanner from "./ErrorBanner";

function moved(ids: string[], from: number, to: number): string[] {
  const next = [...ids];
  const [item] = next.splice(from, 1);
  next.splice(to, 0, item);
  return next;
}

function MoveButtons({
  onUp,
  onDown,
  first,
  last,
}: {
  onUp: () => void;
  onDown: () => void;
  first: boolean;
  last: boolean;
}) {
  return (
    <span>
      <button
        className="btn btn-small"
        onClick={onUp}
        disabled={first}
        aria-label="Move up"
      >
        ↑
      </button>{" "}
      <button
        className="btn btn-small"
        onClick={onDown}
        disabled={last}
        aria-label="Move down"
      >
        ↓
      </button>
    </span>
  );
}

function SceneShots({
  scene,
  shots,
}: {
  scene: Scene;
  shots: ShotListItem[];
}) {
  const router = useRouter();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<ApiError | null>(null);

  const members = shots
    .filter((s) => s.scene_id === scene.id)
    .sort((a, b) => (a.scene_position ?? 0) - (b.scene_position ?? 0));
  const unassigned = shots.filter((s) => s.scene_id === null);
  const memberIds = members.map((m) => m.id);

  async function replace(next: string[]) {
    if (busy) return;
    setBusy(true);
    setError(null);
    try {
      await putSceneShots(scene.id, next);
      router.refresh();
    } catch (err) {
      setError(asApiError(err));
    } finally {
      setBusy(false);
    }
  }

  async function assign(shotId: string) {
    await replace([...memberIds, shotId]);
  }

  return (
    <div className="meta">
      {error ? (
        <ErrorBanner error={error} onDismiss={() => setError(null)} />
      ) : null}
      {members.length === 0 ? (
        <div className="empty">No shots assigned.</div>
      ) : (
        members.map((m, i) => (
          <div className="row" key={m.id}>
            <span>
              {i}. Shot {m.shot_number}
              {m.title ? ` — ${m.title}` : ""}
            </span>
            <span>
              <MoveButtons
                first={i === 0}
                last={i === members.length - 1}
                onUp={() => replace(moved(memberIds, i, i - 1))}
                onDown={() => replace(moved(memberIds, i, i + 1))}
              />{" "}
              <button
                className="btn btn-small"
                onClick={() => replace(memberIds.filter((id) => id !== m.id))}
                disabled={busy}
                aria-label={`Remove shot ${m.shot_number}`}
              >
                ✕
              </button>
            </span>
          </div>
        ))
      )}
      {unassigned.length > 0 ? (
        <div className="form-row">
          <select
            defaultValue=""
            onChange={(e) => {
              const v = e.target.value;
              e.target.value = "";
              if (v) assign(v);
            }}
            aria-label="Assign shot"
          >
            <option value="">Assign shot…</option>
            {unassigned.map((s) => (
              <option key={s.id} value={s.id}>
                Shot {s.shot_number}
                {s.title ? ` — ${s.title}` : ""}
              </option>
            ))}
          </select>
        </div>
      ) : null}
    </div>
  );
}

export function NarrativePanel({
  projectId,
  sequences,
  scenes,
  shots,
}: {
  projectId: string;
  sequences: Sequence[];
  scenes: Scene[];
  shots: ShotListItem[];
}) {
  const router = useRouter();
  const [seqTitle, setSeqTitle] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<ApiError | null>(null);
  const [sceneTitles, setSceneTitles] = useState<Record<string, string>>({});
  const [seqTitles, setSeqTitles] = useState<Record<string, string>>({});

  const sequenceIds = sequences.map((s) => s.id);

  async function run(fn: () => Promise<unknown>) {
    if (busy) return;
    setBusy(true);
    setError(null);
    try {
      await fn();
      router.refresh();
    } catch (err) {
      setError(asApiError(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <section>
      {sequences.map((seq, i) => {
        const seqScenes = scenes
          .filter((c) => c.sequence_id === seq.id)
          .sort((a, b) => a.position - b.position);
        const sceneIds = seqScenes.map((c) => c.id);
        return (
          <div className="card" key={seq.id}>
            <div className="row">
              <strong>
                {seq.position}. {seq.title ?? "Untitled sequence"}
              </strong>
              <span>
                <MoveButtons
                  first={i === 0}
                  last={i === sequences.length - 1}
                  onUp={() =>
                    run(() => reorderSequences(projectId, moved(sequenceIds, i, i - 1)))
                  }
                  onDown={() =>
                    run(() => reorderSequences(projectId, moved(sequenceIds, i, i + 1)))
                  }
                />{" "}
                <button
                  className="btn btn-small"
                  onClick={() =>
                    run(() => deleteSequence(seq.id))
                  }
                  aria-label="Delete sequence"
                >
                  Delete
                </button>
              </span>
            </div>
            <div className="form-row">
              <input
                placeholder="Rename sequence"
                value={seqTitles[seq.id] ?? ""}
                onChange={(e) =>
                  setSeqTitles({ ...seqTitles, [seq.id]: e.target.value })
                }
              />
              <button
                className="btn btn-small"
                onClick={() =>
                  run(() =>
                    patchSequence(seq.id, seqTitles[seq.id]?.trim() || null)
                  )
                }
                disabled={busy}
              >
                Rename
              </button>
            </div>

            {seqScenes.map((scene, j) => (
              <div className="card" key={scene.id}>
                <div className="row">
                  <span>
                    {scene.position}. {scene.title ?? "Untitled scene"}
                  </span>
                  <span>
                    <MoveButtons
                      first={j === 0}
                      last={j === seqScenes.length - 1}
                      onUp={() =>
                        run(() => reorderScenes(seq.id, moved(sceneIds, j, j - 1)))
                      }
                      onDown={() =>
                        run(() => reorderScenes(seq.id, moved(sceneIds, j, j + 1)))
                      }
                    />{" "}
                    <button
                      className="btn btn-small"
                      onClick={() => run(() => deleteScene(scene.id))}
                      aria-label="Delete scene"
                    >
                      Delete
                    </button>
                  </span>
                </div>
                <div className="form-row">
                  <input
                    placeholder="Rename scene"
                    value={sceneTitles[scene.id] ?? ""}
                    onChange={(e) =>
                      setSceneTitles({
                        ...sceneTitles,
                        [scene.id]: e.target.value,
                      })
                    }
                  />
                  <button
                    className="btn btn-small"
                    onClick={() =>
                      run(() =>
                        patchScene(scene.id, sceneTitles[scene.id]?.trim() || null)
                      )
                    }
                    disabled={busy}
                  >
                    Rename
                  </button>
                </div>
                <SceneShots scene={scene} shots={shots} />
              </div>
            ))}

            <div className="form-row">
              <input
                placeholder="New scene title"
                value={sceneTitles[`new:${seq.id}`] ?? ""}
                onChange={(e) =>
                  setSceneTitles({
                    ...sceneTitles,
                    [`new:${seq.id}`]: e.target.value,
                  })
                }
              />
              <button
                className="btn btn-small"
                onClick={() =>
                  run(() =>
                    createScene(
                      seq.id,
                      sceneTitles[`new:${seq.id}`]?.trim() || null
                    )
                  )
                }
                disabled={busy}
              >
                Add scene
              </button>
            </div>
          </div>
        );
      })}

      {error ? (
        <ErrorBanner error={error} onDismiss={() => setError(null)} />
      ) : null}
      <form
        className="card form-row"
        onSubmit={(e) => {
          e.preventDefault();
          run(() =>
            createSequence(projectId, seqTitle.trim() || null)
          ).then(() => setSeqTitle(""));
        }}
      >
        <input
          placeholder="New sequence title"
          value={seqTitle}
          onChange={(e) => setSeqTitle(e.target.value)}
        />
        <button className="btn" type="submit" disabled={busy}>
          Add sequence
        </button>
      </form>
    </section>
  );
}
