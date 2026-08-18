// API DTOs mirroring the FastAPI response schemas (server is authoritative).

export interface Project {
  id: string;
  name: string;
  description: string | null;
  created_at: string;
  updated_at: string;
}

export interface ShotListItem {
  id: string;
  project_id: string;
  shot_number: number;
  title: string | null;
  subject: string;
  scene_id: string | null;
  scene_position: number | null;
  created_at: string;
  updated_at: string;
}

export interface ShotDetail extends ShotListItem {
  action: string | null;
  environment: string | null;
  framing: string | null;
  camera_motion: string | null;
  lens: string | null;
  mood: string | null;
  duration_ms: number | null;
  approved_take_id: string | null;
  working_snapshot_hash: string | null;
  working_state_differs_from_approved: boolean | null;
  semantic_dependencies: SemanticDependency[];
  continuity_ready: boolean;
  continuity_state_ready: boolean;
}

export interface ReferenceItem {
  asset_id: string;
  role: string;
  position: number;
  created_at: string;
}

export interface RevisionSummary {
  id: string;
  shot_id: string;
  revision_number: number;
  snapshot_hash: string;
  continuity_spec_hash: string | null;
  created_at: string;
}

export interface SemanticDependency {
  entity_id: string;
  entity_kind: string;
  entity_name?: string | null;
  role: string;
  position: number;
  resolved_revision_id: string;
  resolved_revision_number: number;
  resolved_revision_hash: string;
}

export interface GenerationInfo {
  id: string;
  shot_id: string;
  generation_number: number;
  status: string;
  executor: string;
  compiled_prompt: string;
  progress_current: number | null;
  progress_total: number | null;
  error_code: string | null;
  error_message: string | null;
}

export interface TakeItem {
  id: string;
  shot_id: string;
  generation_id: string;
  output_key: string;
  rejected_at: string | null;
  created_at: string;
  is_approved: boolean;
  asset_id: string | null;
  blob_hash: string | null;
  detected_media_type: string | null;
  /** Captured logical output kind (provenance-backed), distinct from detected bytes. */
  output_kind: string | null;
  blob_url: string | null;
}

export interface Asset {
  id: string;
  project_id: string;
  take_id: string | null;
  kind: string;
  blob_hash: string;
  detected_media_type: string | null;
  upload_mime_type: string | null;
  original_filename: string | null;
  width: number | null;
  height: number | null;
  duration_ms: number | null;
  fps: number | null;
  created_at: string;
  /** Backend-canonical /blobs/... — map with toBlobUrl() in the browser. */
  blob_url: string;
}

// --- Story World (M6A) ---------------------------------------------------------

export interface Entity {
  id: string;
  project_id: string;
  kind: string;
  name: string;
  description: string | null;
  created_at: string;
  updated_at: string;
  approved_revision_id: string | null;
}

export interface EntityRevisionSummary {
  id: string;
  entity_id: string;
  revision_number: number;
  schema_version: number;
  spec_hash: string;
  created_at: string;
}

export interface EntityRevisionDetail extends EntityRevisionSummary {
  entity_kind: string;
  entity_name: string;
  spec_json: string;
}

// --- Narrative structure (M6B) ---------------------------------------------------

export interface Sequence {
  id: string;
  project_id: string;
  title: string | null;
  position: number;
  created_at: string;
  updated_at: string;
}

export interface Scene {
  id: string;
  sequence_id: string;
  title: string | null;
  description: string | null;
  position: number;
  created_at: string;
  updated_at: string;
}
