"use client";

// Browser-only client: relative /api calls through the Next.js rewrite, plus
// the single canonical Blob-URL mapping boundary (M2 §3.3.3).

import { ApiError, fetchJson, fetchVoid } from "./api.shared";
import type {
  Asset,
  ContinuityFeature,
  ContinuityFeatureTransition,
  ContinuityPredicate,
  ContinuityRelation,
  Entity,
  EntityRevisionSummary,
  GenerationInfo,
  Project,
  ReferenceItem,
  RelationTransition,
  Scene,
  Sequence,
  ShotDetail,
  ShotListItem,
  TakeItem,
} from "./types";

const BASE = "/api";

/**
 * The ONLY place backend-canonical Blob URLs become browser URLs. Accepts the
 * exact canonical form /blobs/<2 hex>/<2 hex>/<64 lowercase hex> with shards
 * matching the hash prefix; rejects absolute, malformed, or traversal input.
 */
const BLOB_URL = /^\/blobs\/([0-9a-f]{2})\/([0-9a-f]{2})\/([0-9a-f]{64})$/;

export function toBlobUrl(canonical: string): string {
  const match = BLOB_URL.exec(canonical);
  if (
    !match ||
    match[1] !== match[3].slice(0, 2) ||
    match[2] !== match[3].slice(2, 4)
  ) {
    throw new ApiError(
      "NON_CANONICAL_BLOB_URL",
      "Refusing non-canonical blob URL.",
      0,
    );
  }
  return `/api${canonical}`;
}

export async function listProjects(): Promise<Project[]> {
  return fetchJson<Project[]>(`${BASE}/projects`);
}

export async function createProject(
  name: string,
  description: string | null,
): Promise<Project> {
  return fetchJson<Project>(`${BASE}/projects`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ name, description }),
  });
}

export async function deleteProject(id: string): Promise<void> {
  await fetchVoid(`${BASE}/projects/${id}`, { method: "DELETE" });
}

export async function listShots(projectId: string): Promise<ShotListItem[]> {
  return fetchJson<ShotListItem[]>(`${BASE}/projects/${projectId}/shots`);
}

export async function createShot(
  projectId: string,
  subject: string,
): Promise<ShotListItem> {
  return fetchJson<ShotListItem>(`${BASE}/projects/${projectId}/shots`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ subject }),
  });
}

export async function deleteShot(id: string): Promise<void> {
  await fetchVoid(`${BASE}/shots/${id}`, { method: "DELETE" });
}

export async function getShot(id: string): Promise<ShotDetail> {
  return fetchJson<ShotDetail>(`${BASE}/shots/${id}`);
}

/** PATCH intent fields; the server response is the normalized truth. */
export async function patchShot(
  id: string,
  fields: Record<string, string | number | null>,
): Promise<ShotDetail> {
  return fetchJson<ShotDetail>(`${BASE}/shots/${id}`, {
    method: "PATCH",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(fields),
  });
}

export async function getReferences(shotId: string): Promise<ReferenceItem[]> {
  return fetchJson<ReferenceItem[]>(`${BASE}/shots/${shotId}/references`);
}

/** Full-set replacement; the returned normalized set is the new truth. */
export async function replaceReferences(
  shotId: string,
  references: { asset_id: string; role: string }[],
): Promise<ReferenceItem[]> {
  return fetchJson<ReferenceItem[]>(`${BASE}/shots/${shotId}/references`, {
    method: "PUT",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ references }),
  });
}

// --- M3A: generation + canon mutations ---------------------------------------

export async function createGeneration(shotId: string): Promise<GenerationInfo> {
  return fetchJson<GenerationInfo>(`${BASE}/shots/${shotId}/generations`, {
    method: "POST",
  });
}

export async function listTakes(shotId: string): Promise<TakeItem[]> {
  return fetchJson<TakeItem[]>(`${BASE}/shots/${shotId}/takes`);
}

