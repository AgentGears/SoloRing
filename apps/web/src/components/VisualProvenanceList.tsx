/**
 * M8 §73 — Historical visual provenance: "Visual References at Capture".
 *
 * Server component fed by the revision-continuity projection. Captured
 * authority (immutable) is displayed strictly separately from CURRENT
 * approved authority; current approval is never presented as historical
 * execution input. Captured Asset/Blob identity remains displayed even
 * if current state later diverges (retention per §40/§91).
 */

import type { ApiError } from "@/lib/api.shared";
import type { RevisionSummary } from "@/lib/types";
import type { RevisionContinuity } from "@/lib/types";

function short(id: string | null): string {
  return id ? `${id.slice(0, 8)}…` : "—";
}

export default function VisualProvenanceList({
  revisions,
  continuity,
}: {
  revisions: RevisionSummary[];
  continuity: Record<string, RevisionContinuity | ApiError | null>;
}) {
  const rows = revisions.map((r) => ({ r, c: continuity[r.id] }));
  const withVisual = rows.filter(
    (x) =>
      x.c && !(x.c instanceof Error) && "visual" in x.c && x.c.visual != null,
  );
  if (withVisual.length === 0) {
    return (
      <div className="empty">
        No schema-4 visual provenance in this Shot&apos;s history.
      </div>
    );
  }
  return (
    <div>
      {withVisual.map(({ r, c }) => {
        const visual = (c as RevisionContinuity).visual!;
        return (
          <div className="card" key={r.id}>
            <div className="meta">
              revision {r.revision_number} · pack{" "}
              {visual.visual_reference_pack_hash ? (
                <span className="hash">
                  {visual.visual_reference_pack_hash.slice(0, 12)}…
                </span>
              ) : (
                "— (empty at capture, honest NULL)"
              )}
            </div>
            {visual.anchors.length === 0 ? (
              <div className="meta">
                No approved visual authority applied at capture.
              </div>
            ) : (
              visual.anchors.map((a) => (
                <div className="card row" key={a.visual_anchor_id}>
                  <div>
                    <strong>
                      {a.entity_id ? "entity" : "feature"} / {a.facet_key}
                    </strong>
                    <div className="meta">
                      captured realization:{" "}
                      {a.entity_revision_id
                        ? `EntityRevision ${short(a.entity_revision_id)}`
                        : `value ${a.feature_value_json ?? ""}`}{" "}
                      · captured VisualAnchorRevision:{" "}
                      {a.captured_revision_number ?? short(
                        a.captured_visual_anchor_revision_id,
                      )}
                    </div>
                    <div className="meta">
                      current approved realization:{" "}
                      {a.current_approved_revision_number != null
                        ? `revision ${a.current_approved_revision_number}`
                        : "none (changed or unapproved since capture)"}
                    </div>
                    <div className="meta">
                      {a.items.length} captured reference
                      {a.items.length === 1 ? "" : "s"}
                      {a.items
                        .slice()
                        .sort((x, y) => x.role.localeCompare(y.role))
                        .map((it) => (
                          <span key={it.asset_id} className="meta">
                            {" · "}
                            {it.role}
                            {it.view_key ? ` (${it.view_key})` : ""}{" "}
                            <span className="hash">
                              {short(it.asset_id)}
                            </span>
                          </span>
                        ))}
                    </div>
                  </div>
                </div>
              ))
            )}
          </div>
        );
      })}
    </div>
  );
}
