// Revision History (M2D §5): summary rows, deliberate empty state.
// Revisions are captured lazily at generation time; until M3A runs, an empty
// list is the honest state — not a loading or error condition.

import type { RevisionSummary } from "@/lib/types";

export default function RevisionList({
  revisions,
}: {
  revisions: RevisionSummary[];
}) {
  if (revisions.length === 0) {
    return (
      <div className="empty">
        No revisions captured yet. Revisions are created when a Generation
        freezes the working state (M3).
      </div>
    );
  }

  return (
    <div>
      {revisions.map((r) => (
        <div className="card row" key={r.id}>
          <div>
            <strong>Revision {r.revision_number}</strong>
            <div className="hash">{r.snapshot_hash}</div>
            {r.continuity_spec_hash ? (
              <div className="meta">
                continuity:{" "}
                <span className="hash">{r.continuity_spec_hash}</span>
              </div>
            ) : null}
          </div>
          <div className="meta">{r.created_at}</div>
        </div>
      ))}
    </div>
  );
}
