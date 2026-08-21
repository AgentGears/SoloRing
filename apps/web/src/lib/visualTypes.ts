// M8 Visual Identity API DTOs (frozen plan §67; server authoritative).

export interface VisualFacet {
  id: string;
  project_id: string;
  target_kind: "entity" | "feature";
  entity_id: string | null;
  feature_id: string | null;
  facet_key: string;
  label: string | null;
  description: string | null;
  requirement: "required" | "optional";
  created_at: string;
  updated_at: string;
}

export interface ValuePolicy {
  feature_value_json: string;
  feature_value_hash: string;
  policy: "required" | "optional" | "not_applicable";
}

export interface VisualAnchor {
  id: string;
  visual_facet_id: string;
  entity_revision_id: string | null;
  feature_value_hash: string | null;
  feature_value_json: string | null;
  visual_context_entity_revision_id: string | null;
  approved_revision_id: string | null;
  created_at: string;
  updated_at: string;
}

export interface WorkingItem {
  asset_id: string;
  role: "primary" | "supporting" | "detail" | "context";
  view_key: string | null;
  position: number;
}

export interface VisualAnchorDetail extends VisualAnchor {
  items: WorkingItem[];
  working_snapshot_hash: string | null;
  approved_snapshot_hash: string | null;
  working_state_differs_from_approved: boolean | null;
}

export interface VisualAnchorRevisionSummary {
  id: string;
  visual_anchor_id: string;
  revision_number: number;
  snapshot_hash: string;
  created_at: string;
}

export interface FacetStatus {
  visual_facet_id: string;
  facet_key: string;
  target_kind: "entity" | "feature";
  entity_id: string | null;
  feature_id: string | null;
  requirement: string;
  resolved: "approved" | "missing" | "unapproved" | "not_applicable";
  visual_anchor_id: string | null;
  approved_revision_id: string | null;
  /** §72 row payload: primary Asset and reference count of the
   * approved realization (null/0 when not approved). */
  primary_asset_id: string | null;
  item_count: number;
  issue: { error_code: string; [k: string]: unknown } | null;
}

export interface VisualContinuityState {
  shot_id: string;
  continuity_state_ready: boolean;
  visual_continuity_ready: boolean;
  visual_reference_pack_hash: string | null;
  visual_continuity_issues: { error_code: string }[];
  facet_statuses: FacetStatus[];
}

// --- §73 historical visual provenance (server-fed, immutable) ---------------------

export interface CapturedVisualItem {
  asset_id: string;
  blob_hash: string;
  role: string;
  view_key: string | null;
  position: number;
}

export interface CapturedVisualAnchor {
  position: number;
  visual_facet_id: string;
  facet_key: string;
  visual_anchor_id: string;
  captured_visual_anchor_revision_id: string;
  captured_revision_number: number | null;
  captured_snapshot_hash: string;
  /** Current authority, clearly distinct from the captured authority. */
  current_approved_revision_id: string | null;
  current_approved_revision_number: number | null;
  target_kind: string;
  entity_id: string | null;
  entity_revision_id: string | null;
  feature_id: string | null;
  feature_value_hash: string | null;
  feature_value_json: string | null;
  visual_context_entity_revision_id: string | null;
  items: CapturedVisualItem[];
}

export interface VisualProvenance {
  visual_reference_pack_hash: string | null;
  anchors: CapturedVisualAnchor[];
}
