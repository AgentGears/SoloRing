// Shot editor page (M2C + M2D): intent form + reference panel + the three
// explicitly distinguished state sections:
//   Current Working State / Approved Canon / Revision History.
// Server components render authoritative state; client mutations refresh it.

import Link from "next/link";

import ApprovedTakePanel from "@/components/ApprovedTakePanel";
import ReferencePanel from "@/components/ReferencePanel";
import { SemanticDependenciesPanel } from "@/components/SemanticDependenciesPanel";
import RevisionList from "@/components/RevisionList";
import ShotForm from "@/components/ShotForm";
import TakesPanel from "@/components/TakesPanel";
import WorkingStatePanel from "@/components/WorkingStatePanel";
import { asApiError, type ApiError } from "@/lib/api.shared";
import {
  serverGetReferences,
  serverGetShot,
  serverListAssets,
  serverListRevisions,
  serverListTakes,
} from "@/lib/api.server";
import { serverListEntities, serverListSemanticDependencies } from "@/lib/api.server";
import type {
  Asset,
  ReferenceItem,
  RevisionSummary,
  ShotDetail,
  TakeItem,
} from "@/lib/types";

export const dynamic = "force-dynamic";

export default async function ShotPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;

  let shot: ShotDetail;
  let references: ReferenceItem[] = [];
  let assets: Asset[] = [];
  let revisions: RevisionSummary[] = [];
  let takes: TakeItem[] = [];
  let entities: import("@/lib/types").Entity[] = [];
  let semanticDeps: import("@/lib/types").SemanticDependency[] = [];
  let loadError: ApiError | null = null;

  try {
    shot = await serverGetShot(id);
    [references, assets, revisions, takes, entities, semanticDeps] =
      await Promise.all([
        serverGetReferences(id),
        serverListAssets(shot.project_id),
        serverListRevisions(id),
        serverListTakes(id),
        serverListEntities(shot.project_id),
        serverListSemanticDependencies(id),
      ]);
  } catch (err) {
    loadError = asApiError(err);
  }

  if (loadError) {
    return (
      <main>
        <h1>Shot</h1>
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
        <Link href={`/projects/${shot!.project_id}`}>← Project</Link>
      </p>
      <h1>
        Shot {shot!.shot_number}
        {shot!.title ? ` — ${shot!.title}` : ""}
      </h1>

      <h2>Current working state</h2>
      <WorkingStatePanel
        workingSnapshotHash={shot!.working_snapshot_hash}
        updatedAt={shot!.updated_at}
      />

      <h2>Approved canon</h2>
      <ApprovedTakePanel
        approvedTakeId={shot!.approved_take_id}
        differs={shot!.working_state_differs_from_approved}
      />

      <h2>Shot intent</h2>
      <ShotForm shot={shot!} />

      <h2>Semantic dependencies</h2>
      <SemanticDependenciesPanel
        shotId={shot!.id}
        initialDependencies={semanticDeps}
        entities={entities}
      />

      <h2>References</h2>
      <ReferencePanel
        shotId={shot!.id}
        projectId={shot!.project_id}
        initialReferences={references}
        initialAssets={assets}
      />

      <h2>Takes</h2>
      <TakesPanel shotId={shot!.id} initialTakes={takes} />

      <h2>Revision history</h2>
      <RevisionList revisions={revisions} />
    </main>
  );
}