export async function approveTake(takeId: string): Promise<{ shot_id: string }> {
  return fetchJson<{ shot_id: string }>(`${BASE}/takes/${takeId}/approve`, {
    method: "POST",
  });
}

export async function rejectTake(
  takeId: string,
): Promise<{ shot_id: string; approved_take_id: string | null }> {
  return fetchJson<{ shot_id: string; approved_take_id: string | null }>(
    `${BASE}/takes/${takeId}/reject`,
    { method: "POST" },
  );
}

export async function listAssets(projectId: string): Promise<Asset[]> {
  return fetchJson<Asset[]>(`${BASE}/projects/${projectId}/assets`);
}

export async function uploadAsset(
  projectId: string,
  file: File,
): Promise<Asset> {
  const form = new FormData();
  form.append("file", file);
  return fetchJson<Asset>(`${BASE}/projects/${projectId}/assets`, {
    method: "POST",
    body: form,
  });
}

// --- Story World (M6A) ---------------------------------------------------------

export async function createEntity(
  projectId: string,
  kind: string,
  name: string,
  description: string | null,
): Promise<Entity> {
  return fetchJson<Entity>(`${BASE}/projects/${projectId}/entities`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ kind, name, description }),
  });
}

export async function patchEntity(
  id: string,
  fields: { name?: string; description?: string | null },
): Promise<Entity> {
  return fetchJson<Entity>(`${BASE}/entities/${id}`, {
    method: "PATCH",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(fields),
  });
}

export async function createEntityRevision(
  entityId: string,
  spec: Record<string, unknown>,
): Promise<EntityRevisionSummary> {
  return fetchJson<EntityRevisionSummary>(
    `${BASE}/entities/${entityId}/revisions`,
    {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ spec }),
    },
  );
}

export async function approveEntityRevision(
  entityId: string,
  revisionId: string,
  expectedApprovedRevisionId: string | null,
): Promise<void> {
  await fetchVoid(`${BASE}/entities/${entityId}/approved-revision`, {
    method: "PUT",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({
      revision_id: revisionId,
      expected_approved_revision_id: expectedApprovedRevisionId,
    }),
  });
}

// --- Narrative (M6B) ------------------------------------------------------------

export async function createSequence(
  projectId: string,
  title: string | null,
): Promise<Sequence> {
  return fetchJson<Sequence>(`${BASE}/projects/${projectId}/sequences`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ title }),
  });
}

export async function patchSequence(
  id: string,
  title: string | null,
): Promise<void> {
  await fetchVoid(`${BASE}/sequences/${id}`, {
    method: "PATCH",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ title }),
  });
}

export async function deleteSequence(id: string): Promise<void> {
  await fetchVoid(`${BASE}/sequences/${id}`, { method: "DELETE" });
}

export async function reorderSequences(
  projectId: string,
  sequenceIds: string[],
): Promise<void> {
  await fetchVoid(`${BASE}/projects/${projectId}/sequences/order`, {
    method: "PUT",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ sequence_ids: sequenceIds }),
  });
}

export async function createScene(
  sequenceId: string,
  title: string | null,
): Promise<Scene> {
  return fetchJson<Scene>(`${BASE}/sequences/${sequenceId}/scenes`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ title }),
  });
}

export async function patchScene(
  id: string,
  title: string | null,
): Promise<void> {
  await fetchVoid(`${BASE}/scenes/${id}`, {
    method: "PATCH",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ title }),
  });
}

export async function deleteScene(id: string): Promise<void> {
  await fetchVoid(`${BASE}/scenes/${id}`, { method: "DELETE" });
}

export async function reorderScenes(
  sequenceId: string,
  sceneIds: string[],
): Promise<void> {
  await fetchVoid(`${BASE}/sequences/${sequenceId}/scenes/order`, {
    method: "PUT",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ scene_ids: sceneIds }),
  });
}

