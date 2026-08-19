// Entity detail (M6A plan §29): identity, revision history, explicit approval.

import Link from "next/link";

import { ContinuityFeaturesPanel } from "@/components/ContinuityFeaturesPanel";
import {
  ApproveRevisionButton,
  EntityRenameForm,
  RevisionCreateForm,
} from "@/components/StoryWorldPanel";
import { asApiError, type ApiError } from "@/lib/api.shared";
import {
  serverGetEntity,
  serverGetEntityRevision,
  serverListContinuityFeatures,
  serverListEntityRevisions,
  serverListFeatureTransitions,
} from "@/lib/api.server";
import type {
  ContinuityFeature,
  ContinuityFeatureTransition,
  EntityRevisionDetail,
  EntityRevisionSummary,
} from "@/lib/types";

export const dynamic = "force-dynamic";

export default async function EntityPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;

  let entity;
  let revisions: EntityRevisionSummary[] = [];
  let details: EntityRevisionDetail[] = [];
  let features: ContinuityFeature[] = [];
  let transitionsByFeature: Record<string, ContinuityFeatureTransition[]> = {};
  let loadError: ApiError | null = null;

  try {
    entity = await serverGetEntity(id);
    revisions = await serverListEntityRevisions(id);
    details = await Promise.all(
      revisions.map((r) => serverGetEntityRevision(r.id)),
    );
    features = await serverListContinuityFeatures(id);
    const perFeature = await Promise.all(
      features.map((f) => serverListFeatureTransitions(f.id)),
    );
    transitionsByFeature = Object.fromEntries(
      features.map((f, i) => [f.id, perFeature[i]]),
    );
  } catch (err) {
    loadError = asApiError(err);
  }

  if (loadError) {
    return (
      <main>
        <h1>Story World</h1>
        <div className="empty">
          {loadError.code} — {loadError.message}
        </div>
        <p>
          <Link href="/">← Back to projects</Link>
        </p>
      </main>
    );
  }

  const approved = entity!.approved_revision_id ?? null;
  const approvedNumber = revisions.find((r) => r.id === approved)?.revision_number;
  const byNumber = new Map(details.map((d) => [d.id, d]));

  return (
    <main>
      <p>
        <Link href={`/projects/${entity!.project_id}`}>← Project</Link>
      </p>
      <h1>{entity!.name}</h1>
      <p className="meta">
        {entity!.kind} · created {entity!.created_at}
      </p>
      <h2>Approved design</h2>
      {approved ? (
        <div className="card row">
          <div>
            Revision {approvedNumber} ·{" "}
            <span className="hash">{approved.slice(0, 12)}…</span>
          </div>
        </div>
      ) : (
        <div className="empty">No approved revision yet.</div>
      )}
      <EntityRenameForm entity={entity!} />

      <h2>Revision history</h2>
      {revisions.length === 0 ? (
        <div className="empty">No design revisions yet.</div>
      ) : (
        [...revisions]
          .sort((a, b) => b.revision_number - a.revision_number)
          .map((r) => {
            const detail = byNumber.get(r.id);
            let description: string | null = null;
            if (detail) {
              try {
                description = (
                  JSON.parse(detail.spec_json) as { description?: string | null }
                ).description ?? null;
              } catch {
                description = null;
              }
            }
            return (
              <div className="card row" key={r.id}>
                <div>
                  <strong>Revision {r.revision_number}</strong>
                  {r.id === approved ? (
                    <span className="meta"> · APPROVED</span>
                  ) : null}
                  <div className="meta">
                    {description ?? "no description"} ·{" "}
                    <span className="hash">{r.spec_hash.slice(0, 12)}…</span> ·{" "}
                    {r.created_at}
                  </div>
                </div>
                <ApproveRevisionButton entity={entity!} revision={r} />
              </div>
            );
          })
      )}
      <RevisionCreateForm entityId={entity!.id} />

      <h2>Continuity features</h2>
      <ContinuityFeaturesPanel
        entityId={entity!.id}
        features={features}
        transitionsByFeature={transitionsByFeature}
      />
    </main>
  );
}
