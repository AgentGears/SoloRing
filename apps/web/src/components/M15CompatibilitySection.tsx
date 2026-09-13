"use client";

/**
 * M15 Production Library compatibility section (frozen R6 §20.1):
 * per-Production-Object update availability — tracked-use count,
 * concrete newer candidates ("Check compatibility"), and the backend
 * assessment summary. Projection only; every verdict is the
 * backend's.
 */

import { useCallback, useEffect, useState } from "react";

import {
  getCompatibilityAssessment,
  getRevisionUpdates,
  type CompatibilityAssessment,
  type UpdateDiscovery,
} from "@/lib/api.client";

export default function M15CompatibilitySection({
  projectId,
}: {
  projectId: string;
}) {
  const [objects, setObjects] = useState<
    { id: string; name: string }[]
  >([]);
  const [selected, setSelected] = useState<string | null>(null);
  const [discovery, setDiscovery] = useState<UpdateDiscovery | null>(null);
  const [assessment, setAssessment] =
    useState<CompatibilityAssessment | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    let cancelled = false;
    fetch(`/api/projects/${projectId}/production-objects`)
      .then((r) => (r.ok ? r.json() : []))
      .then((list) => {
        if (!cancelled) setObjects(list);
      })
      .catch(() => {
        if (!cancelled) setObjects([]);
      });
    return () => {
      cancelled = true;
    };
  }, [projectId]);

  const refresh = useCallback(async (objectId: string | null) => {
    setDiscovery(null);
    setAssessment(null);
    if (!objectId) return;
    try {
      setDiscovery(await getRevisionUpdates(objectId));
    } catch {
      setDiscovery(null);
    }
  }, []);

  const candidates = discovery?.uses.flatMap((u) => u.candidates) ?? [];
  const uniqueCandidates = Array.from(
    new Map(candidates.map((c) => [c.revision_id, c])).values(),
  ).sort((a, b) => b.revision_number - a.revision_number);

  return (
    <div
      className="m15-compatibility"
      data-testid="m15-compatibility-section"
    >
      <h4>Revision updates</h4>
      <select
        aria-label="Production object for update check"
        value={selected ?? ""}
        onChange={(e) => {
          setSelected(e.target.value || null);
          void refresh(e.target.value || null);
        }}
      >
        <option value="">Choose a Production object…</option>
        {objects.map((o) => (
          <option key={o.id} value={o.id}>
            {o.name}
          </option>
        ))}
      </select>
      {discovery && (
        <p data-testid="m15-tracked-use-count">
          {discovery.tracked_use_count} tracked current use
          {discovery.tracked_use_count === 1 ? "" : "s"}
        </p>
      )}
      {uniqueCandidates.length > 0 && (
        <ul data-testid="m15-update-candidates">
          {uniqueCandidates.map((c) => (
            <li key={c.revision_id}>
              r{c.revision_number} · {c.revision_id.slice(0, 8)}
              <button
                type="button"
                disabled={!busy === false || busy}
                data-testid={`check-compatibility-${c.revision_id}`}
                onClick={async () => {
                  if (!discovery?.uses[0]) return;
                  setBusy(true);
                  try {
                    setAssessment(
                      await getCompatibilityAssessment(
                        discovery.uses[0].current_revision_id,
                        c.revision_id,
                      ),
                    );
                  } catch {
                    setAssessment(null);
                  } finally {
                    setBusy(false);
                  }
                }}
              >
                Check compatibility
              </button>
            </li>
          ))}
        </ul>
      )}
      {assessment && (
        <dl data-testid="m15-assessment-summary">
          <dt>Overall summary verdict</dt>
          <dd>{assessment.overall_verdict}</dd>
          <dt>Per-use verdict counts</dt>
          {Object.entries(assessment.verdict_counts).map(([v, n]) => (
            <dd key={v}>
              {v}: {n}
            </dd>
          ))}
          <dt>Advisory references (current state)</dt>
          <dd>
            {assessment.advisory.published_composition_references.length}{" "}
            published ·{" "}
            {assessment.advisory.historical_shot_references.length}{" "}
            historical ·{" "}
            {assessment.advisory.current_shot_selections.length} current
            selections
          </dd>
        </dl>
      )}
    </div>
  );
}