export async function putSceneShots(
  sceneId: string,
  shotIds: string[],
): Promise<void> {
  await fetchVoid(`${BASE}/scenes/${sceneId}/shots`, {
    method: "PUT",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ shot_ids: shotIds }),
  });
}

// --- Semantic dependencies (M6C) --------------------------------------------------

export async function putSemanticDependencies(
  shotId: string,
  dependencies: { entity_id: string; role: string }[],
): Promise<void> {
  await fetchVoid(`${BASE}/shots/${shotId}/semantic-dependencies`, {
    method: "PUT",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ dependencies }),
  });
}


// --- Continuity state (M7/M7D) ------------------------------------------------------

export async function listContinuityFeatures(
  entityId: string,
): Promise<ContinuityFeature[]> {
  return fetchJson<ContinuityFeature[]>(
    `${BASE}/entities/${entityId}/continuity-features`,
  );
}

export async function createContinuityFeature(
  entityId: string,
  payload: {
    key: string;
    kind: string;
    value_type: string;
    name: string;
    description?: string | null;
    enum_values?: string[] | null;
    unit?: string | null;
    supersedes_feature_id?: string | null;
  },
): Promise<ContinuityFeature> {
  return fetchJson<ContinuityFeature>(
    `${BASE}/entities/${entityId}/continuity-features`,
    {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify(payload),
    },
  );
}

export async function patchContinuityFeature(
  featureId: string,
  fields: { name?: string; description?: string | null },
): Promise<ContinuityFeature> {
  return fetchJson<ContinuityFeature>(
    `${BASE}/continuity-features/${featureId}`,
    {
      method: "PATCH",
      headers: { "content-type": "application/json" },
      body: JSON.stringify(fields),
    },
  );
}

export async function deleteContinuityFeature(
  featureId: string,
): Promise<void> {
  await fetchVoid(`${BASE}/continuity-features/${featureId}`, {
    method: "DELETE",
  });
}

export async function listFeatureTransitions(
  featureId: string,
): Promise<ContinuityFeatureTransition[]> {
  return fetchJson<ContinuityFeatureTransition[]>(
    `${BASE}/continuity-features/${featureId}/transitions`,
  );
}

export async function createFeatureTransition(
  featureId: string,
  payload: {
    anchor_type: string;
    anchor_id: string;
    boundary: string;
    operation: string;
    value?: unknown;
  },
): Promise<ContinuityFeatureTransition> {
  return fetchJson<ContinuityFeatureTransition>(
    `${BASE}/continuity-features/${featureId}/transitions`,
    {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify(payload),
    },
  );
}

export async function patchFeatureTransition(
  transitionId: string,
  fields: Partial<{
    anchor_type: string;
    anchor_id: string;
    boundary: string;
    operation: string;
    value: unknown;
  }>,
): Promise<ContinuityFeatureTransition> {
  return fetchJson<ContinuityFeatureTransition>(
    `${BASE}/continuity-feature-transitions/${transitionId}`,
    {
      method: "PATCH",
      headers: { "content-type": "application/json" },
      body: JSON.stringify(fields),
    },
  );
}

export async function deleteFeatureTransition(
  transitionId: string,
): Promise<void> {
  await fetchVoid(`${BASE}/continuity-feature-transitions/${transitionId}`, {
    method: "DELETE",
  });
}

export async function listPredicates(
  projectId: string,
): Promise<ContinuityPredicate[]> {
  return fetchJson<ContinuityPredicate[]>(
    `${BASE}/projects/${projectId}/continuity-predicates`,
  );
}

export async function createPredicate(
  projectId: string,
  key: string,
  name: string,
  description: string | null,
): Promise<ContinuityPredicate> {
  return fetchJson<ContinuityPredicate>(
    `${BASE}/projects/${projectId}/continuity-predicates`,
    {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ key, name, description }),
    },
  );
}

