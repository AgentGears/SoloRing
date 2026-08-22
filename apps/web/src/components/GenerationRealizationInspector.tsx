/**
 * M9 §36.3 — Historical Generation realization inspector (pure display).
 * Shows CAPTURED facts (profile/model/fingerprint hashes, per-channel
 * selected references with Asset + Blob identity, parameter overrides,
 * omissions). Historical captured values are authoritative; nothing here
 * consults current package/profile/M8 state (§74).
 */

import type { GenerationRealization } from "@/lib/realizationTypes";

function short(id: string | null): string {
  return id ? `${id.slice(0, 8)}…` : "—";
}

export default function GenerationRealizationInspector({
  generation,
}: {
  generation: GenerationRealization;
}) {
  const summary = generation.realization_summary;
  if (
    generation.workflow_spec_schema_version !== 2 ||
    summary === null
  ) {
    return (
      <div className="empty">
        No captured M9 realization (legacy workflow-spec schema 1).
      </div>
    );
  }
  return (
    <div>
      <div className="meta">
        captured profile {generation.realization_profile_id} v
        {generation.realization_profile_version}{" "}
        <span className="hash">
          {short(generation.realization_profile_hash)}
        </span>{" "}
        · model {generation.model} {generation.model_version} · fingerprint{" "}
        <span className="hash">
          {short(summary.execution_model_fingerprint_hash)}
        </span>{" "}
        · M8 pack{" "}
        <span className="hash">
          {short(generation.visual_reference_pack_hash)}
        </span>
      </div>
      {summary.channels.map((c) => (
        <div className="card" key={c.channel}>
          <strong>{c.channel}</strong>
          <div className="meta">input {c.input_key}</div>
          {c.bindings.map((b) => (
            <div className="meta" key={`${b.asset_id}-${b.facet_key}`}>
              {b.required ? "required" : "optional"} {b.facet_key} ·{" "}
              {b.role}
              {b.view_key ? ` (${b.view_key})` : ""} · asset{" "}
              <span className="hash">{short(b.asset_id)}</span> blob{" "}
              <span className="hash">{short(b.blob_hash)}</span>
            </div>
          ))}
        </div>
      ))}
      {summary.omitted_optional.length > 0 ? (
        <div className="meta">
          Omitted at capture:{" "}
          {summary.omitted_optional
            .map((o) => `${o.facet_key} (${o.reason})`)
            .join(", ")}
        </div>
      ) : null}
      {Object.keys(summary.parameter_overrides).length > 0 ? (
        <div className="meta">
          Profile parameter overrides:{" "}
          {Object.entries(summary.parameter_overrides)
            .map(([k, v]) => `${k}=${String(v)}`)
            .join(", ")}
        </div>
      ) : null}
    </div>
  );
}
