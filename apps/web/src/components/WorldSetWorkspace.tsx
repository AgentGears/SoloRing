"use client";

/**
 * World/Set workspace (frozen M12 R3 §15): the minimum honest surface for
 * Composition authoring. Direct occurrences only; nested internals require
 * switching authoring context. Scope is displayed before consequential
 * mutation. Identity vs new-identity actions are distinct.
 */

import { useCallback, useEffect, useMemo, useState } from "react";

import { asApiError, type ApiError } from "@/lib/api.shared";
import {
  applyIdentityOperation,
  createComposition,
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

export default function WorldSetWorkspace({ projectId }: { projectId: string }) {
  const [compositions, setCompositions] = useState<Composition[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [occurrences, setOccurrences] = useState<OccurrenceRow[]>([]);
  const [revisions, setRevisions] = useState<CompositionRevisionSummary[]>([]);
  const [newName, setNewName] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);

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

  const loadOccurrences = useCallback(async (cid: string) => {
    try {
      setOccurrences(await listOccurrences(cid));
    } catch (e) {
      setError(asApiError(e).message);
    }
  }, []);

  useEffect(() => {
    void loadCompositions();
  }, [loadCompositions]);

  async function handleCreate() {
    setBusy(true);
    setError(null);
    try {
      const comp = await createComposition(projectId, newName.trim(), null);
      setNewName("");
      await loadCompositions();
      setSelectedId(comp.id);
    } catch (e) {
      setError(asApiError(e).message);
    } finally {
      setBusy(false);
    }
  }

  async function selectComposition(cid: string) {
    setSelectedId(cid);
    setNotice(null);
    await loadOccurrences(cid);
    try {
      const revs = await fetch(
        `/api/compositions/${cid}/revisions`,
      ).then((r) => r.json());
      setRevisions(revs);
    } catch {
      setRevisions([]);
    }
  }

  async function handleMint(spec: {
    display_name: string;
    revision_id: string;
  }) {
    if (!selectedId) return;
    setBusy(true);
    setError(null);
    try {
      const out = await mintOccurrence(selectedId, {
        scope: SCOPE,
        expected_working_version: selected?.working_version ?? 0,
        display_name: spec.display_name,
        source: { kind: "production_revision", revision_id: spec.revision_id },
        visible: true,
        transform: { translation_mm: [0, 0, 0], rotation_udeg: [0, 0, 0] },
      });
      await selectComposition(selectedId);
      return out;
    } catch (e) {
      setError(asApiError(e).message);
    } finally {
      setBusy(false);
    }
  }

  async function handleRename(occurrenceId: string, name: string) {
    if (!selectedId) return;
    setBusy(true);
    try {
      await patchOccurrence(selectedId, occurrenceId, {
        scope: SCOPE,
        expected_working_version: selected?.working_version ?? 0,
        display_name: name,
      });
      await selectComposition(selectedId);
    } catch (e) {
      setError(asApiError(e).message);
    } finally {
      setBusy(false);
    }
  }

  async function handleReplaceAsNew(occurrenceId: string) {
    if (!selectedId) return;
    setBusy(true);
    setError(null);
    setNotice(null);
    try {
      const request = {
        kind: "replace_as_new",
        source_occurrence_ids: [occurrenceId],
        target_working_specs: [],
      };
      const p = await previewIdentityOperation(selectedId, request);
      const out = await applyIdentityOperation(selectedId, {
        scope: SCOPE,
        expected_working_version: p.working_version,
        expected_request_fingerprint: p.request_fingerprint,
        expected_impact_fingerprint: p.impact_fingerprint,
        request,
      });
      await selectComposition(selectedId);
      setNotice(
        `Replaced as new occurrence ${out.target_occurrence_ids[0]}`,
      );
    } catch (e) {
      setError(asApiError(e).message);
    } finally {
      setBusy(false);
    }
  }

  async function handleUpdateSource(occurrenceId: string, revisionId: string) {
    if (!selectedId) return;
    setBusy(true);
    setError(null);
    try {
      await patchOccurrence(selectedId, occurrenceId, {
        scope: SCOPE,
        expected_working_version: selected?.working_version ?? 0,
        source: { kind: "production_revision", revision_id: revisionId },
      });
      await selectComposition(selectedId);
      setNotice(
        "Identity is preserved. Physical/rig/spatial compatibility is not " +
          "certified by this milestone.",
      );
    } catch (e) {
      setError(asApiError(e).message);
    } finally {
      setBusy(false);
    }
  }

  async function handlePublish() {
    if (!selectedId) return;
    setBusy(true);
    setError(null);
    try {
      const result = await publishComposition(
        selectedId, selected?.working_version ?? 0);
      await selectComposition(selectedId);
      setNotice(
        result.created
          ? `Published revision ${result.revision.revision_number} (new)`
          : `Converged on revision ${result.revision.revision_number}`,
      );
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
          <button
            onClick={handlePublish}
            disabled={busy}
            data-testid="publish-composition"
          >
            Publish revision
          </button>

          <ul aria-label="Occurrences" data-testid="occurrence-list">
            {occurrences.map((o) => (
              <li key={o.occurrence_id} data-testid={`occ-${o.occurrence_id}`}>
                <span>{o.display_name}</span>
                <small>{o.occurrence_id}</small>
                <button
                  onClick={() =>
                    void handleRename(o.occurrence_id, `${o.display_name} ✎`)}
                >
                  Update this occurrence
                </button>
                <button
                  onClick={() => void handleUpdateSource(
                    o.occurrence_id, o.production_revision_id ?? "")}
                  title="Identity is preserved. Physical compatibility is not certified."
                >
                  Update source (same identity)
                </button>
                <button
                  onClick={() => void handleReplaceAsNew(o.occurrence_id)}
                  data-testid={`replace-${o.occurrence_id}`}
                >
                  Replace as new occurrence
                </button>
              </li>
            ))}
          </ul>

          {revisions.length > 0 && (
            <ul aria-label="Published revisions">
              {revisions.map((r) => (
                <li key={r.revision_id}>
                  Revision {r.revision_number} · {r.revision_id}
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
    </section>
  );
}
