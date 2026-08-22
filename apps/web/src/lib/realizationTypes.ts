// M9 Realization API DTOs (frozen plan §34–35; server authoritative).

export interface RealizationIssue {
  error_code: string;
  message?: string;
  layer?: string;
  [k: string]: unknown;
}

export interface RealizationSelectedFacetRow {
  visual_facet_id: string;
  target_kind: string;
  facet_key: string;
  requirement: string;
  status: "selected" | "required_blocked" | "optional_omitted";
  channel: string | null;
  input_key: string | null;
  selected_items: {
    asset_id: string;
    blob_hash: string;
    role: string;
    view_key: string | null;
    source_position: number;
    binding_position: number;
  }[];
  reason: string | null;
  issue_code: string | null;
}

export interface RealizationChannelRow {
  channel: string;
  input_key: string;
  min_items: number;
  max_items: number;
  used_items: number;
  active: boolean;
}

export interface EnvironmentStatus {
  attestation: string;
  attestation_detail?: string;
  runtime_compatible: boolean;
  model_roots_configured: Record<string, boolean>;
  note: string;
}

export interface RealizationReadiness {
  shot_id: string;
  ready: boolean;
  package: {
    schema_version: number;
    workflow_id: string;
    workflow_version: number;
    manifest_hash: string;
    workflow_template_hash: string;
    realization_profile_hash: string | null;
    execution_model_fingerprint_hash: string | null;
  };
  model: { id: string; version: string } | null;
  profile: { id: string; version: number; hash: string } | null;
  visual_reference_pack_hash: string | null;
  issues: RealizationIssue[];
  channels: RealizationChannelRow[];
  facet_statuses: RealizationSelectedFacetRow[];
  omitted_optional: {
    visual_facet_id: string;
    target_kind: string;
    facet_key: string;
    reason: string;
  }[];
  environment?: EnvironmentStatus | null;
}

export interface RealizationSummaryBinding {
  facet_key: string;
  required: boolean;
  asset_id: string;
  blob_hash: string;
  role: string;
  view_key: string | null;
}

export interface GenerationRealization {
  workflow_spec_schema_version: number | null;
  model: string | null;
  model_version: string | null;
  realization_profile_id: string | null;
  realization_profile_version: number | null;
  realization_profile_hash: string | null;
  visual_reference_pack_hash: string | null;
  manifest_hash: string | null;
  workflow_template_hash: string | null;
  realization_summary: {
    channels: {
      channel: string;
      input_key: string;
      bindings: RealizationSummaryBinding[];
    }[];
    omitted_optional: {
      facet_key: string;
      reason: string;
    }[];
    parameter_overrides: Record<string, unknown>;
    execution_model_fingerprint_hash: string | null;
  } | null;
}
