"use client";

// Browser-only client: relative /api calls through the Next.js rewrite, plus
// the single canonical Blob-URL mapping boundary (M2 §3.3.3).

import { ApiError, fetchJson, fetchVoid } from "./api.shared";
import type {
  Asset,
  Entity,
  EntityRevisionSummary,
  GenerationInfo,
  Project,
  ReferenceItem,
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
