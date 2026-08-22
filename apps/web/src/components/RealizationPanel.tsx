/**
 * M9 §36.1/§36.2 — Shot realization panel (pure display, server-fed).
 * Current inspection is NOT a reservation; the evaluated package hashes
 * make staleness inspectable. M8 readiness, M9 realization readiness,
 * and executor/runtime compatibility are separate concepts — never
 * collapsed. No M8 mutation controls exist here (§36.4).
 */

import type {
  RealizationReadiness,
  RealizationSelectedFacetRow,
} from "@/lib/realizationTypes";

function short(id: string | null): string {
  return id ? `${id.slice(0, 8)}…` : "—";
}

function FacetRow({ row }: { row: RealizationSelectedFacetRow }) {
  const requirementLabel =
    row.requirement === "required" ? "required" : "optional";
  return (
    <div className="card row">
      <div>
        <strong>
          {row.target_kind === "entity" ? "entity" : "feature"} /{" "}
          {row.facet_key}
        </strong>
        <div className="meta">
          {requirementLabel} ·{" "}
          {row.status === "selected"
            ? `→ ${row.channel} (${row.input_key})`
            : row.status === "required_blocked"
              ? `BLOCKED — ${row.issue_code}`
              : `omitted — ${row.reason}`}
        </div>
        {row.selected_items.map((it) => (
          <div className="meta" key={it.asset_id}>
            {it.role}
            {it.view_key ? ` (${it.view_key})` : ""} asset{" "}
            <span className="hash">{short(it.asset_id)}</span> blob{" "}
            <span className="hash">{short(it.blob_hash)}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

export default function RealizationPanel({
  state,
}: {
  state: RealizationReadiness | null;
}) {
  if (state === null) {
    return (
      <section>
        <div className="empty">
          Realization inspection unavailable — no authoritative evaluation
          exists.
        </div>
      </section>
    );
  }
  const m7 = state.issues.some((i) => i.layer === "m7");
  const m8 = state.issues.some((i) => i.layer === "m8");
  const m9 = state.issues.some((i) => i.layer === "m9");
  return (
    <section>
      <div className="meta">
        Current inspection — NOT reserved. Evaluated against package{" "}
        {state.package.workflow_id} v{state.package.workflow_version}:
        manifest <span className="hash">
          {short(state.package.manifest_hash)}
        </span>{" "}
        · profile{" "}
        <span className="hash">
          {short(state.package.realization_profile_hash)}
        </span>{" "}
        · fingerprint{" "}
        <span className="hash">
          {short(state.package.execution_model_fingerprint_hash)}
        </span>
      </div>

      {m7 || m8 ? (
        <div className="empty">
          {m7
            ? "Blocked by M7 semantic state — "
            : "Blocked by M8 visual continuity — "}
          {state.issues.map((i) => i.error_code).join(", ")}. Resolve the{" "}
          {m7 ? "semantic" : "visual"} readiness first; no partial
          realization evaluation is shown.
        </div>
      ) : null}

      {!m7 && !m8 && !state.ready ? (
        <div className="empty">
          NOT realizable with this package —{" "}
          {state.issues.map((i) => i.error_code).join(", ")}. Generation
          creation is blocked before queueing; M8 authority is not
          weakened to fit the model.
        </div>
      ) : null}

      {state.ready && state.facet_statuses.length === 0 ? (
        <div className="empty">
          Ready — no captured M8 authority applies; the legacy path
          executes without realization content.
        </div>
      ) : null}

      {state.facet_statuses.map((row) => (
        <FacetRow key={row.visual_facet_id} row={row} />
      ))}

      {state.channels.map((c) => (
        <div className="card row" key={c.channel}>
          <div>
            <strong>{c.channel}</strong>
            <div className="meta">
              input {c.input_key} · capacity {c.used_items}/{c.max_items}
              {c.min_items > 0 ? ` (min ${c.min_items})` : ""} ·{" "}
              {c.active ? "active" : "inactive"}
            </div>
          </div>
        </div>
      ))}

      {state.omitted_optional.length > 0 ? (
        <div className="meta">
          Omitted optional facets:{" "}
          {state.omitted_optional
            .map((o) => `${o.facet_key} (${o.reason})`)
            .join(", ")}
        </div>
      ) : null}

      {state.profile ? (
        <div className="meta">
          profile {state.profile.id} v{state.profile.version} · model{" "}
          {state.model?.id} {state.model?.version} · pack{" "}
          {state.visual_reference_pack_hash ? (
            <span className="hash">
              {short(state.visual_reference_pack_hash)}
            </span>
          ) : (
            "(none)"
          )}
        </div>
      ) : null}
    </section>
  );
}
