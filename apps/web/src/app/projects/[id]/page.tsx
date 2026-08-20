// Project page (M2B): shot list + persistent Project Asset list.

import Link from "next/link";

import { ProjectContinuityPanel } from "@/components/ProjectContinuityPanel";
import { VisualIdentityPanel } from "@/components/VisualIdentityPanel";
import { ShotCreateForm, ShotDeleteButton } from "@/components/ShotActions";
import { NarrativePanel } from "@/components/NarrativePanel";
import { StoryWorldPanel } from "@/components/StoryWorldPanel";
import { asApiError, type ApiError } from "@/lib/api.shared";
import {
  serverGetProject,
  serverListAssets,
  serverListEntities,
  serverListPredicates,
  serverListRelationTransitions,
  serverListRelations,
  serverListScenes,
  serverListSequences,
  serverListShots,
  serverListVisualAnchors,
  serverListVisualFacets,
} from "@/lib/api.server";
import type {
  Asset,
  ContinuityPredicate,
  ContinuityRelation,
  Entity,
  Project,
  RelationTransition,
  Scene,
  Sequence,
  ShotListItem,
} from "@/lib/types";

export const dynamic = "force-dynamic";

function AssetTile({ asset }: { asset: Asset }) {
  const image =
    asset.detected_media_type === "image/png" ||
    asset.detected_media_type === "image/jpeg";
  return (
    <div className="asset-tile" title={asset.blob_hash}>
      {image ? (
        // Client-mapped Blob URL is applied by AssetThumb in M2C; M2B renders
        // metadata only to avoid importing client code in a server component.
        <div className="generic-icon">IMG</div>
      ) : (
        <div className="generic-icon">FILE</div>
      )}
      <div className="name">{asset.original_filename ?? "unnamed"}</div>
      <div className="meta">
        {asset.created_at} · {asset.blob_hash.slice(0, 8)}…
      </div>
    </div>
  );
}

export default async function ProjectPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;

  let project: Project;
  let shots: ShotListItem[] = [];
  let assets: Asset[] = [];
  let entities: Entity[] = [];
  let sequences: Sequence[] = [];
  let scenes: Scene[] = [];
  let predicates: ContinuityPredicate[] = [];
  let relations: ContinuityRelation[] = [];
  let transitionsByRelation: Record<string, RelationTransition[]> = {};
  let visualFacets: import("@/lib/visualTypes").VisualFacet[] = [];
  let anchorsByFacet: Record<
    string,
    import("@/lib/visualTypes").VisualAnchor[]
  > = {};
  let loadError: ApiError | null = null;

  try {
    project = await serverGetProject(id);
    [shots, assets, entities, sequences, predicates, relations, visualFacets] =
      await Promise.all([
        serverListShots(id),
        serverListAssets(id),
        serverListEntities(id),
        serverListSequences(id),
        serverListPredicates(id),
        serverListRelations(id),
        serverListVisualFacets(id),
      ]);
    const anchorsByFacetList = await Promise.all(
      visualFacets.map((vf) => serverListVisualAnchors(vf.id)),
    );
    anchorsByFacet = Object.fromEntries(
      visualFacets.map((vf, i) => [vf.id, anchorsByFacetList[i]]),
    );
    scenes = (
      await Promise.all(
        sequences.map((s) => serverListScenes(s.id)),
      )
    ).flat();
    const perRelation = await Promise.all(
      relations.map((r) => serverListRelationTransitions(r.id)),
    );
    transitionsByRelation = Object.fromEntries(
      relations.map((r, i) => [r.id, perRelation[i]]),
    );
  } catch (err) {
    loadError = asApiError(err);
  }

  if (loadError) {
    return (
      <main>
        <h1>Project</h1>
        <div className="empty">
          {loadError.code} — {loadError.message}
        </div>
        <p>
          <Link href="/">← Back to projects</Link>
        </p>
      </main>
    );
  }

  return (
    <main>
      <p>
        <Link href="/">← Projects</Link>
      </p>
      <h1>{project!.name}</h1>
      {project!.description ? (
        <p className="meta">{project!.description}</p>
      ) : null}

      <h2>Narrative structure</h2>
      {sequences.length === 0 ? (
        <div className="empty">No sequences yet.</div>
      ) : null}
      <NarrativePanel
        projectId={id}
        sequences={sequences}
        scenes={scenes}
        shots={shots}
      />

      <h2>Shots</h2>
      {shots.length === 0 ? (
        <div className="empty">No shots yet.</div>
      ) : (
        shots.map((s) => (
          <div className="card row" key={s.id}>
            <div>
              <Link href={`/shots/${s.id}`}>
                <strong>
                  Shot {s.shot_number}
                  {s.title ? ` — ${s.title}` : ""}
                </strong>
              </Link>
              <div className="meta">{s.subject}</div>
            </div>
            <ShotDeleteButton shot={s} />
          </div>
        ))
      )}
      <ShotCreateForm projectId={id} />

      <h2>Project assets</h2>
      {assets.length === 0 ? (
        <div className="empty">No reference assets uploaded yet.</div>
      ) : (
        <div className="asset-grid">
          {assets.map((a) => (
            <AssetTile key={a.id} asset={a} />
          ))}
        </div>
      )}

      <h2>Story World</h2>
      <StoryWorldPanel projectId={id} entities={entities} />

      <h2>Visual Identity</h2>
      <VisualIdentityPanel
        projectId={id}
        facets={visualFacets}
        anchorsByFacet={anchorsByFacet}
      />

      <h2>Continuity relations</h2>
      <ProjectContinuityPanel
        projectId={id}
        entities={entities}
        predicates={predicates}
        relations={relations}
        transitionsByRelation={transitionsByRelation}
        shots={shots}
      />
    </main>
  );
}
