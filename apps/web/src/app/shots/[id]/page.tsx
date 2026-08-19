// Shot editor page (M2C + M2D): intent form + reference panel + the three
// explicitly distinguished state sections:
//   Current Working State / Approved Canon / Revision History.
// Server components render authoritative state; client mutations refresh it.

import Link from "next/link";

import ApprovedTakePanel from "@/components/ApprovedTakePanel";
import ContinuityStatePanel from "@/components/ContinuityStatePanel";
import ReferencePanel from "@/components/ReferencePanel";
import { SemanticDependenciesPanel } from "@/components/SemanticDependenciesPanel";
import RevisionProvenanceList from "@/components/RevisionProvenanceList";
import RevisionList from "@/components/RevisionList";
import ShotForm from "@/components/ShotForm";
import TakesPanel from "@/components/TakesPanel";
import WorkingStatePanel from "@/components/WorkingStatePanel";
import { asApiError, type ApiError } from "@/lib/api.shared";
import {
  serverGetContinuityState,
  serverGetReferences,
  serverGetRevisionContinuity,
  serverGetShot,
  serverListAssets,
  serverListRevisions,
  serverListTakes,
} from "@/lib/api.server";
import { serverListEntities, serverListSemanticDependencies } from "@/lib/api.server";
import type {
  Asset,
  ContinuityStateResponse,
  ReadinessIssue,
  ReferenceItem,
  RevisionContinuity,
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
  let continuity: ContinuityStateResponse | null = null;
  let notReadyCode: string | null = null;
  let notReadyIssues: ReadinessIssue[] = [];
  let provenance: Record<string, RevisionContinuity | null> = {};
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

  // The strict current-state endpoint RAISES when not ready; the error
  // envelope carries the full ordered issue set — render it honestly
  // (APR-051) instead of a partial body.
  if (!loadError) {
    try {
      continuity = await serverGetContinuityState(id);
    } catch (err) {
      const apiErr = asApiError(err);
      notReadyCode = apiErr.code;
      const issues = apiErr.details?.issues;
      if (Array.isArray(issues)) {
        notReadyIssues = issues as ReadinessIssue[];
      }
    }
    provenance = Object.fromEntries(
      await Promise.all(
        revisions.map(async (r) => {
          try {
            return [r.id, await serverGetRevisionContinuity(r.id)] as const;
          } catch {
            return [r.id, null] as const;
          }
        }),
      ),
    );
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

      <h2>Revision continuity provenance</h2>
      <RevisionProvenanceList
        revisions={revisions}
        continuity={provenance}
        entityNames={Object.fromEntries(
          entities.map((e) => [e.id, e.name]),
        )}
      />

      <h2>Current continuity state</h2>
      <ContinuityStatePanel
        state={continuity}
        notReadyCode={notReadyCode}
        notReadyIssues={notReadyIssues}
        entityNames={Object.fromEntries(entities.map((e) => [e.id, e.name]))}
      />
    </main>
  );
}
