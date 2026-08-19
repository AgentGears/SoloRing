/**
 * M7D §18.2.5 — current continuity state (pure display, server-fed).
 *
 * Unresolved state is represented honestly (APR-051): when the strict
 * endpoint raises, the error envelope's ordered issue set names the
 * missing endpoint; nothing is fabricated. When ready, the effective
 * Feature and Relation states render with their source anchors.
 */

import type {
  ContinuityStateResponse,
  ReadinessIssue,
} from "@/lib/types";

function entityLabel(
  id: string | undefined,
  names: Record<string, string>,
): string {
  if (!id) return "?";
  return names[id] ? `${names[id]} (${id.slice(0, 8)}…)` : `${id.slice(0, 8)}…`;
}

function IssueRow({
  issue,
  names,
}: {
  issue: ReadinessIssue;
  names: Record<string, string>;
}) {
  if (issue.error_code === "CONTINUITY_RELATION_ENDPOINT_REQUIRED") {
    return (
      <div className="card row">
        <div>
          <strong>Incomplete relation — missing dependency endpoint</strong>
          <div className="meta">
            {entityLabel(issue.subject_entity_id, names)} —
            {" "}{issue.predicate_key} →{" "}
            {entityLabel(issue.object_entity_id, names)}: endpoint{" "}
            {entityLabel(issue.missing_entity_id, names)} is not a semantic
            dependency of this Shot. Add the dependency or deactivate the
            relation; no hidden dependency is created for you.
          </div>
        </div>
      </div>
    );
  }
  if (issue.error_code === "NARRATIVE_CONTEXT_REQUIRED") {
    return (
      <div className="card row">
        <div>
          <strong>Narrative context required</strong>
          <div className="meta">
            The Shot is unassigned and has relevant narrative state — assign
            it to a scene before capturing or generating.
          </div>
        </div>
      </div>
    );
  }
  return (
    <div className="card row">
      <div>
        <strong>{issue.error_code}</strong>
      </div>
    </div>
  );
}

export default function ContinuityStatePanel({
  state,
  notReadyCode,
  notReadyIssues,
  loadError,
  entityNames,
}: {
  state: ContinuityStateResponse | null;
  /** Error-envelope code from the strict endpoint — ONLY the two semantic
   * not-ready conditions (classified by the caller); anything else is a
   * loadError and renders as an error, never as readiness. */
  notReadyCode: string | null;
  /** The FULL ordered issue set from the error envelope details. */
  notReadyIssues: ReadinessIssue[];
  /** Any non-semantic failure of the strict endpoint (500s, transport,
   * invariant violations) — rendered honestly as what it is. */
  loadError: { code: string; message: string } | null;
  entityNames: Record<string, string>;
}) {
  if (loadError) {
    return (
      <section>
        <div className="empty">
          Continuity state failed to load — {loadError.code}:{" "}
          {loadError.message} This is a load/integrity error, NOT a
          continuity-readiness condition.
        </div>
      </section>
    );
  }
  if (notReadyCode) {
    return (
      <section>
        <div className="empty">
          Continuity state not ready — {notReadyCode}. Capture and
          generation are blocked until this is resolved.
        </div>
        {notReadyIssues.map((issue, i) => (
          <IssueRow key={i} issue={issue} names={entityNames} />
        ))}
      </section>
    );
  }
  if (!state) {
    return (
      <section>
        <div className="empty">
          Continuity state unresolved — no authoritative resolution exists.
        </div>
      </section>
    );
  }
  return (
    <section>
      {state.feature_states.length === 0 &&
      state.relation_states.length === 0 ? (
        <div className="empty">
          Ready — no effective continuity state at this position.
        </div>
      ) : null}
      {state.feature_states.map((s) => (
        <div className="card row" key={s.feature_id}>
          <div>
            <strong>
              {entityLabel(s.entity_id, entityNames)} · {s.feature_key} ={" "}
              {String(s.value)}
              {s.unit ? ` ${s.unit}` : ""}
            </strong>
            <div className="meta">
              {s.feature_kind} ({s.value_type}) · from {s.source_anchor.anchor_type}
              /{s.source_anchor.boundary} ·{" "}
              <span className="hash">{s.source_anchor.anchor_id.slice(0, 8)}…</span>
            </div>
          </div>
        </div>
      ))}
      {state.relation_states.map((s) => (
        <div className="card row" key={s.relation_id}>
          <div>
            <strong>
              {entityLabel(s.subject_entity_id, entityNames)} —{" "}
              {s.predicate_key} →{" "}
              {entityLabel(s.object_entity_id, entityNames)}
            </strong>
            <div className="meta">
              active · from {s.source_anchor.anchor_type}/
              {s.source_anchor.boundary} ·{" "}
              <span className="hash">{s.source_anchor.anchor_id.slice(0, 8)}…</span>
            </div>
          </div>
        </div>
      ))}
    </section>
  );
}
