/**
 * M10D §44-47 — Shot spatial continuity panel: CURRENT complete
 * projection + Shot plan CAS editor.
 *
 * Every displayed value comes from
 * GET /api/shots/{id}/spatial-continuity — the client never computes
 * world selection, staging winners, axis validity, or hashes. The plan
 * editor sends real CAS requests carrying the LAST server-returned
 * plan_hash; SPATIAL_SHOT_PLAN_CONFLICT instructs reconciliation
 * (never auto-overwrite). Labels say CURRENT; the captured view lives
 * in the revision provenance list (SpatialProvenanceBlock).
 */

"use client";

import { useCallback, useEffect, useState } from "react";
import ErrorBanner from "@/components/ErrorBanner";
import { ApiError } from "@/lib/api.shared";

interface Issue {
  code: string;
  layer: string;
  message: string;
  details: Record<string, unknown>;
}

interface SpatialContinuityBody {
  shot_id: string;
  ready: boolean;
  spatial_continuity_hash: string | null;
  issues: Issue[];
  spatial_continuity: {
    selected_world: {
      spatial_world_id: string;
      requirement: string;
      location_entity_id: string;
    };
    location_entity_revision_id: string | null;
    approved_world_revision: {
      id: string;
      revision_number: number;
      snapshot_hash: string;
    } | null;
    staging: Array<{
      spatial_track_id: string;
      entity_id: string;
      entity_revision_id: string;
      requirement: string;
      transform: {
        translation_mm: [number, number, number];
        rotation_udeg: [number, number, number];
      };
      source_transition: {
        id: string;
        anchor_type: string;
        anchor_id: string;
        boundary: string;
      };
    }>;
    plan: PlanDoc | null;
    plan_hash: string | null;
    axis_status: {
      spatial_axis_id: string;
      camera_side: string;
      violating_keyframe_times_ms: number[];
    } | null;
  } | null;
}

interface PlanDoc {
  schema_version: number;
  spatial_world_id: string;
  camera: {
    projection: string;
    focal_length_um: number;
    sensor_width_um: number;
    sensor_height_um: number;
    keyframes: Array<{
      time_ms: number;
      transform: {
        translation_mm: [number, number, number];
        rotation_udeg: [number, number, number];
      };
    }>;
  };
  blocking: Array<{
    spatial_track_id: string;
    screen_direction: string;
    keyframes: Array<{
      time_ms: number;
      transform: {
        translation_mm: [number, number, number];
        rotation_udeg: [number, number, number];
      };
    }>;
  }>;
  axis_constraint: { spatial_axis_id: string; camera_side: string } | null;
}

async function api(path: string, method: string,
                   body?: unknown): Promise<unknown> {
  const res = await fetch(path, {
    method,
    headers: body ? { "Content-Type": "application/json" } : undefined,
    body: body ? JSON.stringify(body) : undefined,
  });
  if (!res.ok) {
    const err = await res.json().catch(() => null);
    throw new ApiError(
      err?.error_code ?? "SPATIAL_SHOT_PLAN_INVALID",
      err?.message ?? `${method} ${path} failed (${res.status})`,
      res.status,
      err?.details ?? {});
  }
  if (method === "PUT") return res.json();
  return null;
}

const num = (v: string) => Number.parseInt(v, 10) || 0;