export async function patchPredicate(
  predicateId: string,
  fields: { name?: string; description?: string | null },
): Promise<ContinuityPredicate> {
  return fetchJson<ContinuityPredicate>(
    `${BASE}/continuity-predicates/${predicateId}`,
    {
      method: "PATCH",
      headers: { "content-type": "application/json" },
      body: JSON.stringify(fields),
    },
  );
}

export async function deletePredicate(predicateId: string): Promise<void> {
  await fetchVoid(`${BASE}/continuity-predicates/${predicateId}`, {
    method: "DELETE",
  });
}

export async function listRelations(
  projectId: string,
): Promise<ContinuityRelation[]> {
  return fetchJson<ContinuityRelation[]>(
    `${BASE}/projects/${projectId}/continuity-relations`,
  );
}

export async function createRelation(
  projectId: string,
  subjectEntityId: string,
  predicateId: string,
  objectEntityId: string,
): Promise<ContinuityRelation> {
  return fetchJson<ContinuityRelation>(
    `${BASE}/projects/${projectId}/continuity-relations`,
    {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({
        subject_entity_id: subjectEntityId,
        predicate_id: predicateId,
        object_entity_id: objectEntityId,
      }),
    },
  );
}

export async function deleteRelation(relationId: string): Promise<void> {
  await fetchVoid(`${BASE}/continuity-relations/${relationId}`, {
    method: "DELETE",
  });
}

export async function listRelationTransitions(
  relationId: string,
): Promise<RelationTransition[]> {
  return fetchJson<RelationTransition[]>(
    `${BASE}/continuity-relations/${relationId}/transitions`,
  );
}

export async function createRelationTransition(
  relationId: string,
  payload: {
    anchor_type: string;
    anchor_id: string;
    boundary: string;
    state: string;
  },
): Promise<RelationTransition> {
  return fetchJson<RelationTransition>(
    `${BASE}/continuity-relations/${relationId}/transitions`,
    {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify(payload),
    },
  );
}

export async function patchRelationTransition(
  transitionId: string,
  fields: Partial<{
    anchor_type: string;
    anchor_id: string;
    boundary: string;
    state: string;
  }>,
): Promise<RelationTransition> {
  return fetchJson<RelationTransition>(
    `${BASE}/continuity-relation-transitions/${transitionId}`,
    {
      method: "PATCH",
      headers: { "content-type": "application/json" },
      body: JSON.stringify(fields),
    },
  );
}

export async function deleteRelationTransition(
  transitionId: string,
): Promise<void> {
  await fetchVoid(`${BASE}/continuity-relation-transitions/${transitionId}`, {
    method: "DELETE",
  });
}


// --- Visual Identity (M8) ---------------------------------------------------------

import type {
  ValuePolicy,
  VisualAnchorDetail,
  VisualAnchorRevisionSummary,
  VisualContinuityState,
  VisualFacet,
} from "./visualTypes";

export async function listVisualFacets(
  projectId: string,
): Promise<VisualFacet[]> {
  return fetchJson<VisualFacet[]>(
    `${BASE}/projects/${projectId}/visual-facets`,
  );
}

export async function createVisualFacet(
  projectId: string,
  payload: {
    target_kind: string;
    entity_id?: string;
    feature_id?: string;
    facet_key: string;
    label?: string | null;
    requirement?: string;
  },
): Promise<VisualFacet> {
  return fetchJson<VisualFacet>(
    `${BASE}/projects/${projectId}/visual-facets`,
    {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify(payload),
    },
  );
}

export async function patchVisualFacet(
  facetId: string,
  fields: { label?: string | null; requirement?: string },
): Promise<VisualFacet> {
  return fetchJson<VisualFacet>(`${BASE}/visual-facets/${facetId}`, {
    method: "PATCH",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(fields),
  });
}

export async function deleteVisualFacet(facetId: string): Promise<void> {
  await fetchVoid(`${BASE}/visual-facets/${facetId}`, { method: "DELETE" });
}

