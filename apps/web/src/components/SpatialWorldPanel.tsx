/**
 * M10B §50 + M10C §10 — Spatial World workspace: form/table EDITOR.
 *
 * Server-owned authority throughout: every mutation is an explicit
 * server action (frames, membership values, axes, capture, approve,
 * unapprove; M10C adds track requirement/delete, transition set/clear,
 * staging preview). The panel renders the server-computed canonical
 * WORKING hash beside the approved revision hash so working-vs-approved
 * is mechanically visible. No client-side transform/hash/axis/rank
 * computation exists. Narrative ranks are never computed here — anchor
 * pickers are server-fed identities only (M10C §10.2).
 */

"use client";

import { useCallback, useEffect, useState } from "react";
import ErrorBanner from "@/components/ErrorBanner";
import { ApiError } from "@/lib/api.shared";

interface StateFrameRow {
  spatial_frame_id: string;
  frame_key: string;
  bound_entity_id: string | null;
  x_mm: number;
  y_mm: number;
  z_mm: number;
  yaw_udeg: number;
  pitch_udeg: number;
  roll_udeg: number;
  half_x_mm: number | null;
  half_y_mm: number | null;
  half_z_mm: number | null;
}

interface StableFrame {
  id: string;
  key: string;
  name: string;
  parent_spatial_frame_id: string | null;
  bound_entity_id: string | null;
}

interface StableAxis {
  id: string;
  key: string;
  name: string;
}

interface TransitionRow {
  id: string;
  anchor_type: string;
  anchor_id: string;
  boundary: string;
  operation: string;
  x_mm: number | null;
  y_mm: number | null;
  z_mm: number | null;
  yaw_udeg: number | null;
  pitch_udeg: number | null;
  roll_udeg: number | null;
}

interface TrackRow {
  id: string;
  entity_id: string;
  requirement: string;
  transitions: TransitionRow[];
}

interface NarrativeOptions {
  entities: Array<{ id: string; kind: string; name: string }>;
  sequences: Array<{ id: string; title: string | null; position: number }>;
  scenes: Array<{
    id: string; sequence_id: string; title: string | null;
    position: number }>;
  shots: Array<{
    id: string; title: string | null; subject: string;
    scene_id: string | null }>;
}

interface WorldWorkspaceData {
  world: {
    id: string;
    key: string;
    name: string;
    requirement: string;
    location_entity_id: string;
  };
  stable_frames: StableFrame[];
  stable_axes: StableAxis[];
  tracks: TrackRow[];
  narrative: NarrativeOptions;
  states: Array<{
    id: string;
    location_entity_revision_id: string;
    approved_revision_id: string | null;
    working_snapshot_hash: string | null;
    frames: StateFrameRow[];
    axes: Array<{
      spatial_axis_id: string;
      axis_key: string;
      a_frame_id: string;
      b_frame_id: string;
    }>;
    revisions: Array<{
      id: string;
      revision_number: number;
      snapshot_hash: string;
      created_at: string;
    }>;
  }>;
}

async function api(
  path: string, method: string, body?: unknown): Promise<unknown> {
  const res = await fetch(path, {
    method,
    headers: body ? { "Content-Type": "application/json" } : undefined,
    body: body ? JSON.stringify(body) : undefined,
  });
  if (!res.ok) {
    const err = await res.json().catch(() => null);
    throw new Error(err?.message ?? `${method} ${path} failed (${res.status})`);
  }
  if (method === "POST") return res.json();
  return null;
}

const num = (v: string) => Number.parseInt(v, 10) || 0;

