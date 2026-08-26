/**
 * M10D §47/§60 — captured spatial provenance block for the historical
 * ShotRevision view: renders EXACTLY what the immutable-row
 * reconstruction endpoint returned (never current state). Labeled
 * "Captured" — never "Current"; current comparison belongs to the
 * SpatialContinuityPanel.
 */

import { ApiError } from "@/lib/api.shared";

export interface CapturedSpatial {
  spatial_continuity_hash: string;
  world: {
    spatial_world_id: string;
    requirement: string;
    spatial_world_revision_id: string;
    spatial_world_revision_hash: string;
    location_entity_id: string;
    location_entity_revision_id: string;
  };
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
      spatial_transition_id: string;
      anchor_type: string;
      anchor_id: string;
      boundary: string;
    };
  }>;
  shot_plan: {
    camera: {
      focal_length_um: number;
      keyframes: Array<{
        time_ms: number;
        transform: { translation_mm: [number, number, number] };
      }>;
    };
    blocking: Array<{
      spatial_track_id: string;
      screen_direction: string;
    }>;
  };
}

export default function SpatialProvenanceBlock({
  spatial,
}: {
  spatial: CapturedSpatial | ApiError | null;
}) {
  if (spatial === null) {
    return (
      <div className="meta">
        No captured spatial authority in this revision.
      </div>
    );
  }
  if (spatial instanceof ApiError) {
    return (
      <div className="card row">
        <span className="badge badge-error">Captured spatial: ERROR</span>
        <span className="meta">{spatial.message}</span>
      </div>
    );
  }
  return (
    <div className="card">
      <div className="row">
        <strong>Captured spatial continuity</strong>
        <span className="meta">
          hash <code>{spatial.spatial_continuity_hash.slice(0, 16)}…</code>
        </span>
      </div>
      <div className="meta">
        Captured world revision{" "}
        <code>{spatial.world.spatial_world_revision_hash.slice(0, 12)}…</code>{" "}
        ({spatial.world.requirement}) — used by this captured revision.
      </div>
      <table className="table">
        <thead>
          <tr><th>Captured staging entity</th><th>Rev</th>
            <th>Transform</th><th>Source</th></tr>
        </thead>
        <tbody>
          {spatial.staging.map((st) => (
            <tr key={st.spatial_track_id}>
              <td><code>{st.entity_id.slice(0, 8)}…</code></td>
              <td><code>{st.entity_revision_id.slice(0, 8)}…</code></td>
              <td>{st.transform.translation_mm.join(" / ")}</td>
              <td>{st.source_transition.anchor_type}/
                {st.source_transition.boundary}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <div className="meta">
        Captured Shot plan: focal{" "}
        {spatial.shot_plan.camera.focal_length_um} µm,{" "}
        {spatial.shot_plan.camera.keyframes.length} camera keyframe(s),{" "}
        {spatial.shot_plan.blocking.length} blocking entr
        {spatial.shot_plan.blocking.length === 1 ? "y" : "ies"}.
      </div>
    </div>
  );
}
