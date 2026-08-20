/**
 * M8 §72 — Shot Visual Continuity inspector (pure display, server-fed).
 * Honest unresolved rendering per APR-051: no fabricated pack hash.
 */

import type { VisualContinuityState } from "@/lib/visualTypes";

export default function VisualContinuityPanel({
  state,
}: {
  state: VisualContinuityState | null;
}) {
  if (state === null) {
    return (
      <section>
        <div className="empty">
          Visual continuity unresolved — no authoritative resolution
          exists.
        </div>
      </section>
    );
  }
  if (!state.continuity_state_ready) {
    return (
      <section>
        <div className="empty">
          Visual continuity blocked by semantic state —{" "}
          {state.visual_continuity_issues.map((i) => i.error_code).join(", ")}
          . Resolve semantic readiness first; no partial visual resolution
          is shown.
        </div>
      </section>
    );
  }
  if (!state.visual_continuity_ready) {
    return (
      <section>
        <div className="empty">
          Visual continuity NOT ready —{" "}
          {state.visual_continuity_issues.map((i) => i.error_code).join(", ")}
          . Capture and generation are blocked until the required
          realizations exist and are approved.
        </div>
        {state.facet_statuses.map((s) => (
          <div className="card row" key={s.visual_facet_id}>
            <div>
              <strong>
                {s.target_kind === "entity" ? "entity" : "feature"} /{" "}
                {s.facet_key}
              </strong>
              <div className="meta">
                {s.requirement} ·{" "}
                {s.resolved === "missing"
                  ? "missing realization"
                  : s.resolved === "unapproved"
                    ? "realization not approved"
                    : s.resolved}
              </div>
            </div>
          </div>
        ))}
      </section>
    );
  }
  return (
    <section>
      {state.facet_statuses.length === 0 ? (
        <div className="empty">
          Ready — no visual facets apply to this Shot.
        </div>
      ) : null}
      {state.facet_statuses.map((s) => (
        <div className="card row" key={s.visual_facet_id}>
          <div>
            <strong>
              {s.target_kind === "entity" ? "entity" : "feature"} /{" "}
              {s.facet_key}
            </strong>
            <div className="meta">
              {s.resolved === "approved"
                ? `✓ approved (${s.approved_revision_id?.slice(0, 8)}…)`
                : s.resolved === "not_applicable"
                  ? "— not applicable"
                  : s.resolved === "missing"
                    ? "missing realization (optional)"
                    : "not approved (optional)"}
            </div>
          </div>
        </div>
      ))}
      {state.visual_reference_pack_hash ? (
        <div className="meta">
          pack <span className="hash">
            {state.visual_reference_pack_hash.slice(0, 12)}…
          </span>
        </div>
      ) : (
        <div className="meta">
          Ready — no approved visual authority applies (empty pack, honest
          NULL hash).
        </div>
      )}
    </section>
  );
}