export function SpatialWorldPanel({ worldId }: { worldId: string }) {
  const [data, setData] = useState<WorldWorkspaceData | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [frameKey, setFrameKey] = useState("");
  const [frameName, setFrameName] = useState("");
  const [tx, setTx] = useState("0");
  const [ty, setTy] = useState("0");
  const [tz, setTz] = useState("0");
  const [axisKey, setAxisKey] = useState("");
  const [axisA, setAxisA] = useState("");
  const [axisB, setAxisB] = useState("");
  const [memberFrame, setMemberFrame] = useState("");
  const [hx, setHx] = useState("");
  const [hy, setHy] = useState("");
  const [hz, setHz] = useState("");
  const [trackEntity, setTrackEntity] = useState("");
  const [trackReq, setTrackReq] = useState("optional");
  const [trTrack, setTrTrack] = useState("");
  const [trAnchorType, setTrAnchorType] = useState("shot");
  const [trAnchorId, setTrAnchorId] = useState("");
  const [trBoundary, setTrBoundary] = useState("start");
  const [trOperation, setTrOperation] = useState("set");
  const [trT, setTrT] = useState(["0", "0", "0"]);
  const [trR, setTrR] = useState(["0", "0", "0"]);

  const load = useCallback(async () => {
    try {
      const res = await fetch(`/api/spatial-worlds/${worldId}/workspace`);
      if (!res.ok) throw new Error(`workspace load failed (${res.status})`);
      setData(await res.json());
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }, [worldId]);

  useEffect(() => {
    void load();
  }, [load]);

  async function act(fn: () => Promise<void>) {
    setBusy(true);
    try {
      await fn();
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  if (error) {
    return (
      <ErrorBanner
        error={new ApiError("SPATIAL_WORLD_INVALID", error, 500)} />
    );
  }
  if (!data) return <div className="card">Loading spatial world…</div>;

  const first = data.states[0];

  return (
    <div className="stack">
      <div className="card row">
        <div>
          <strong>{data.world.name}</strong>{" "}
          <span className="meta">({data.world.key})</span>
          <span className={`badge ${data.world.requirement === "required"
            ? "badge-error" : "badge-matches"}`}>
            {data.world.requirement}
          </span>
        </div>
      </div>

      <div className="card">
        <h3>Temporal staging tracks (M10C)</h3>
        <div className="row">
          <select value={trackEntity}
                  onChange={(e) => setTrackEntity(e.target.value)}
                  aria-label="track entity">
            <option value="">select entity…</option>
            {data.narrative.entities.map((e) => (
              <option key={e.id} value={e.id}>
                {e.name} ({e.kind})
              </option>
            ))}
          </select>
          <select value={trackReq}
                  onChange={(e) => setTrackReq(e.target.value)}
                  aria-label="track requirement">
            <option value="required">required</option>
            <option value="optional">optional</option>
          </select>
          <button disabled={busy || !trackEntity}
                  onClick={() => void act(async () => {
                    await api(
                      `/api/spatial-worlds/${worldId}/tracks`, "POST",
                      { entity_id: trackEntity, requirement: trackReq });
                    setTrackEntity("");
                  })}>Create track</button>
        </div>
        {data.tracks.length === 0 && (
          <div className="meta">No active tracks in this world.</div>
        )}
        {data.tracks.map((t) => {
          const ent = data.narrative.entities.find(
            (e) => e.id === t.entity_id);
          return (
            <div key={t.id} className="card">
              <div className="row">
                <strong>{ent ? ent.name : "Entity"}{" "}
                  <span className="meta">
                    track {t.id.slice(0, 8)}…
                  </span>
                </strong>
                <span className={`badge ${t.requirement === "required"
                  ? "badge-error" : "badge-matches"}`}>
                  {t.requirement}
                </span>
                <button disabled={busy}
                        onClick={() => void act(async () => {
                          await api(`/api/spatial-tracks/${t.id}`,
                                    "PATCH",
                                    { requirement: t.requirement ===
                                      "required" ? "optional" :
                                      "required" });
                        })}>
                  Make {t.requirement === "required" ? "optional"
                                              : "required"}
                </button>
                <button disabled={busy}
                        onClick={() => void act(async () => {
                          await api(`/api/spatial-tracks/${t.id}`,
                                    "DELETE");
                        })}>Delete track</button>
              </div>
              <table className="table">
                <thead>
                  <tr>
                    <th>Anchor</th><th>Boundary</th><th>Op</th>
                    <th>X/Y/Z mm</th><th>Yaw/Pitch/Roll µ°</th><th />
                  </tr>
                </thead>
                <tbody>
                  {t.transitions.map((tr) => {
                    const label = tr.anchor_type === "sequence"
                      ? (data.narrative.sequences.find(
                          (s) => s.id === tr.anchor_id)?.title ??
                        tr.anchor_id.slice(0, 8))
                      : tr.anchor_type === "scene"
                        ? (data.narrative.scenes.find(
                            (s) => s.id === tr.anchor_id)?.title ??
                          tr.anchor_id.slice(0, 8))
                        : (data.narrative.shots.find(
                            (s) => s.id === tr.anchor_id)?.title ??
                          tr.anchor_id.slice(0, 8));
                    return (
                      <tr key={tr.id}>
                        <td>{tr.anchor_type}: {label}</td>
                        <td>{tr.boundary}</td>
                        <td>{tr.operation}</td>
                        <td>{tr.operation === "set"
                          ? `${tr.x_mm} / ${tr.y_mm} / ${tr.z_mm}` : "—"}</td>
                        <td>{tr.operation === "set"
                          ? `${tr.yaw_udeg} / ${tr.pitch_udeg} / ` +
                            `${tr.roll_udeg}` : "—"}</td>
                        <td>
                          <button disabled={busy}
                                  onClick={() => void act(async () => {
                                    await api(
                                      `/api/spatial-transitions/${tr.id}`,
                                      "DELETE");
                                  })}>Delete</button>
                        </td>
                      </tr>
                    );
                  })}
                  {t.transitions.length === 0 && (
                    <tr><td colSpan={6} className="meta">
                      No active transitions
                    </td></tr>
                  )}
                </tbody>
              </table>
            </div>
          );
        })}
        <h4>Author transition</h4>
        <div className="row">
          <select value={trTrack} aria-label="transition track"
                  onChange={(e) => setTrTrack(e.target.value)}>
            <option value="">track…</option>
            {data.tracks.map((t) => (
              <option key={t.id} value={t.id}>
                {data.narrative.entities.find(
                  (e) => e.id === t.entity_id)?.name ?? t.id.slice(0, 8)}
              </option>
            ))}
          </select>
          <select value={trAnchorType} aria-label="anchor type"
                  onChange={(e) => {
                    setTrAnchorType(e.target.value);
                    setTrAnchorId("");
                  }}>
            <option value="sequence">sequence</option>
            <option value="scene">scene</option>
            <option value="shot">shot</option>
          </select>
          <select value={trAnchorId} aria-label="anchor"
                  onChange={(e) => setTrAnchorId(e.target.value)}>
            <option value="">anchor…</option>
            {(trAnchorType === "sequence"
              ? data.narrative.sequences.map((s) => [s.id,
                  s.title ?? s.id.slice(0, 8)] as const)
              : trAnchorType === "scene"
                ? data.narrative.scenes.map((s) => [s.id,
                    s.title ?? s.id.slice(0, 8)] as const)
                : data.narrative.shots.map((s) => [s.id,
                    s.title ?? s.subject.slice(0, 24)] as const)
            ).map(([id, label]) => (
              <option key={id} value={id}>{label}</option>
            ))}
          </select>
          <select value={trBoundary} aria-label="boundary"
                  onChange={(e) => setTrBoundary(e.target.value)}>
            <option value="start">start</option>
            <option value="end">end</option>
          </select>
          <select value={trOperation} aria-label="operation"
                  onChange={(e) => setTrOperation(e.target.value)}>
            <option value="set">set</option>
            <option value="clear">clear</option>
          </select>
          {trOperation === "set" && (
            <>
              {(["x", "y", "z"] as const).map((k, i) => (
                <input key={k} placeholder={`${k} mm`}
                       aria-label={`translation ${k}`}
                       value={trT[i]}
                       onChange={(e) => setTrT(
                         trT.map((v, j) => j === i ? e.target.value : v)
                       )} />
              ))}
              {(["yaw", "pitch", "roll"] as const).map((k, i) => (
                <input key={k} placeholder={`${k} µ°`}
                       aria-label={`rotation ${k}`}
                       value={trR[i]}
                       onChange={(e) => setTrR(
                         trR.map((v, j) => j === i ? e.target.value : v)
                       )} />
              ))}
            </>
          )}
          <button
            disabled={busy || !trTrack || !trAnchorId ||
              (trOperation === "set" &&
               (trT.some((v) => v === "") || trR.some((v) => v === "")))}
            onClick={() => void act(async () => {
              await api(`/api/spatial-tracks/${trTrack}/transitions`,
                        "POST",
                        { anchor_type: trAnchorType,
                          anchor_id: trAnchorId,
                          boundary: trBoundary,
                          operation: trOperation,
                          ...(trOperation === "set" ? {
                            translation_mm: trT.map(num),
                            rotation_udeg: trR.map(num),
                          } : {}) });
            })}>Add transition</button>
        </div>
      </div>

      {data.states.map((st) => (
        <div key={st.id} className="card">
          <div className="row">
            <strong>State {st.id.slice(0, 8)}…</strong>
            <span className={`badge ${st.approved_revision_id
              ? "badge-matches" : "badge-error"}`}>
              {st.approved_revision_id
                ? `Approved ${st.approved_revision_id.slice(0, 8)}…`
                : "No approved revision"}
            </span>
          </div>
          <div className="meta">
            Working hash:{" "}
            <code>{st.working_snapshot_hash
              ? st.working_snapshot_hash.slice(0, 16) + "…"
              : "unavailable"}</code>
          </div>

          <h4>Working membership (mutable; not captured authority)</h4>
          <table className="table">
            <thead>
              <tr>
                <th>Frame key</th><th>X/Y/Z mm</th><th>Yaw/Pitch/Roll µ°</th>
                <th>Half extents</th><th>Bound entity</th>
              </tr>
            </thead>
            <tbody>
              {st.frames.map((f) => (
                <tr key={f.spatial_frame_id}>
                  <td>{f.frame_key}</td>
                  <td>{f.x_mm} / {f.y_mm} / {f.z_mm}</td>
                  <td>{f.yaw_udeg} / {f.pitch_udeg} / {f.roll_udeg}</td>
                  <td>{f.half_x_mm == null
                    ? "—"
                    : `${f.half_x_mm} / ${f.half_y_mm} / ${f.half_z_mm}`}</td>
                  <td>{f.bound_entity_id
                    ? f.bound_entity_id.slice(0, 8) + "…" : "—"}</td>
                </tr>
              ))}
              {st.frames.length === 0 && (
                <tr><td colSpan={5} className="meta">No frames included</td></tr>
              )}
            </tbody>
          </table>
          {st.axes.length > 0 && (
            <>
              <h4>Working axes</h4>
              <ul>
                {st.axes.map((a) => (
                  <li key={a.spatial_axis_id}>
                    {a.axis_key}: {a.a_frame_id.slice(0, 8)}… ↔{" "}
                    {a.b_frame_id.slice(0, 8)}…
                  </li>
                ))}
              </ul>
            </>
          )}

          <h4>Author frame</h4>
          <div className="row">
            <input placeholder="frame key" value={frameKey}
                   onChange={(e) => setFrameKey(e.target.value)} />
            <input placeholder="name" value={frameName}
                   onChange={(e) => setFrameName(e.target.value)} />
            <button disabled={busy || !frameKey || !frameName}
                    onClick={() => void act(async () => {
                      const created = await api(
                        `/api/spatial-worlds/${worldId}/frames`,
                        "POST", { key: frameKey, name: frameName });
                      setFrameKey(""); setFrameName("");
                      setMemberFrame(
                        (created as { id: string } | null)?.id ?? "");
                    })}>Create frame</button>
          </div>
          <div className="row">
            <select value={memberFrame} aria-label="membership frame"
                    onChange={(e) => setMemberFrame(e.target.value)}>
              <option value="">select frame…</option>
              {data.stable_frames.map((f) => (
                <option key={f.id} value={f.id}>
                  {f.key}
                </option>
              ))}
            </select>
            <input placeholder="x mm" value={tx}
                   onChange={(e) => setTx(e.target.value)} />
            <input placeholder="y mm" value={ty}
                   onChange={(e) => setTy(e.target.value)} />
            <input placeholder="z mm" value={tz}
                   onChange={(e) => setTz(e.target.value)} />
            <input placeholder="half x (opt)" value={hx}
                   onChange={(e) => setHx(e.target.value)} />
            <input placeholder="half y (opt)" value={hy}
                   onChange={(e) => setHy(e.target.value)} />
            <input placeholder="half z (opt)" value={hz}
                   onChange={(e) => setHz(e.target.value)} />
            <button
              disabled={busy || !memberFrame}
              onClick={() => void act(async () => {
                const halves = hx && hy && hz
                  ? [num(hx), num(hy), num(hz)] : null;
                await api(
                  `/api/spatial-world-states/${st.id}/frames/` +
                  `${memberFrame}`,
                  "PUT",
                  { translation_mm: [num(tx), num(ty), num(tz)],
                    rotation_udeg: [0, 0, 0],
                    half_extents_mm: halves });
              })}>Set membership value</button>
          </div>

          <h4>Author axis</h4>
          <div className="meta">
            Endpoints must already be included in this state (endpoints
            list only member frames).
          </div>
          <div className="row">
            <input placeholder="axis key" value={axisKey}
                   onChange={(e) => setAxisKey(e.target.value)} />
            <select value={axisA} aria-label="axis endpoint a"
                    onChange={(e) => setAxisA(e.target.value)}>
              <option value="">endpoint A…</option>
              {st.frames.map((f) => (
                <option key={f.spatial_frame_id}
                        value={f.spatial_frame_id}>
                  {f.frame_key}
                </option>
              ))}
            </select>
            <select value={axisB} aria-label="axis endpoint b"
                    onChange={(e) => setAxisB(e.target.value)}>
              <option value="">endpoint B…</option>
              {st.frames.map((f) => (
                <option key={f.spatial_frame_id}
                        value={f.spatial_frame_id}>
                  {f.frame_key}
                </option>
              ))}
            </select>
            <button
              disabled={busy || !axisKey || !axisA || !axisB || axisA === axisB}
              onClick={() => void act(async () => {
                const created = await api(
                  `/api/spatial-worlds/${worldId}/axes`, "POST",
                  { key: axisKey, name: axisKey }) as { id: string };
                await api(
                  `/api/spatial-world-states/${st.id}/axes/` +
                  `${created.id}`,
                  "PUT",
                  { a_frame_id: axisA, b_frame_id: axisB });
                setAxisKey(""); setAxisA(""); setAxisB("");
              })}>Create + bind axis</button>
          </div>

          <div className="row">
            <button disabled={busy} onClick={() => void act(async () => {
              await api(`/api/spatial-world-states/${st.id}/revisions`,
                        "POST");
            })}>Capture revision</button>
            {st.revisions.map((r) => (
              <button key={r.id} disabled={busy ||
                st.approved_revision_id === r.id}
                onClick={() => void act(async () => {
                  await api(
                    `/api/spatial-world-states/${st.id}/approval`,
                    "PUT",
                    { revision_id: r.id,
                      expected_approved_revision_id:
                        st.approved_revision_id });
                })}>Approve #{r.revision_number}</button>
            ))}
            {st.approved_revision_id && (
              <button disabled={busy}
                      onClick={() => void act(async () => {
                        await api(
                          `/api/spatial-world-states/${st.id}/approval`,
                          "DELETE",
                          { expected_approved_revision_id:
                              st.approved_revision_id });
                      })}>Unapprove</button>
            )}
          </div>

          <h4>Revision history (immutable)</h4>
          <table className="table">
            <thead>
              <tr><th>#</th><th>Hash</th><th>Captured at</th><th /></tr>
            </thead>
            <tbody>
              {st.revisions.map((r) => (
                <tr key={r.id}>
                  <td>{r.revision_number}</td>
                  <td><code>{r.snapshot_hash.slice(0, 16)}…</code></td>
                  <td>{r.created_at}</td>
                  <td>{st.approved_revision_id === r.id
                    ? <span className="badge badge-matches">Approved</span>
                    : null}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ))}
      {first === undefined && (
        <div className="card">No states for this world yet.</div>
      )}
    </div>
  );
}
