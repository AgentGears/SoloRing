/**
 * M10C §10.3-§10.4 — target-Shot staging inspector.
 *
 * Renders the SERVER-resolved current effective staging for this world
 * at an operator-chosen target Shot: exact EntityRevision, effective
 * transform, winning transition provenance, and honest absence states.
 * Labeled "Current effective staging" — never captured/history, because
 * schema-5 ShotRevision capture does not exist yet (M10D). The client
 * performs no ranking, winner selection, or revision choice.
 */

"use client";

import { useCallback, useEffect, useState } from "react";
import ErrorBanner from "@/components/ErrorBanner";
import { ApiError } from "@/lib/api.shared";

interface ShotOption {
  id: string;
  title: string | null;
  subject: string;
  scene_id: string | null;
}

interface StagingPreview {
  shot_id: string;
  spatial_world_id: string;
  assigned: boolean;
  relevant_transition_data: boolean;
  narrative_context_required: boolean;
  states: Array<{
    spatial_track_id: string;
    entity_id: string;
    entity_name: string | null;
    entity_revision_id: string;
    requirement: string;
    transform: {
      translation_mm: [number, number, number];
      rotation_udeg: [number, number, number];
    };
    source_transition_id: string;
    source_anchor_type: string;
    source_anchor_id: string;
    source_boundary: string;
  }>;
  absent: Array<{
    spatial_track_id: string;
    entity_id: string;
    entity_name: string | null;
    entity_revision_id: string;
    requirement: string;
    reason: string;
  }>;
}

export function StagingInspector({ worldId }: { worldId: string }) {
  const [shots, setShots] = useState<ShotOption[] | null>(null);
  const [shotId, setShotId] = useState("");
  const [preview, setPreview] = useState<StagingPreview | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const loadOptions = useCallback(async () => {
    try {
      const res = await fetch(`/api/spatial-worlds/${worldId}/workspace`);
      if (!res.ok) throw new Error(`workspace load failed (${res.status})`);
      const body = await res.json();
      setShots(body.narrative?.shots ?? []);
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }, [worldId]);

  useEffect(() => {
    void loadOptions();
  }, [loadOptions]);

  async function resolve() {
    setBusy(true);
    try {
      const res = await fetch(
        `/api/spatial-worlds/${worldId}/staging?shot_id=${shotId}`);
      if (!res.ok) {
        const err = await res.json().catch(() => null);
        throw new Error(err?.message ??
                        `staging preview failed (${res.status})`);
      }
      setPreview(await res.json());
      setError(null);
    } catch (e) {
      setPreview(null);
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  if (error && !preview) {
    return (
      <ErrorBanner
        error={new ApiError("SPATIAL_TRACK_INVALID", error, 500)} />
    );
  }
  if (!shots) return <div className="card">Loading shots…</div>;

  return (
    <div className="card">
      <h3>Current effective staging for this world</h3>
      <div className="meta">
        Authoring/inspection projection — not captured ShotRevision
        history.
      </div>
      <div className="row">
        <select aria-label="target shot" value={shotId}
                onChange={(e) => setShotId(e.target.value)}>
          <option value="">target shot…</option>
          {shots.map((s) => (
            <option key={s.id} value={s.id}>
              {(s.title ?? s.subject.slice(0, 32)) +
               (s.scene_id ? "" : " (unassigned)")}
            </option>
          ))}
        </select>
        <button disabled={busy || !shotId}
                onClick={() => void resolve()}>
          Resolve current staging
        </button>
      </div>

      {preview && (
        <>
          {preview.narrative_context_required && (
            <div className="meta">
              Narrative context required: this Shot has relevant temporal
              staging data but no narrative position.
            </div>
          )}
          <table className="table">
            <thead>
              <tr>
                <th>Entity</th><th>EntityRevision</th><th>Req</th>
                <th>Transform (mm / µ°)</th><th>Source</th>
              </tr>
            </thead>
            <tbody>
              {preview.states.map((s) => (
                <tr key={s.spatial_track_id}>
                  <td>{s.entity_name ?? s.entity_id.slice(0, 8)}</td>
                  <td>
                    <code>{s.entity_revision_id}</code>
                  </td>
                  <td>{s.requirement}</td>
                  <td>
                    {s.transform.translation_mm.join(" / ")} ·{" "}
                    {s.transform.rotation_udeg.join(" / ")}
                  </td>
                  <td>
                    {s.source_anchor_type}/{s.source_boundary}{" "}
                    transition <code>
                      {s.source_transition_id}
                    </code>
                  </td>
                </tr>
              ))}
              {preview.states.length === 0 && (
                <tr><td colSpan={5} className="meta">
                  No effective staged states at this Shot/start.
                </td></tr>
              )}
            </tbody>
          </table>

          {preview.absent.length > 0 && (
            <>
              <h4>Tracks without effective state</h4>
              <ul>
                {preview.absent.map((a) => (
                  <li key={a.spatial_track_id}>
                    <span className={
                      `badge ${a.requirement === "required"
                        ? "badge-error" : "badge-matches"}`}>
                      {a.requirement}
                    </span>{" "}
                    {a.entity_name ?? a.entity_id.slice(0, 8)} —{" "}
                    {a.requirement === "required"
                      ? "required track has no effective state"
                      : "optional track absent"}{" "}
                    ({a.reason})
                  </li>
                ))}
              </ul>
            </>
          )}
        </>
      )}
    </div>
  );
}
