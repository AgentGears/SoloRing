/**
 * M9 §36.3 — Historical Generation realization inspector (pure display).
 * Shows CAPTURED facts (manifest/template/profile/model/fingerprint
 * identities, per-channel selected references with Asset + Blob
 * identity, parameter overrides, omissions). The CURRENT
 * package/profile/model status block is informational only and may be
 * unavailable (§74): captured values are never relabeled from it.
 */

import type {
  EnvironmentStatus,
  GenerationRealization,
} from "@/lib/realizationTypes";

function short(id: string | null): string {
  return id ? `${id.slice(0, 8)}…` : "—";
}

export default function GenerationRealizationInspector({
  generation,
  currentEnvironment = null,
}: {
  generation: GenerationRealization;
  currentEnvironment?: EnvironmentStatus | null;
}) {
  const summary = generation.realization_summary;
  if (generation.workflow_spec_schema_version !== 2 || summary === null) {
    return (
      <div className="empty">
        No captured M9 realization (legacy workflow-spec schema 1).
      </div>
    );
  }
  return (
    <div>
      <div className="meta">
        captured manifest <span className="hash">
          {short(generation.manifest_hash)}
        </span>{" "}
        · template <span className="hash">
          {short(generation.workflow_template_hash)}
        </span>{" "}
        · profile {generation.realization_profile_id} v
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
      <CurrentEnvironmentStatus environment={currentEnvironment} />
    </div>
  );
}

function CurrentEnvironmentStatus({
  environment,
}: {
  environment: EnvironmentStatus | null;
}) {
  if (environment === null) {
    return (
      <div className="meta">
        Current environment status: unavailable (informational only; the
        captured values above remain authoritative for this Generation).
      </div>
    );
  }
  const roots = Object.entries(environment.model_roots_configured)
    .map(([k, v]) => `${k}:${v ? "configured" : "unset"}`)
    .join(", ");
  return (
    <div className="meta">
      Current environment (informational, NOT what this Generation
      used): attestation {environment.attestation}
      {environment.attestation_detail
        ? ` — ${environment.attestation_detail}`
        : ""}{" "}
      · runtime {environment.runtime_compatible ? "compatible" : "incompatible"}{" "}
      · model roots {roots}. {environment.note}
    </div>
  );
}
