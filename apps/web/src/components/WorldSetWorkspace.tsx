"use client";

/**
 * World/Set workspace (frozen M12 R3 §15): the minimum honest surface.
 * Direct occurrences only; nested internals require switching context.
 * Scope is displayed before consequential mutation; identity vs
 * new-identity actions are distinct; readiness is shown before publish;
 * identity history and revision survival are inspectable.
 */

import { useCallback, useEffect, useMemo, useState } from "react";

import {
  AuthoritySubjectRow,
  BindingPanel,
} from "@/components/ProductionWorldPanel";

import { asApiError } from "@/lib/api.shared";
import {
  applyIdentityOperation,
  createComposition,
  getJson,
  listCompositions,
  listOccurrences,
  mintOccurrence,
  patchOccurrence,
  previewIdentityOperation,
  publishComposition,
} from "@/lib/api.client";
import type {
  Composition,
  CompositionRevisionSummary,
  OccurrenceRow,
} from "@/lib/types";

const SCOPE = "composition_working_state";

interface HistoryEntry {
  operation_id: string;
  kind: string;
  working_version_before: number;
  working_version_after: number;
  sources: Array<{ occurrence_id: string; terminates_identity: number }>;
  targets: string[];
}

interface RevisionDetailLite {
  revision_id: string;
  revision_number: number;
  snapshot_json: string;
}

interface ReadinessLite {
  ready: boolean;
  issues: Array<{ code: string; message: string }>;
  working_version: number;
  occurrence_count?: number;
  flattened_production_dependency_count?: number;
  flattened_nested_dependency_count?: number;
  proposed_snapshot_hash?: string | null;
}

