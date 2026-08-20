/**
 * M7D §18.2.6 — historical continuity provenance per revision (pure
 * display, server-fed from the immutable-row reconstruction endpoint).
 * Never re-resolves current state; renders exactly what was captured.
 * Fail-closed historical errors (e.g. INTERNAL_INVARIANT_VIOLATION)
 * render VISIBLY as errors — never silently reclassified as absence.
 */

import { ApiError } from "@/lib/api.shared";
import type { RevisionContinuity, RevisionSummary } from "@/lib/types";

export default function RevisionProvenanceList({
  revisions,
  continuity,
  entityNames,
}: {
  revisions: RevisionSummary[];
  continuity: Record<string, RevisionContinuity | ApiError | null>;
  entityNames: Record<string, string>;
}) {
  if (revisions.length === 0) {
    return <div className="empty">No revisions captured yet.</div>;
  }
  return (
    <section>
      {revisions.map((r) => {
        const c = continuity[r.id];
        if (c && c instanceof ApiError) {
          return (
            <div className="card row" key={r.id}>
              <div>
                <strong>Revision {r.revision_number}</strong>
                <div className="empty">
                  Provenance failed to load — {c.code}: {c.message}. The
                  backend surfaced this integrity failure deliberately; it
                  is not hidden as absence.
                </div>
              </div>
            </div>
          );
        }
        return (
          <div className="card" key={r.id}>
            <div className="row">
              <div>
                <strong>Revision {r.revision_number}</strong>
                <span className="meta">
                  {" "}
                  · snapshot schema {c?.snapshot_schema_version ?? "?"} ·
                  continuity spec{" "}
                  {c?.continuity_schema_version
                    ? `v${c.continuity_schema_version}`
                    : "—"}
                </span>
                <div className="meta">
                  <span className="hash">{r.snapshot_hash.slice(0, 12)}…</span>
                  {r.continuity_spec_hash ? (
                    <>
                      {" "}
                      · spec{" "}
                      <span className="hash">
                        {r.continuity_spec_hash.slice(0, 12)}…
                      </span>
                    </>
                  ) : null}{" "}
                  · {r.created_at}
                </div>
              </div>
            </div>
            {c ? (
              <div>
                <div className="meta">
                  {c.dependencies.length} dependencies ·{" "}
                  {c.feature_states.length} feature states ·{" "}
                  {c.relations.length} relations ·{" "}
                  {c.source_transition_audit.length} source transitions
                </div>
                {c.relations.length > 0 ? (
                  <ul>
                    {c.relations.map((rel) => (
                      <li key={rel.relation_id} className="meta">
                        {entityNames[rel.subject_entity_id] ??
                          rel.subject_entity_id.slice(0, 8)}{" "}
                        — {rel.predicate_key} →{" "}
                        {entityNames[rel.object_entity_id] ??
                          rel.object_entity_id.slice(0, 8)}{" "}
                        (from {rel.source_anchor.anchor_type}/
                        {rel.source_anchor.boundary})
                      </li>
                    ))}
                  </ul>
                ) : null}
                {c.feature_states.length > 0 ? (
                  <ul>
                    {c.feature_states.map((s) => (
                      <li key={s.feature_id} className="meta">
                        {entityNames[s.entity_id] ?? s.entity_id.slice(0, 8)}{" "}
                        · {s.feature_key} = {String(s.value)}
                      </li>
                    ))}
                  </ul>
                ) : null}
              </div>
            ) : (
              <div className="meta">provenance unavailable</div>
            )}
          </div>
        );
      })}
    </section>
  );
}