export async function putValuePolicies(
  facetId: string,
  policies: { value: unknown; policy: string }[],
): Promise<ValuePolicy[]> {
  return fetchJson<ValuePolicy[]>(
    `${BASE}/visual-facets/${facetId}/value-policies`,
    {
      method: "PUT",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ policies }),
    },
  );
}

export async function getVisualAnchor(
  anchorId: string,
): Promise<VisualAnchorDetail> {
  return fetchJson<VisualAnchorDetail>(
    `${BASE}/visual-anchors/${anchorId}`,
  );
}

export async function putWorkingSet(
  anchorId: string,
  items: { asset_id: string; role: string; view_key?: string | null }[],
): Promise<VisualAnchorDetail> {
  return fetchJson<VisualAnchorDetail>(
    `${BASE}/visual-anchors/${anchorId}/items`,
    {
      method: "PUT",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ items }),
    },
  );
}

export async function captureRevision(
  anchorId: string,
): Promise<VisualAnchorRevisionSummary> {
  return fetchJson<VisualAnchorRevisionSummary>(
    `${BASE}/visual-anchors/${anchorId}/revisions`,
    { method: "POST" },
  );
}

export async function approveRevision(
  revisionId: string,
  expected: string | null,
): Promise<void> {
  await fetchVoid(
    `${BASE}/visual-anchor-revisions/${revisionId}/approve`,
    {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ expected_approved_revision_id: expected }),
    },
  );
}

export async function unapproveAnchor(
  anchorId: string,
  expected: string | null,
): Promise<void> {
  await fetchVoid(`${BASE}/visual-anchors/${anchorId}/unapprove`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ expected_approved_revision_id: expected }),
  });
}

export async function deleteVisualAnchor(anchorId: string): Promise<void> {
  await fetchVoid(`${BASE}/visual-anchors/${anchorId}`, {
    method: "DELETE",
  });
}

export async function createVisualAnchor(
  facetId: string,
  payload: {
    entity_revision_id?: string | null;
    value?: unknown;
    visual_context_entity_revision_id?: string | null;
  },
): Promise<import("./visualTypes").VisualAnchor> {
  return fetchJson<import("./visualTypes").VisualAnchor>(
    `${BASE}/visual-facets/${facetId}/anchors`,
    {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify(payload),
    },
  );
}

export async function listVisualAnchorRevisions(
  anchorId: string,
): Promise<VisualAnchorRevisionSummary[]> {
  return fetchJson<VisualAnchorRevisionSummary[]>(
    `${BASE}/visual-anchors/${anchorId}/revisions`,
  );
}

export async function listValuePolicies(
  facetId: string,
): Promise<ValuePolicy[]> {
  return fetchJson<ValuePolicy[]>(
    `${BASE}/visual-facets/${facetId}/value-policies`,
  );
}

// --- Realization (M9) ------------------------------------------------------------

export async function getRealizationReadiness(
  shotId: string,
): Promise<import("./realizationTypes").RealizationReadiness> {
  return fetchJson<import("./realizationTypes").RealizationReadiness>(
    `${BASE}/shots/${shotId}/realization-readiness`,
  );
}

// --- M11 Production Library (frozen R3 plan §11) -----------------------------

import type {
  ProductionObject,
  ProductionRevisionDetail,
  ProductionRevisionSummary,
  PublicationReadiness,
} from "./types";

export async function listProductionObjects(
  projectId: string,
): Promise<ProductionObject[]> {
  return fetchJson<ProductionObject[]>(
    `${BASE}/projects/${projectId}/production-objects`,
  );
}

export async function createProductionObject(
  projectId: string,
  name: string,
  description: string | null,
): Promise<ProductionObject> {
  return fetchJson<ProductionObject>(
    `${BASE}/projects/${projectId}/production-objects`,
    { method: "POST", body: JSON.stringify({ name, description }) },
  );
}

