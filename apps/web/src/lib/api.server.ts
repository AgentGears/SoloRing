// SERVER-ONLY client for Server Components (M2 §4.2). Reads the absolute
// backend origin from SOLORING_API_ORIGIN (never NEXT_PUBLIC_; must never
// appear in Client Component props or emitted browser JS). The server-only
// npm marker is not installed, so the boundary is enforced by module
// separation + the emitted-bundle check (no new runtime dependency).

import { fetchJson } from "./api.shared";
import type {
  Asset,
  Entity,
  EntityRevisionDetail,
  EntityRevisionSummary,
  Project,
  ReferenceItem,
  RevisionSummary,
  Scene,
  Sequence,
  ShotDetail,
  ShotListItem,
  TakeItem,
} from "./types";

export function apiOrigin(): string {
  return process.env.SOLORING_API_ORIGIN || "http://127.0.0.1:8000";
}

export async function serverListProjects(): Promise<Project[]> {
  return fetchJson<Project[]>(`${apiOrigin()}/projects`);
}

export async function serverGetProject(id: string): Promise<Project> {
  return fetchJson<Project>(`${apiOrigin()}/projects/${id}`);
}

export async function serverListShots(projectId: string): Promise<ShotListItem[]> {
  return fetchJson<ShotListItem[]>(`${apiOrigin()}/projects/${projectId}/shots`);
}

export async function serverListAssets(projectId: string): Promise<Asset[]> {
  return fetchJson<Asset[]>(`${apiOrigin()}/projects/${projectId}/assets`);
}

export async function serverGetShot(id: string): Promise<ShotDetail> {
  return fetchJson<ShotDetail>(`${apiOrigin()}/shots/${id}`);
}

export async function serverGetReferences(shotId: string): Promise<ReferenceItem[]> {
  return fetchJson<ReferenceItem[]>(`${apiOrigin()}/shots/${shotId}/references`);
}

export async function serverListRevisions(
  shotId: string,
): Promise<RevisionSummary[]> {
  return fetchJson<RevisionSummary[]>(`${apiOrigin()}/shots/${shotId}/revisions`);
}

export async function serverListTakes(shotId: string): Promise<TakeItem[]> {
  return fetchJson<TakeItem[]>(`${apiOrigin()}/shots/${shotId}/takes`);
}

// --- Story World (M6A) ---------------------------------------------------------

export async function serverListEntities(
  projectId: string,
): Promise<Entity[]> {
  return fetchJson<Entity[]>(`${apiOrigin()}/projects/${projectId}/entities`);
}

export async function serverGetEntity(id: string): Promise<Entity> {
  return fetchJson<Entity>(`${apiOrigin()}/entities/${id}`);
}

export async function serverListEntityRevisions(
  entityId: string,
): Promise<EntityRevisionSummary[]> {
  return fetchJson<EntityRevisionSummary[]>(
    `${apiOrigin()}/entities/${entityId}/revisions`,
  );
}

export async function serverGetEntityRevision(
  revisionId: string,
): Promise<EntityRevisionDetail> {
  return fetchJson<EntityRevisionDetail>(
    `${apiOrigin()}/entity-revisions/${revisionId}`,
  );
}

// --- Narrative (M6B) ------------------------------------------------------------

export async function serverListSequences(
  projectId: string,
): Promise<Sequence[]> {
  return fetchJson<Sequence[]>(`${apiOrigin()}/projects/${projectId}/sequences`);
}

export async function serverListScenes(
  sequenceId: string,
): Promise<Scene[]> {
  return fetchJson<Scene[]>(`${apiOrigin()}/sequences/${sequenceId}/scenes`);
}

// --- Semantic dependencies (M6C) --------------------------------------------------

export async function serverListSemanticDependencies(
  shotId: string,
): Promise<import("./types").SemanticDependency[]> {
  return fetchJson<import("./types").SemanticDependency[]>(
    `${apiOrigin()}/shots/${shotId}/semantic-dependencies`,
  );
}


// --- Narrative continuity state (M7D) ----------------------------------------------

export async function serverListContinuityFeatures(
  entityId: string,
): Promise<import("./types").ContinuityFeature[]> {
  return fetchJson<import("./types").ContinuityFeature[]>(
    `${apiOrigin()}/entities/${entityId}/continuity-features`,
  );
}

export async function serverListFeatureTransitions(
  featureId: string,
): Promise<import("./types").ContinuityFeatureTransition[]> {
  return fetchJson<import("./types").ContinuityFeatureTransition[]>(
    `${apiOrigin()}/continuity-features/${featureId}/transitions`,
  );
}

export async function serverListPredicates(
  projectId: string,
): Promise<import("./types").ContinuityPredicate[]> {
  return fetchJson<import("./types").ContinuityPredicate[]>(
    `${apiOrigin()}/projects/${projectId}/continuity-predicates`,
  );
}

export async function serverListRelations(
  projectId: string,
): Promise<import("./types").ContinuityRelation[]> {
  return fetchJson<import("./types").ContinuityRelation[]>(
    `${apiOrigin()}/projects/${projectId}/continuity-relations`,
  );
}

export async function serverListRelationTransitions(
  relationId: string,
): Promise<import("./types").RelationTransition[]> {
  return fetchJson<import("./types").RelationTransition[]>(
    `${apiOrigin()}/continuity-relations/${relationId}/transitions`,
  );
}

export async function serverGetContinuityState(
  shotId: string,
): Promise<import("./types").ContinuityStateResponse> {
  return fetchJson<import("./types").ContinuityStateResponse>(
    `${apiOrigin()}/shots/${shotId}/continuity-state`,
  );
}

export async function serverGetRevisionContinuity(
  revisionId: string,
): Promise<import("./types").RevisionContinuity> {
  return fetchJson<import("./types").RevisionContinuity>(
    `${apiOrigin()}/shot-revisions/${revisionId}/continuity`,
  );
}


// --- Visual Identity (M8) ---------------------------------------------------------

export async function serverListVisualFacets(
  projectId: string,
): Promise<import("./visualTypes").VisualFacet[]> {
  return fetchJson<import("./visualTypes").VisualFacet[]>(
    `${apiOrigin()}/projects/${projectId}/visual-facets`,
  );
}

export async function serverListVisualAnchors(
  facetId: string,
): Promise<import("./visualTypes").VisualAnchor[]> {
  return fetchJson<import("./visualTypes").VisualAnchor[]>(
    `${apiOrigin()}/visual-facets/${facetId}/anchors`,
  );
}

export async function serverGetVisualAnchor(
  anchorId: string,
): Promise<import("./visualTypes").VisualAnchorDetail> {
  return fetchJson<import("./visualTypes").VisualAnchorDetail>(
    `${apiOrigin()}/visual-anchors/${anchorId}`,
  );
}

export async function serverGetVisualContinuity(
  shotId: string,
): Promise<import("./visualTypes").VisualContinuityState> {
  return fetchJson<import("./visualTypes").VisualContinuityState>(
    `${apiOrigin()}/shots/${shotId}/visual-continuity`,
  );
}

export async function serverGetRealizationReadiness(
  shotId: string,
): Promise<import("./realizationTypes").RealizationReadiness> {
  return fetchJson<import("./realizationTypes").RealizationReadiness>(
    `${apiOrigin()}/shots/${shotId}/realization-readiness`,
  );
}

export async function serverGetGenerationRealization(
  generationId: string,
): Promise<import("./realizationTypes").GenerationRealization> {
  return fetchJson<import("./realizationTypes").GenerationRealization>(
    `${apiOrigin()}/generations/${generationId}`,
  );
}
