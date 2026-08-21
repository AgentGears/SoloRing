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