export async function getPublicationReadiness(
  productionObjectId: string,
  assetId: string,
): Promise<PublicationReadiness> {
  return fetchJson<PublicationReadiness>(
    `${BASE}/production-objects/${productionObjectId}/publication-readiness`,
    { method: "POST", body: JSON.stringify({ asset_id: assetId }) },
  );
}

export async function publishProductionRevision(
  productionObjectId: string,
  assetId: string,
): Promise<ProductionRevisionDetail> {
  return fetchJson<ProductionRevisionDetail>(
    `${BASE}/production-objects/${productionObjectId}/revisions`,
    { method: "POST", body: JSON.stringify({ asset_id: assetId }) },
  );
}

export async function listProductionRevisions(
  productionObjectId: string,
): Promise<ProductionRevisionSummary[]> {
  return fetchJson<ProductionRevisionSummary[]>(
    `${BASE}/production-objects/${productionObjectId}/revisions`,
  );
}

export async function getProductionRevision(
  revisionId: string,
): Promise<ProductionRevisionDetail> {
  return fetchJson<ProductionRevisionDetail>(
    `${BASE}/production-revisions/${revisionId}`,
  );
}

// --- M12 Composition authority (frozen R3 §14) --------------------------------

import type {
  Composition,
  CompositionRevisionSummary,
  IdentityPreview,
  OccurrenceRow,
  PublishOutcome,
} from "./types";

export async function listCompositions(
  projectId: string,
): Promise<Composition[]> {
  return fetchJson<Composition[]>(
    `${BASE}/projects/${projectId}/compositions`);
}

export async function createComposition(
  projectId: string,
  name: string,
  description: string | null,
): Promise<Composition> {
  return fetchJson<Composition>(
    `${BASE}/projects/${projectId}/compositions`,
    { method: "POST", body: JSON.stringify({ name, description }) });
}

export async function listOccurrences(
  compositionId: string,
): Promise<OccurrenceRow[]> {
  return fetchJson<OccurrenceRow[]>(
    `${BASE}/compositions/${compositionId}/occurrences`);
}

export interface MintInput {
  scope: string;
  expected_working_version: number;
  display_name: string;
  source: { kind: string; revision_id: string };
  visible: boolean;
  transform: { translation_mm: number[]; rotation_udeg: number[] };
}

export async function mintOccurrence(
  compositionId: string,
  body: MintInput,
): Promise<{ occurrence_id: string; working_version: number }> {
  return fetchJson(`${BASE}/compositions/${compositionId}/occurrences`, {
    method: "POST", body: JSON.stringify(body),
  });
}

export async function patchOccurrence(
  compositionId: string,
  occurrenceId: string,
  body: Partial<MintInput>,
): Promise<{ occurrence_id: string; working_version: number }> {
  return fetchJson(
    `${BASE}/compositions/${compositionId}/occurrences/${occurrenceId}`,
    { method: "PATCH", body: JSON.stringify(body) });
}

export async function previewIdentityOperation(
  compositionId: string,
  body: { scope: string; request: unknown },
): Promise<IdentityPreview> {
  return fetchJson<IdentityPreview>(
    `${BASE}/compositions/${compositionId}/identity-operations/preview`,
    { method: "POST", body: JSON.stringify(body) });
}

export async function applyIdentityOperation(
  compositionId: string,
  body: {
    scope: string;
    expected_working_version: number;
    expected_request_fingerprint: string;
    expected_impact_fingerprint: string;
    request: unknown;
  },
): Promise<{
  operation_id: string;
  kind: string;
  working_version: number;
  target_occurrence_ids: string[];
}> {
  return fetchJson(
    `${BASE}/compositions/${compositionId}/identity-operations`,
    { method: "POST", body: JSON.stringify(body) });
}

