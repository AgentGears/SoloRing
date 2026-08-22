// Shot editor page (M2C + M2D): intent form + reference panel + the three
// explicitly distinguished state sections:
//   Current Working State / Approved Canon / Revision History.
// Server components render authoritative state; client mutations refresh it.

import Link from "next/link";

import ApprovedTakePanel from "@/components/ApprovedTakePanel";
import ContinuityStatePanel from "@/components/ContinuityStatePanel";
import GenerationRealizationInspector from "@/components/GenerationRealizationInspector";
import RealizationPanel from "@/components/RealizationPanel";
import VisualContinuityPanel from "@/components/VisualContinuityPanel";
import VisualProvenanceList from "@/components/VisualProvenanceList";
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
  serverGetGenerationRealization,
  serverGetRealizationReadiness,
  serverGetReferences,
  serverGetRevisionContinuity,
  serverGetShot,
  serverGetVisualContinuity,
  serverListAssets,
  serverListRevisions,
  serverListTakes,
  serverListVisualAnchors,
  serverListVisualFacets,
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
  let continuityLoadError: { code: string; message: string } | null = null;
  let visualState: import("@/lib/visualTypes").VisualContinuityState | null =
    null;
  let realizationState: import("@/lib/realizationTypes").RealizationReadiness | null =
    null;
  let generationRealizations: Record<
    string,
    import("@/lib/realizationTypes").GenerationRealization | null
  > = {};
  let visualFacets: import("@/lib/visualTypes").VisualFacet[] = [];
  let visualAnchorsByFacet: Record<
    string,
    import("@/lib/visualTypes").VisualAnchor[]
  > = {};
  let provenance: Record<
    string,
    import("@/lib/types").RevisionContinuity | ApiError | null
  > = {};
  let loadError: ApiError | null = null;

  // ONLY these two are semantic not-ready conditions (r2 B6); any other
  // failure of the strict endpoint is a load/integrity error and renders
  // as one — never reinterpreted as continuity readiness.
  const NOT_READY_CODES = new Set([
    "NARRATIVE_CONTEXT_REQUIRED",
    "CONTINUITY_RELATION_ENDPOINT_REQUIRED",
  ]);

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

  if (!loadError) {
    try {
      continuity = await serverGetContinuityState(id);
    } catch (err) {
      const apiErr = asApiError(err);
      if (NOT_READY_CODES.has(apiErr.code)) {
        notReadyCode = apiErr.code;
        const issues = apiErr.details?.issues;
        if (Array.isArray(issues)) {
          notReadyIssues = issues as ReadinessIssue[];
        }
      } else {
        continuityLoadError = {
          code: apiErr.code,
          message: apiErr.message,
        };
      }
    }
    // Historical provenance errors surface VISIBLY (fail-closed integrity
    // responses are never silently nulled); null only for a response that
    // legitimately could not be attempted.
    try {
      visualState = await serverGetVisualContinuity(id);
    } catch {
      // Honest failure: the composed endpoint raised a non-semantic
      // error; the panel renders the unresolved state.
      visualState = null;
    }
    // M9 §34/§36: current realization inspection + per-Generation
    // captured realization (server-fed; failures render honestly).
    try {
      realizationState = await serverGetRealizationReadiness(id);
    } catch {
      realizationState = null;
    }
    generationRealizations = Object.fromEntries(
      await Promise.all(
        takes.map((t) => t.generation_id).map(async (gid) => {
          try {
            return [gid, await serverGetGenerationRealization(gid)] as const;
          } catch {
            return [gid, null] as const;
          }
        }),
      ),
    );
    // §71 promotion targets: the Shot's Project facets + realizations.
    try {
      visualFacets = await serverListVisualFacets(shot!.project_id);
      const perFacet = await Promise.all(
        visualFacets.map((vf) => serverListVisualAnchors(vf.id)),
      );
      visualAnchorsByFacet = Object.fromEntries(
        visualFacets.map((vf, i) => [vf.id, perFacet[i]]),
      );
    } catch {
      visualFacets = [];
      visualAnchorsByFacet = {};
    }
    provenance = Object.fromEntries(
      await Promise.all(
        revisions.map(async (r) => {
          try {
            return [r.id, await serverGetRevisionContinuity(r.id)] as const;
          } catch (err) {
            return [r.id, asApiError(err)] as const;
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
      <TakesPanel
        shotId={shot!.id}
        initialTakes={takes}
        visualTargets={{
          facets: visualFacets,
          anchorsByFacet: visualAnchorsByFacet,
        }}
      />

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

      <h2>Realization</h2>
      <RealizationPanel state={realizationState} />
      {takes.map((t) => {
        const gr = generationRealizations[t.generation_id];
        if (!gr) return null;
        return (
          <div key={t.id}>
            <h3>Generation {t.generation_id.slice(0, 8)}…</h3>
            <GenerationRealizationInspector generation={gr} currentEnvironment={realizationState?.environment ?? null} />
          </div>
        );
      })}

      <h2>Visual continuity</h2>
      <VisualContinuityPanel
        state={visualState}
        entityNames={Object.fromEntries(
          entities.map((e) => [e.id, e.name]),
        )}
      />

      <h2>Visual references at capture</h2>
      <VisualProvenanceList revisions={revisions} continuity={provenance} />

      <h2>Current continuity state</h2>
      <ContinuityStatePanel
        state={continuity}
        notReadyCode={notReadyCode}
        notReadyIssues={notReadyIssues}
        loadError={continuityLoadError}
        entityNames={Object.fromEntries(entities.map((e) => [e.id, e.name]))}
      />
    </main>
  );
}
