/**
 * M8 §72 — Shot Visual Continuity inspector (pure display, server-fed).
 * Honest unresolved rendering per APR-051: no fabricated pack hash.
 * Each row exposes the stable facet, semantic target, approved
 * realization + revision, primary Asset, reference count, and blocking
 * issue. No model/executor terminology (§72).
 */

import type { VisualContinuityState } from "@/lib/visualTypes";

function short(id: string | null): string {
  return id ? `${id.slice(0, 8)}…` : "—";
}

export default function VisualContinuityPanel({
  state,
  entityNames = {},
}: {
  state: VisualContinuityState | null;
  entityNames?: Record<string, string>;
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
                {entityNames[s.entity_id ?? ""]
                  ? `${entityNames[s.entity_id ?? ""]} / `
                  : `${s.target_kind} / `}
                {s.facet_key}
              </strong>
              <div className="meta">
                {s.requirement} ·{" "}
                {s.resolved === "missing"
                  ? "missing realization"
                  : s.resolved === "unapproved"
                    ? "realization not approved"
                    : s.resolved}
                {s.issue ? ` · ${s.issue.error_code}` : ""}
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
              {entityNames[s.entity_id ?? ""]
                ? `${entityNames[s.entity_id ?? ""]} / `
                : `${s.target_kind} / `}
              {s.facet_key}
            </strong>
            <div className="meta">
              {s.resolved === "approved"
                ? `✓ approved (${short(s.approved_revision_id)}) · primary ${short(s.primary_asset_id)} · ${s.item_count} reference${s.item_count === 1 ? "" : "s"}`
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