export async function publishComposition(
  compositionId: string,
  expectedWorkingVersion: number,
): Promise<PublishOutcome> {
  return fetchJson<PublishOutcome>(
    `${BASE}/compositions/${compositionId}/publish`,
    { method: "POST", body: JSON.stringify({ expected_working_version: expectedWorkingVersion }) });
}

import { fetchJson as sharedFetchJson } from "./api.shared";

/** GET helper for read endpoints (lists/details/history). */
export async function getJson<T>(url: string): Promise<T> {
  return sharedFetchJson<T>(url);
}

// --- M13 production world (frozen R3 §24) ----------------------------------

export interface AuthoritySubjectRead {
  composition_id: string;
  occurrence_id: string;
  subject_kind: string;
  subject_id: string | null;
  creative_entity_id: string | null;
  created_at: string | null;
}

export interface SpatialInterpretationRead {
  production_revision_id: string;
  interpretation_hash: string;
  spatial_interpretation_available?: boolean;
}

export interface BindingReadiness {
  ready: boolean;
  issues: { code: string }[];
  proposed_binding_hash: string;
  composition_revision_id: string;
  composition_revision_hash: string;
  spatial_world_revision_id: string;
  spatial_world_revision_hash: string;
  subject_summaries: { occurrence_id: string; kind?: string; id?: string }[];
  entry_summaries: { occurrence_id: string; placement: { kind: string; id: string } }[];
}

export interface BindingRead {
  binding_id: string;
  binding_hash: string;
  composition_revision_id: string;
  composition_revision_hash: string;
  spatial_world_revision_id: string;
  spatial_world_revision_hash: string;
  subjects: unknown[];
  entries: unknown[];
  created_at: string;
}

export interface ProductionWorldStatus {
  shot_id: string;
  selected: boolean;
  binding_id: string | null;
  binding_hash: string | null;
  binding_current_complete: boolean | null;
  stale_details: { code: string }[];
  ready: boolean;
  issues: { code: string }[];
  production_world: {
    binding: {
      binding_id: string;
      binding_hash: string;
      value: {
        composition_revision: {
          revision_id: string; snapshot_hash: string };
        spatial_world_revision: {
          revision_id: string; snapshot_hash: string };
      };
    };
    instance_feature_states?: unknown[];
    instance_spatial_states?: {
      production_instance_track_id: string;
      requirement: string }[];
  } | null;
  production_world_hash: string | null;
}

export async function getAuthoritySubject(
  compositionId: string, occurrenceId: string,
): Promise<AuthoritySubjectRead> {
  return getJson<AuthoritySubjectRead>(
    `${BASE}/compositions/${compositionId}/occurrences/${occurrenceId}`
    + `/authority-subject`);
}

export async function adoptAuthoritySubject(
  compositionId: string, occurrenceId: string, kind: string,
  creativeEntityId?: string,
): Promise<AuthoritySubjectRead> {
  return fetchJson(
    `${BASE}/compositions/${compositionId}/occurrences/${occurrenceId}`
    + `/authority-subject`,
    { method: "POST", body: JSON.stringify(
      { kind, creative_entity_id: creativeEntityId ?? null }) });
}

export async function getSpatialInterpretation(
  revisionId: string,
): Promise<{
  interpretation_hash: string;
  realization_local_to_subject_local: {
    translation_mm: number[]; rotation_udeg: number[] };
} | null> {
  const res = await fetch(
    `${BASE}/production-revisions/${revisionId}/spatial-interpretation`);
  if (res.status === 404) return null;
  if (!res.ok) throw new Error(`interpretation ${res.status}`);
  return res.json();
}

export async function createSpatialInterpretation(
  revisionId: string,
  translationMm: number[],
): Promise<{ interpretation_hash: string }> {
  return createSpatialInterpretationTransform(
    revisionId, translationMm, [0, 0, 0]);
}

