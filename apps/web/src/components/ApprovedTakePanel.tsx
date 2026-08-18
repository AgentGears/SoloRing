// Approved Canon panel (M2D §5, §8.3): honest states only.
//
//   approved_take_id = null  -> "No approved Take yet." (NOT "matches canon")
//   differs = false          -> matches canon
//   differs = true           -> working state differs from canon
//   differs = null           -> continuity state unresolved: NEITHER
//                               "matches" nor "differs" (M7B compatibility)
//
// Server-rendered; no client logic.

export default function ApprovedTakePanel({
  approvedTakeId,
  differs,
}: {
  approvedTakeId: string | null;
  differs: boolean | null;
}) {
  if (approvedTakeId === null) {
    return (
      <div className="card">
        <div className="empty-inline">No approved Take yet.</div>
        <div className="meta">
          Canon is established by approving a candidate Take; approval arrives
          with generation (M3).
        </div>
      </div>
    );
  }

  if (differs === null) {
    return (
      <div className="card">
        <div className="empty-inline">
          Continuity state unresolved — canon comparison unavailable.
        </div>
        <div className="meta">approved take {approvedTakeId}</div>
      </div>
    );
  }

  return (
    <div className="card">
      {differs ? (
        <div className="badge badge-differs">
          Working state differs from approved canon
        </div>
      ) : (
        <div className="badge badge-matches">Working state matches approved canon</div>
      )}
      <div className="meta">approved take {approvedTakeId}</div>
    </div>
  );
}