export default function SpatialContinuityPanel({
  shotId,
}: {
  shotId: string;
}) {
  const [body, setBody] = useState<SpatialContinuityBody | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [conflict, setConflict] = useState<string | null>(null);
  const [planHash, setPlanHash] = useState<string | null>(null);
  const [worldId, setWorldId] = useState("");
  const [focal, setFocal] = useState("50000");
  const [cx, setCx] = useState("0");
  const [cy, setCy] = useState("0");
  const [cz, setCz] = useState("0");
  const [axisId, setAxisId] = useState("");
  const [side, setSide] = useState("positive");

  const load = useCallback(async () => {
    try {
      const res = await fetch(`/api/shots/${shotId}/spatial-continuity`);
      if (!res.ok) throw new Error(`load failed (${res.status})`);
      const b = (await res.json()) as SpatialContinuityBody;
      setBody(b);
      const sc = b.spatial_continuity;
      setPlanHash(sc?.plan_hash ?? null);
      setWorldId(sc?.plan?.spatial_world_id ?? sc?.selected_world
        ?.spatial_world_id ?? "");
      if (sc?.plan) {
        setFocal(String(sc.plan.camera.focal_length_um));
        const t = sc.plan.camera.keyframes[0].transform.translation_mm;
        setCx(String(t[0])); setCy(String(t[1])); setCz(String(t[2]));
        if (sc.plan.axis_constraint) {
          setAxisId(sc.plan.axis_constraint.spatial_axis_id);
          setSide(sc.plan.axis_constraint.camera_side);
        }
      }
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }, [shotId]);

  useEffect(() => {
    void load();
  }, [load]);

  async function act(fn: () => Promise<void>) {
    setBusy(true);
    setConflict(null);
    try {
      await fn();
      await load();
    } catch (e) {
      if (e instanceof ApiError &&
          e.code === "SPATIAL_SHOT_PLAN_CONFLICT") {
        setConflict("The plan changed on the server — refresh and " +
          "reconcile before saving again. Nothing was overwritten.");
      } else {
        setError(e instanceof Error ? e.message : String(e));
      }
    } finally {
      setBusy(false);
    }
  }

  if (error && !body) {
    return <ErrorBanner error={new ApiError(
      "SPATIAL_SHOT_PLAN_INVALID", error, 500)} />;
  }
  if (!body) return <div className="card">Loading spatial continuity…</div>;

  const sc = body.spatial_continuity;

  return (
    <div className="card">
      <h3>Current spatial continuity</h3>
      <div className="meta">
        Authoring/inspection projection — captured authority lives in
        ShotRevision history.
      </div>
      <div className="row">
        <span className={`badge ${body.ready ? "badge-matches"
          : "badge-error"}`}>
          {body.ready ? "ready" : "not ready"}
        </span>
        <span className="meta">hash:{" "}
          <code>{body.spatial_continuity_hash
            ? body.spatial_continuity_hash.slice(0, 16) + "…"
            : "—"}</code>
        </span>
      </div>

      {body.issues.length > 0 && (
        <ul>
          {body.issues.map((i, k) => (
            <li key={k} className="meta">
              <code>{i.code}</code> [{i.layer}] {i.message}
            </li>
          ))}
        </ul>
      )}

      {sc && (
        <>
          <h4>Approved reusable world</h4>
          <div className="meta">
            world <code>{sc.selected_world.spatial_world_id.slice(0, 8)}…</code>{" "}
            ({sc.selected_world.requirement}) · location revision{" "}
            <code>{sc.location_entity_revision_id?.slice(0, 8) ?? "—"}…</code>
            {sc.approved_world_revision && <> · approved revision #
              {sc.approved_world_revision.revision_number}{" "}
              <code>{sc.approved_world_revision.snapshot_hash
                .slice(0, 12)}…</code></>}
          </div>

          <h4>Current effective staging</h4>
          <table className="table">
            <thead>
              <tr><th>Entity</th><th>Rev</th><th>Req</th>
                <th>Transform (mm / µ°)</th><th>Source</th></tr>
            </thead>
            <tbody>
              {sc.staging.map((st) => (
                <tr key={st.spatial_track_id}>
                  <td><code>{st.entity_id.slice(0, 8)}…</code></td>
                  <td><code>{st.entity_revision_id.slice(0, 8)}…</code></td>
                  <td>{st.requirement}</td>
                  <td>{st.transform.translation_mm.join(" / ")} ·{" "}
                    {st.transform.rotation_udeg.join(" / ")}</td>
                  <td>{st.source_transition.anchor_type}/
                    {st.source_transition.boundary}</td>
                </tr>
              ))}
              {sc.staging.length === 0 && (
                <tr><td colSpan={5} className="meta">
                  No effective staged tracks.
                </td></tr>
              )}
            </tbody>
          </table>

          {sc.axis_status && (
            <div className="meta">
              axis <code>{sc.axis_status.spatial_axis_id.slice(0, 8)}…</code>{" "}
              ({sc.axis_status.camera_side} side):{" "}
              {sc.axis_status.violating_keyframe_times_ms.length === 0
                ? "all camera keyframes on the declared side"
                : `violating keyframes at ${
                  sc.axis_status.violating_keyframe_times_ms.join(", ")}`}
            </div>
          )}

          <h4>Working Shot spatial plan</h4>
          <div className="meta">
            current plan hash:{" "}
            <code>{sc.plan_hash ? sc.plan_hash.slice(0, 16) + "…" : "—"}</code>
          </div>
          {conflict && <div className="meta badge badge-error">{conflict}</div>}
          <div className="row">
            <input placeholder="world id" aria-label="plan world"
                   value={worldId}
                   onChange={(e) => setWorldId(e.target.value)} />
            <input placeholder="focal µm" aria-label="plan focal"
                   value={focal}
                   onChange={(e) => setFocal(e.target.value)} />
            <input placeholder="cam x" aria-label="plan cam x" value={cx}
                   onChange={(e) => setCx(e.target.value)} />
            <input placeholder="cam y" aria-label="plan cam y" value={cy}
                   onChange={(e) => setCy(e.target.value)} />
            <input placeholder="cam z" aria-label="plan cam z" value={cz}
                   onChange={(e) => setCz(e.target.value)} />
            <input placeholder="axis id (opt)" aria-label="plan axis"
                   value={axisId}
                   onChange={(e) => setAxisId(e.target.value)} />
            <select aria-label="plan axis side" value={side}
                    onChange={(e) => setSide(e.target.value)}>
              <option value="positive">positive</option>
              <option value="negative">negative</option>
            </select>
            <button
              disabled={busy || !worldId}
              onClick={() => void act(async () => {
                await api(`/api/shots/${shotId}/spatial-plan`, "PUT", {
                  expected_plan_hash: planHash,
                  plan: {
                    schema_version: 1,
                    spatial_world_id: worldId,
                    camera: {
                      projection: "perspective",
                      focal_length_um: num(focal),
                      sensor_width_um: 36000,
                      sensor_height_um: 20250,
                      keyframes: [{
                        time_ms: 0,
                        transform: {
                          translation_mm: [num(cx), num(cy), num(cz)],
                          rotation_udeg: [0, 0, 0],
                        },
                      }],
                    },
                    blocking: sc.plan?.blocking ?? [],
                    axis_constraint: axisId
                      ? { spatial_axis_id: axisId, camera_side: side }
                      : null,
                  },
                });
              })}>Save plan (CAS)</button>
            <button
              disabled={busy || planHash === null}
              onClick={() => void act(async () => {
                await api(`/api/shots/${shotId}/spatial-plan`, "DELETE", {
                  expected_plan_hash: planHash,
                });
              })}>Delete plan</button>
          </div>
          {sc.plan && (
            <table className="table">
              <thead>
                <tr><th>Blocking track</th><th>Direction</th>
                  <th>t0 transform</th></tr>
              </thead>
              <tbody>
                {sc.plan.blocking.map((b) => (
                  <tr key={b.spatial_track_id}>
                    <td><code>{b.spatial_track_id.slice(0, 8)}…</code></td>
                    <td>{b.screen_direction}</td>
                    <td>{b.keyframes[0].transform.translation_mm
                      .join(" / ")}</td>
                  </tr>
                ))}
                {sc.plan.blocking.length === 0 && (
                  <tr><td colSpan={3} className="meta">
                    No blocking entries.
                  </td></tr>
                )}
              </tbody>
            </table>
          )}
        </>
      )}
    </div>
  );
}