export async function createSpatialInterpretationTransform(
  revisionId: string,
  translationMm: number[],
  rotationUdeg: number[],
): Promise<{ interpretation_hash: string }> {
  return fetchJson(
    `${BASE}/production-revisions/${revisionId}/spatial-interpretation`,
    { method: "POST", body: JSON.stringify({
      realization_local_to_subject_local: {
        translation_mm: translationMm,
        rotation_udeg: rotationUdeg } }) });
}

export async function bindingReadiness(
  compositionRevisionId: string, worldRevisionId: string,
): Promise<BindingReadiness> {
  return fetchJson(
    `${BASE}/composition-revisions/${compositionRevisionId}`
    + `/spatial-binding-readiness`,
    { method: "POST", body: JSON.stringify({
      spatial_world_revision_id: worldRevisionId }) });
}

export async function publishBinding(
  compositionRevisionId: string, worldRevisionId: string,
): Promise<BindingRead> {
  return fetchJson(
    `${BASE}/composition-revisions/${compositionRevisionId}`
    + `/spatial-bindings`,
    { method: "POST", body: JSON.stringify({
      spatial_world_revision_id: worldRevisionId }) });
}

export async function getShotProductionWorld(
  shotId: string,
): Promise<ProductionWorldStatus> {
  return getJson<ProductionWorldStatus>(
    `${BASE}/shots/${shotId}/production-world`);
}

export async function putProductionWorldSelection(
  shotId: string, bindingId: string, expectedBindingId: string | null,
): Promise<{ binding_id: string }> {
  return fetchJson(
    `${BASE}/shots/${shotId}/production-world-selection`,
    { method: "PUT", body: JSON.stringify({
      binding_id: bindingId, expected_binding_id: expectedBindingId }) });
}

export async function deleteProductionWorldSelection(
  shotId: string, expectedBindingId: string,
): Promise<void> {
  const res = await fetch(
    `${BASE}/shots/${shotId}/production-world-selection`,
    { method: "DELETE", body: JSON.stringify({
      expected_binding_id: expectedBindingId }) });
  if (!res.ok) throw new Error(`selection delete ${res.status}`);
}

// --- M13 round-4: canonical /api helpers (browser boundary) -------------

export async function listProductionInstanceTracks(
  worldId: string,
): Promise<{ id: string; occurrence_id: string; requirement: string }[]> {
  return getJson(
    `${BASE}/spatial-worlds/${worldId}/production-instance-tracks`);
}

export async function createProductionInstanceTrack(
  worldId: string, occurrenceId: string, requirement: string,
): Promise<{ id: string }> {
  return fetchJson(
    `${BASE}/spatial-worlds/${worldId}/production-instance-tracks`,
    { method: "POST", body: JSON.stringify({
      occurrence_id: occurrenceId, requirement }) });
}

export async function createProductionInstanceSpatialTransition(
  trackId: string, body: {
    anchor_type: string; anchor_id: string; boundary: string;
    operation: string; transform: { translation_mm: number[];
                                    rotation_udeg: number[] } },
): Promise<{ id: string }> {
  return fetchJson(
    `${BASE}/production-instance-spatial-tracks/${trackId}/transitions`,
    { method: "POST", body: JSON.stringify(body) });
}

export interface CapturedProductionWorldRead {
  captured: boolean;
  production_world_hash?: string;
  binding?: {
    binding_id: string; binding_hash: string;
    composition_revision_id: string; composition_revision_hash: string;
    spatial_world_revision_id: string;
    spatial_world_revision_hash: string;
  };
  captured_feature_states?: unknown[];
  captured_spatial_states?: unknown[];
}

export async function getCapturedProductionWorld(
  revisionId: string,
): Promise<CapturedProductionWorldRead> {
  return getJson<CapturedProductionWorldRead>(
    `${BASE}/shot-revisions/${revisionId}/production-world`);
}

export async function listCompositionRevisionsPublic(
  compositionId: string,
): Promise<{ revision_id: string; revision_number?: number }[]> {
  return getJson(
    `${BASE}/compositions/${compositionId}/revisions`);
}