export default function WorldSetWorkspace({ projectId }: { projectId: string }) {
  const [compositions, setCompositions] = useState<Composition[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [occurrences, setOccurrences] = useState<OccurrenceRow[]>([]);
  const [revisions, setRevisions] = useState<CompositionRevisionSummary[]>([]);
  const [history, setHistory] = useState<HistoryEntry[]>([]);
  const [readiness, setReadiness] = useState<ReadinessLite | null>(null);
  const [newName, setNewName] = useState("");
  const [sourceInput, setSourceInput] = useState("");
  const [sourceKind, setSourceKind] = useState<"production_revision" | "composition_revision">(
    "production_revision");
  const [pendingImpact, setPendingImpact] = useState<{
    summary: string;
    confirm: () => void;
  } | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);
  const [compare, setCompare] = useState<{
    a: RevisionDetailLite;
    b: RevisionDetailLite;
  } | null>(null);
  const [replaceTarget, setReplaceTarget] = useState<{
    occurrenceId: string;
    spec: {
      display_name: string;
      revisionId: string;
      kind: "production_revision" | "composition_revision";
    };
  } | null>(null);

  const selected = useMemo(
    () => compositions.find((c) => c.id === selectedId) ?? null,
    [compositions, selectedId],
  );

  const loadCompositions = useCallback(async () => {
    try {
      setCompositions(await listCompositions(projectId));
    } catch (e) {
      setError(asApiError(e).message);
    }
  }, [projectId]);

  const selectComposition = useCallback(async (cid: string) => {
    setSelectedId(cid);
    setNotice(null);
    setCompare(null);
    try {
      setOccurrences(await listOccurrences(cid));
      setRevisions(await getJson<CompositionRevisionSummary[]>(
        `/api/compositions/${cid}/revisions?limit=500`));
      setHistory(await getJson<HistoryEntry[]>(
        `/api/compositions/${cid}/identity-history?limit=500`));
      setReadiness(await getJson<ReadinessLite>(
        `/api/compositions/${cid}/publication-readiness`));
    } catch (e) {
      setError(asApiError(e).message);
    }
  }, []);

  useEffect(() => {
    void loadCompositions();
  }, [loadCompositions]);

  async function reload() {
    if (selectedId) await selectComposition(selectedId);
    await loadCompositions();
  }

  async function handleCreate() {
    setBusy(true);
    setError(null);
    try {
      const comp = await createComposition(projectId, newName.trim(), null);
      setNewName("");
      await loadCompositions();
      await selectComposition(comp.id);
    } catch (e) {
      setError(asApiError(e).message);
    } finally {
      setBusy(false);
    }
  }

  async function handleAddOccurrence() {
    if (!selectedId || !sourceInput.trim()) return;
    setBusy(true);
    setError(null);
    try {
      await mintOccurrence(selectedId, {
        scope: SCOPE,
        expected_working_version: selected?.working_version ?? 0,
        display_name: "New occurrence",
        source: { kind: sourceKind, revision_id: sourceInput.trim() },
        visible: true,
        transform: { translation_mm: [0, 0, 0], rotation_udeg: [0, 0, 0] },
      });
      setSourceInput("");
      await reload();
    } catch (e) {
      setError(asApiError(e).message);
    } finally {
      setBusy(false);
    }
  }

  async function handleFieldPatch(
    occurrenceId: string,
    body: Record<string, unknown>,
    note?: string,
  ) {
    if (!selectedId) return;
    setBusy(true);
    setError(null);
    try {
      await patchOccurrence(selectedId, occurrenceId, {
        scope: SCOPE,
        expected_working_version: selected?.working_version ?? 0,
        ...body,
      });
      await reload();
      if (note) setNotice(note);
    } catch (e) {
      setError(asApiError(e).message);
    } finally {
      setBusy(false);
    }
  }

  async function handleSourceUpdate(
    occurrenceId: string,
    kind: "production_revision" | "composition_revision",
    revisionId: string,
  ) {
    await handleFieldPatch(
      occurrenceId,
      { source: { kind, revision_id: revisionId } },
      "Identity is preserved. Physical/rig/spatial compatibility is not " +
        "certified by this milestone.",
    );
  }

  /** Preview an identity operation and present its impact for explicit
   * filmmaker confirmation — Preview is a decision point, never a hidden
   * handshake fed straight into Apply (frozen §15/§8.3). */
  async function previewThenConfirm(
    request: unknown,
    summary: (p: {
      source_occurrence_summaries: Array<Record<string, unknown>>;
      historical_reference_counts: Record<string, number>;
    }) => string,
    onConfirm: (
      p: { working_version: number; request_fingerprint: string;
           impact_fingerprint: string }) => Promise<void>,
  ) {
    if (!selectedId) return;
    setBusy(true);
    setError(null);
    try {
      const p = await previewIdentityOperation(
        selectedId, { scope: SCOPE, request });
      setPendingImpact({
        summary: summary(p),
        confirm: () => {
          void (async () => {
            setBusy(true);
            try {
              await onConfirm({
                working_version: p.working_version,
                request_fingerprint: p.request_fingerprint,
                impact_fingerprint: p.impact_fingerprint,
              });
              setPendingImpact(null);
            } catch (e) {
              setError(asApiError(e).message);
            } finally {
              setBusy(false);
            }
          })();
        },
      });
    } catch (e) {
      setError(asApiError(e).message);
    } finally {
      setBusy(false);
    }
  }

  function impactSummary(p: {
    source_occurrence_summaries: Array<Record<string, unknown>>;
    historical_reference_counts: Record<string, number>;
  }): string {
    const states = p.source_occurrence_summaries.map(
      (s) => {
        const oid = String(s.occurrence_id ?? "?");
        const active = s.active === true;
        const inWs = s.in_working_state === true;
        return `${oid} (${active ? "active" : "TERMINATED"}, ` +
          `${inWs ? "in working set" : "not in working set"})`;
      });
    const refs = Object.entries(p.historical_reference_counts)
      .map(([id, n]) => `${id} in ${n} published revision(s)`)
      .join(", ");
    return `Impact: ${states.join("; ") || "no sources"}` +
      (refs ? ` — history references: ${refs}` : "");
  }

  async function handleReplaceConfirm() {
    if (!selectedId || !replaceTarget) return;
    // frozen cardinality: replace_as_new carries exactly ONE target spec;
    // the target kind follows the CURRENT occurrence's source kind (a
    // nested Composition occurrence replaces into a nested Composition
    // Revision, never a Production-Revision-labeled UUID).
    const request = {
      kind: "replace_as_new",
      source_occurrence_ids: [replaceTarget.occurrenceId],
      target_working_specs: [{
        display_name: replaceTarget.spec.display_name,
        source: {
          kind: replaceTarget.spec.kind,
          revision_id: replaceTarget.spec.revisionId,
        },
        visible: true,
        transform: { translation_mm: [0, 0, 0], rotation_udeg: [0, 0, 0] },
      }],
    };
    await previewThenConfirm(
      request,
      impactSummary,
      async (p) => {
        const out = await applyIdentityOperation(selectedId, {
          scope: SCOPE,
          expected_working_version: p.working_version,
          expected_request_fingerprint: p.request_fingerprint,
          expected_impact_fingerprint: p.impact_fingerprint,
          request,
        });
        setReplaceTarget(null);
        await reload();
        setNotice(
          `Replaced as new occurrence ${out.target_occurrence_ids[0]} — ` +
          "old identity terminated in lineage; compatibility not certified.",
        );
      });
  }

  async function handleRemove(occurrenceId: string) {
    if (!selectedId) return;
    const request = { kind: "remove",
                      source_occurrence_ids: [occurrenceId],
                      target_working_specs: [] };
    await previewThenConfirm(
      request, impactSummary, async (p) => {
        await applyIdentityOperation(selectedId, {
          scope: SCOPE,
          expected_working_version: p.working_version,
          expected_request_fingerprint: p.request_fingerprint,
          expected_impact_fingerprint: p.impact_fingerprint,
          request,
        });
        await reload();
        setNotice(
          `Removed occurrence ${occurrenceId} (terminated in lineage)`);
      });
  }

  async function handleFork(
    occurrenceId: string,
    sourceKind: "production_revision" | "composition_revision",
    sourceRevisionId: string,
  ) {
    if (!selectedId) return;
    const request = {
      kind: "fork",
      source_occurrence_ids: [occurrenceId],
      target_working_specs: [{
        display_name: `Fork of ${occurrenceId.slice(0, 8)}`,
        source: { kind: sourceKind, revision_id: sourceRevisionId },
        visible: true,
        transform: { translation_mm: [0, 0, 0], rotation_udeg: [0, 0, 0] },
      }],
    };
    await previewThenConfirm(
      request, impactSummary, async (p) => {
        await applyIdentityOperation(selectedId, {
          scope: SCOPE,
          expected_working_version: p.working_version,
          expected_request_fingerprint: p.request_fingerprint,
          expected_impact_fingerprint: p.impact_fingerprint,
          request,
        });
        await reload();
        setNotice(`Forked occurrence ${occurrenceId}`);
      });
  }

  async function handlePublish() {
    if (!selectedId) return;
    setBusy(true);
    setError(null);
    try {
      const result = await publishComposition(
        selectedId, selected?.working_version ?? 0);
      await reload();
      setNotice(result.created
        ? `Published revision ${result.revision.revision_number} (new)`
        : `Converged on revision ${result.revision.revision_number}`);
    } catch (e) {
      setError(asApiError(e).message);
    } finally {
      setBusy(false);
    }
  }

  async function handleCompare() {
    if (!selectedId || revisions.length < 2) return;
    setBusy(true);
    try {
      const [aId, bId] = [
        revisions[revisions.length - 2].revision_id,
        revisions[revisions.length - 1].revision_id,
      ];
      const [a, b] = await Promise.all([
        getJson<RevisionDetailLite>(`/api/composition-revisions/${aId}`),
        getJson<RevisionDetailLite>(`/api/composition-revisions/${bId}`),
      ]);
      setCompare({ a, b });
    } catch (e) {
      setError(asApiError(e).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <section aria-label="World Set workspace" data-testid="world-set">
      <h2>Reusable Sets</h2>
      {error && <p role="alert" data-testid="ws-error">{error}</p>}
      {notice && <p data-testid="ws-notice">{notice}</p>}

      <div>
        <label htmlFor="new-composition-name">New reusable set name</label>
        <input
          id="new-composition-name"
          value={newName}
          onChange={(e) => setNewName(e.target.value)}
        />
        <button onClick={handleCreate} disabled={busy || !newName.trim()}>
          Create reusable set
        </button>
      </div>

      {compositions.length > 0 && (
        <ul aria-label="Reusable sets">
          {compositions.map((c) => (
            <li key={c.id}>
              <button onClick={() => void selectComposition(c.id)}>
                {c.name}
              </button>
              <small data-testid={`composition-id-${c.id}`}>{c.id}</small>
            </li>
          ))}
        </ul>
      )}

      {selected && (
        <div data-testid="composition-detail">
          <h3>
            {selected.name} — working version {selected.working_version}
          </h3>
          <p data-testid="scope-banner">
            Editing: Reusable set / this occurrence
          </p>

          {readiness && (
            <div data-testid="readiness-panel">
              {readiness.ready ? (
                <p>
                  Ready to publish: {readiness.occurrence_count} occurrences,
                  {" "}{readiness.flattened_production_dependency_count}{" "}
                  production and {readiness.flattened_nested_dependency_count}{" "}
                  nested dependencies (proposed{" "}
                  {readiness.proposed_snapshot_hash?.slice(0, 12)}…)
                </p>
              ) : (
                <p>
                  Not ready:{" "}
                  {readiness.issues.map((i) => i.code).join(", ") || "unresolved"}
                </p>
              )}
            </div>
          )}

          <M13BindingLauncher compositionId={selected.id} />

          <div>
            <select
              aria-label="Source kind"
              value={sourceKind}
              onChange={(e) => setSourceKind(
                e.target.value as "production_revision" | "composition_revision")}
              data-testid="source-kind-select">
              <option value="production_revision">Production Revision</option>
              <option value="composition_revision">Nested Composition Revision</option>
            </select>
            <label htmlFor="source-revision">
              {sourceKind === "production_revision"
                ? "Production Revision ID" : "Composition Revision ID"}
            </label>
            <input
              id="source-revision"
              value={sourceInput}
              onChange={(e) => setSourceInput(e.target.value)}
              placeholder={sourceKind === "production_revision"
                ? "exact Production Revision UUID"
                : "published Composition Revision UUID"}
            />
            <button onClick={handleAddOccurrence}
                    disabled={busy || !sourceInput.trim()}>
              Add occurrence
            </button>
          </div>

          <button onClick={handlePublish} disabled={busy}
                  data-testid="publish-composition">
            Publish revision
          </button>
          <button onClick={handleCompare}
                  disabled={busy || revisions.length < 2}
                  data-testid="compare-revisions">
            Compare last two revisions
          </button>

          <ul aria-label="Occurrences" data-testid="occurrence-list">
            {occurrences.map((o) => (
              <li key={o.occurrence_id} data-testid={`occ-${o.occurrence_id}`}>
                <span>{o.display_name}</span>
                <small>{o.occurrence_id}</small>
                <AuthoritySubjectRow
                  compositionId={selected.id}
                  occurrenceId={o.occurrence_id} />
                <span>
                  {" "}(x {o.x_mm}, y {o.y_mm}, z {o.z_mm}; yaw {o.yaw_udeg})
                  {o.visible ? "" : " — hidden"}
                </span>
                <button
                  onClick={() => void handleFieldPatch(
                    o.occurrence_id,
                    { display_name: `${o.display_name} ✎` })}>
                  Update this occurrence
                </button>
                <button
                  onClick={() => void handleFieldPatch(
                    o.occurrence_id, { visible: !o.visible })}>
                  {o.visible ? "Hide" : "Show"}
                </button>
                <button
                  onClick={() => {
                    const next = window.prompt(
                      "translation_mm x,y,z",
                      `${o.x_mm},${o.y_mm},${o.z_mm}`);
                    if (!next) return;
                    const [x, y, z] = next.split(",").map(Number);
                    void handleFieldPatch(o.occurrence_id, {
                      transform: {
                        translation_mm: [x, y, z],
                        rotation_udeg: [o.yaw_udeg, o.pitch_udeg, o.roll_udeg],
                      },
                    });
                  }}>
                  Edit transform
                </button>
                <button
                  onClick={() => {
                    const kind = o.source_kind === "composition_revision"
                      ? "composition_revision" : "production_revision";
                    const rid = window.prompt(
                      kind === "production_revision"
                        ? "same-lineage Production Revision ID"
                        : "same-lineage Composition Revision ID",
                      o.production_revision_id
                        ?? o.nested_composition_revision_id ?? "");
                    if (rid) {
                      void handleSourceUpdate(o.occurrence_id, kind, rid);
                    }
                  }}
                  title="Identity is preserved. Physical compatibility is not certified."
                  data-testid={`update-source-${o.occurrence_id}`}>
                  Update source (same identity)
                </button>
                <button
                  onClick={() => setReplaceTarget({
                    occurrenceId: o.occurrence_id,
                    spec: {
                      display_name: `${o.display_name} (new)`,
                      revisionId:
                        o.production_revision_id
                        ?? o.nested_composition_revision_id
                        ?? sourceInput.trim(),
                      kind: o.source_kind === "composition_revision"
                        ? "composition_revision" : "production_revision",
                    },
                  })}
                  data-testid={`replace-${o.occurrence_id}`}>
                  Replace as new occurrence
                </button>
                <button onClick={() => void handleRemove(o.occurrence_id)}
                        data-testid={`remove-${o.occurrence_id}`}>
                  Remove
                </button>
                <button
                  onClick={() => void handleFork(
                    o.occurrence_id,
                    o.source_kind === "composition_revision"
                      ? "composition_revision" : "production_revision",
                    o.production_revision_id
                      ?? o.nested_composition_revision_id
                      ?? sourceInput.trim())}
                  data-testid={`fork-${o.occurrence_id}`}>
                  Fork
                </button>
              </li>
            ))}
          </ul>

          {pendingImpact && (
            <div data-testid="impact-review">
              <h4>Identity operation impact</h4>
              <p>{pendingImpact.summary}</p>
              <button onClick={pendingImpact.confirm} disabled={busy}
                      data-testid="impact-confirm">
                Confirm identity operation
              </button>
              <button onClick={() => setPendingImpact(null)}
                      data-testid="impact-cancel">
                Cancel
              </button>
            </div>
          )}

          {replaceTarget && (
            <div data-testid="replace-dialog">
              <p>
                Replace {replaceTarget.occurrenceId} as a NEW occurrence with
                target name &quot;{replaceTarget.spec.display_name}&quot;
                sourcing revision {replaceTarget.spec.revisionId}. Identity
                will change; lineage is recorded.
              </p>
              <button onClick={handleReplaceConfirm} disabled={busy}
                      data-testid="replace-confirm">
                Confirm replace as new
              </button>
              <button onClick={() => setReplaceTarget(null)}>Cancel</button>
            </div>
          )}

          {revisions.length > 0 && (
            <ul aria-label="Published revisions">
              {revisions.map((r) => (
                <li key={r.revision_id}>
                  Revision {r.revision_number} · {r.revision_id}
                </li>
              ))}
            </ul>
          )}

          {compare && (
            <div data-testid="revision-compare">
              <h4>
                Revision {compare.a.revision_number} →{" "}
                {compare.b.revision_number}
              </h4>
              <ul>
                {diffOccurrences(
                  JSON.parse(compare.a.snapshot_json),
                  JSON.parse(compare.b.snapshot_json),
                ).map((d) => (
                  <li key={d.occurrence_id}
                      data-testid={`diff-${d.occurrence_id}`}>
                    {d.occurrence_id}: {d.state}
                  </li>
                ))}
              </ul>
            </div>
          )}

          {history.length > 0 && (
            <div data-testid="identity-history">
              <h4>Identity history</h4>
              <ul>
                {history.map((h) => (
                  <li key={h.operation_id}
                      data-testid={`history-${h.operation_id}`}>
                    {h.kind} (v{h.working_version_before}→
                    {h.working_version_after}): sources{" "}
                    {h.sources.map((s) => s.occurrence_id).join(", ") || "∅"} →{" "}
                    targets {h.targets.join(", ") || "∅"}
                  </li>
                ))}
              </ul>
            </div>
          )}
        </div>
      )}
    </section>
  );
}

function diffOccurrences(
  a: { occurrences: Array<Record<string, unknown> & { occurrence_id: string }> },
  b: { occurrences: Array<Record<string, unknown> & { occurrence_id: string }> },
) {
  // identity survives iff the occurrence_id persists; the STATE claim
  // compares the complete frozen occurrence value (name, source, transform,
  // visibility) so a moved/hidden chair is never labeled "same state".
  const byId = new Map(b.occurrences.map((o) => [o.occurrence_id, o]));
  return a.occurrences.map((oa) => {
    const ob = byId.get(oa.occurrence_id);
    if (!ob) {
      return { occurrence_id: oa.occurrence_id,
               state: "REMOVED in later revision" };
    }
    const sameState = JSON.stringify(oa) === JSON.stringify(ob);
    const changes: string[] = [];
    if (oa.display_name !== ob.display_name) {
      changes.push(`name "${oa.display_name}" to "${ob.display_name}"`);
    }
    const sa = oa.source as { kind: string; revision_id: string };
    const sb = ob.source as { kind: string; revision_id: string };
    if (sa.revision_id !== sb.revision_id || sa.kind !== sb.kind) {
      changes.push(`source ${sa.revision_id.slice(0, 8)} to ` +
        `${sb.revision_id.slice(0, 8)}`);
    }
    const ta = oa.transform as { translation_mm: number[] };
    const tb = ob.transform as { translation_mm: number[] };
    if (JSON.stringify(oa.transform) !== JSON.stringify(ob.transform)) {
      changes.push(`transform ${JSON.stringify(ta.translation_mm)} to ` +
        `${JSON.stringify(tb.translation_mm)}`);
    }
    if (oa.visible !== ob.visible) {
      changes.push(`visible ${oa.visible} to ${ob.visible}`);
    }
    return {
      occurrence_id: oa.occurrence_id,
      state: sameState ? "SAME identity and state" :
        `SAME identity, changed: ${changes.join("; ")}`,
    };
  });
}


function M13BindingLauncher({ compositionId }: { compositionId: string }) {
  const [pair, setPair] = useState<{ c: string; w: string } | null>(null);
  return (
    <section aria-label="m13 binding launcher">
      <button
        type="button"
        onClick={() => {
          const c = window.prompt("exact published Composition Revision ID:");
          if (!c) return;
          const w = window.prompt("exact SpatialWorldRevision ID:");
          if (!w) return;
          setPair({ c: c.trim(), w: w.trim() });
        }}>
        Compose↔Spatial binding for this set…
      </button>
      {pair ? (
        <BindingPanel compositionRevisionId={pair.c}
                      worldRevisionId={pair.w} />
      ) : (
        <small>
          {" "}The server derives the complete subject/entry sets; the
          caller submits only the exact revision pair.
        </small>
      )}
    </section>
  );
}
