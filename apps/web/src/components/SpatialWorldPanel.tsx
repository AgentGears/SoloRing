/**
 * M10B §50 — Spatial World workspace (form/table, server-owned state).
 *
 * Working vs Approved authority is ALWAYS visually distinct (§89): the
 * working membership table and the approved immutable revision render
 * under separate labeled sections; nothing client-side computes
 * transforms, hashes, or axis sides. Capture and approval are explicit
 * server actions.
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

interface WorldWorkspaceData {
  world: {
    id: string;
    key: string;
    name: string;
    requirement: string;
    location_entity_id: string;
  };
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

export function SpatialWorldPanel({ worldId }: { worldId: string }) {
  const [data, setData] = useState<WorldWorkspaceData | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

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

  async function capture(stateId: string) {
    setBusy(true);
    try {
      const res = await fetch(
        `/api/spatial-world-states/${stateId}/revisions`,
        { method: "POST" });
      if (!res.ok) {
        const body = await res.json().catch(() => null);
        throw new Error(body?.message ?? `capture failed (${res.status})`);
      }
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  async function approve(stateId: string, revisionId: string,
                         expected: string | null) {
    setBusy(true);
    try {
      const res = await fetch(
        `/api/spatial-world-states/${stateId}/approval`,
        { method: "PUT",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            revision_id: revisionId,
            expected_approved_revision_id: expected }) });
      if (!res.ok) {
        const body = await res.json().catch(() => null);
        throw new Error(body?.message ?? `approval failed (${res.status})`);
      }
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
      {data.states.map((st) => (
        <div key={st.id} className="card">
          <div className="row">
            <strong>State {st.id.slice(0, 8)}…</strong>
            <span className="meta">
              Location revision {st.location_entity_revision_id.slice(0, 8)}…
            </span>
            <span className={`badge ${st.approved_revision_id
              ? "badge-matches" : "badge-error"}`}>
              {st.approved_revision_id
                ? `Approved ${st.approved_revision_id.slice(0, 8)}…`
                : "No approved revision"}
            </span>
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
                    {a.b_frame_id.slice(0,8)}…
                  </li>
                ))}
              </ul>
            </>
          )}

          <div className="row">
            <button disabled={busy} onClick={() => void capture(st.id)}>
              Capture revision
            </button>
            {st.revisions.map((r) => (
              <button key={r.id} disabled={busy ||
                st.approved_revision_id === r.id}
                onClick={() => void approve(
                  st.id, r.id, st.approved_revision_id)}>
                Approve #{r.revision_number}
              </button>
            ))}
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
    </div>
  );
}
