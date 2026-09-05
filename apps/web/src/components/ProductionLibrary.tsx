"use client";

/**
 * Minimal Production Library (M11 frozen R3 §15): create Production Object →
 * choose existing candidate Asset → readiness preview → Publish → immutable
 * revision inspection. Candidate Asset ≠ published revision; source
 * provenance ≠ consumption closure — rendered as distinct sections. No
 * rich authoring surface, no representation switching.
 */

import { useCallback, useEffect, useMemo, useState } from "react";

import { asApiError, type ApiError } from "@/lib/api.shared";
import {
  createProductionObject,
  getProductionRevision,
  getPublicationReadiness,
  listAssets,
  listProductionObjects,
  listProductionRevisions,
  publishProductionRevision,
} from "@/lib/api.client";
import type {
  Asset,
  ProductionObject,
  ProductionRevisionDetail,
  ProductionRevisionSummary,
  PublicationReadiness,
} from "@/lib/types";

// Candidate selection uses the existing Project Asset surface; a tiny local
// loader keeps this component self-contained without a second upload path.
function useStateAssets(projectId: string): Asset[] {
  const [assets, setAssets] = useState<Asset[]>([]);
  useEffect(() => {
    let cancelled = false;
    listAssets(projectId)
      .then((list) => {
        if (!cancelled) setAssets(list);
      })
      .catch(() => {
        if (!cancelled) setAssets([]);
      });
    return () => {
      cancelled = true;
    };
  }, [projectId]);
  return assets;
}

export default function ProductionLibrary({ projectId }: { projectId: string }) {
  const [objects, setObjects] = useState<ProductionObject[]>([]);
  const [selectedObjectId, setSelectedObjectId] = useState<string | null>(null);
  const [newName, setNewName] = useState("");
  const [candidateAssetId, setCandidateAssetId] = useState("");
  const [readiness, setReadiness] = useState<PublicationReadiness | null>(null);
  const [revisions, setRevisions] = useState<ProductionRevisionSummary[]>([]);
  const [detail, setDetail] = useState<ProductionRevisionDetail | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const selectedObject = useMemo(
    () => objects.find((o) => o.id === selectedObjectId) ?? null,
    [objects, selectedObjectId],
  );

  const loadObjects = useCallback(async () => {
    try {
      setObjects(await listProductionObjects(projectId));
    } catch (e) {
      setError(asApiError(e).message);
    }
  }, [projectId]);

  useEffect(() => {
    void loadObjects();
  }, [loadObjects]);

  async function handleCreate() {
    setBusy(true);
    setError(null);
    try {
      const obj = await createProductionObject(projectId, newName.trim(), null);
      setNewName("");
      await loadObjects();
      setSelectedObjectId(obj.id);
    } catch (e) {
      setError(asApiError(e).message);
    } finally {
      setBusy(false);
    }
  }

  async function handleReadiness() {
    if (!selectedObjectId || !candidateAssetId) return;
    setBusy(true);
    setError(null);
    setDetail(null);
    try {
      setReadiness(
        await getPublicationReadiness(selectedObjectId, candidateAssetId),
      );
    } catch (e) {
      setError(asApiError(e).message);
    } finally {
      setBusy(false);
    }
  }

  async function handlePublish() {
    if (!selectedObjectId || !candidateAssetId) return;
    setBusy(true);
    setError(null);
    try {
      const published = await publishProductionRevision(
        selectedObjectId,
        candidateAssetId,
      );
      setRevisions(await listProductionRevisions(selectedObjectId));
      setDetail(await getProductionRevision(published.revision_id));
      setReadiness(null);
    } catch (e) {
      setError(asApiError(e).message);
    } finally {
      setBusy(false);
    }
  }

  async function loadRevisions(objectId: string) {
    setSelectedObjectId(objectId);
    setReadiness(null);
    setDetail(null);
    try {
      setRevisions(await listProductionRevisions(objectId));
    } catch (e) {
      setError(asApiError(e).message);
    }
  }

  const assetsState = useStateAssets(projectId);
  const blockers = readiness && !readiness.ready ? readiness.issues : [];

  return (
    <section aria-label="Production Library" data-testid="production-library">
      <h2>Production Library</h2>
      {error && (
        <p role="alert" data-testid="production-error">
          {error}
        </p>
      )}

      <div>
        <label htmlFor="new-object-name">New Production Object name</label>
        <input
          id="new-object-name"
          value={newName}
          onChange={(e) => setNewName(e.target.value)}
          placeholder="Reception Desk"
        />
        <button onClick={handleCreate} disabled={busy || !newName.trim()}>
          Create Production Object
        </button>
      </div>

      {objects.length > 0 && (
        <ul aria-label="Production Objects">
          {objects.map((o) => (
            <li key={o.id}>
              <button onClick={() => void loadRevisions(o.id)}>
                {o === selectedObject ? "▸ " : ""}
                {o.name}
              </button>
              {/* Duplicate display names never become identity: the stable
                  id is always shown as the disambiguator. */}
              <small data-testid={`object-id-${o.id}`}>{o.id}</small>
            </li>
          ))}
        </ul>
      )}

      {selectedObject && (
        <div>
          <h3>
            Production Object: {selectedObject.name} ({selectedObject.id})
          </h3>

          <label htmlFor="candidate-asset">Candidate Asset</label>
          <select
            id="candidate-asset"
            value={candidateAssetId}
            onChange={(e) => {
              setCandidateAssetId(e.target.value);
              setReadiness(null);
            }}
          >
            <option value="">— choose a candidate Asset —</option>
            {assetsState.map((a) => (
              <option key={a.id} value={a.id}>
                {a.original_filename ?? a.id} ({a.kind}, {a.blob_hash.slice(0, 12)}…)
              </option>
            ))}
          </select>
          <button
            onClick={handleReadiness}
            disabled={busy || !candidateAssetId}
          >
            Preview Readiness
          </button>

          {readiness && readiness.ready && readiness.closure && (
            <div data-testid="readiness-ready">
              <h4>Publication readiness: ready</h4>
              <p data-testid="proposed-snapshot-hash">
                proposed snapshot hash: {readiness.proposed_snapshot_hash}
              </p>
              <dl data-testid="proposed-closure">
                <dt>consumption closure</dt>
                <dd>
                  {readiness.closure.contract_key}/v
                  {readiness.closure.contract_version} · blob{" "}
                  {readiness.closure.blob_hash} ·{" "}
                  {readiness.closure.size_bytes} bytes ·{" "}
                  {readiness.closure.media_type ?? "no media type"}
                </dd>
              </dl>
            </div>
          )}

          {blockers.length > 0 && (
            <ul data-testid="readiness-blockers" aria-label="readiness blockers">
              {blockers.map((issue) => (
                <li key={issue.code}>
                  {issue.code}: {issue.message}
                </li>
              ))}
            </ul>
          )}

          <button
            onClick={handlePublish}
            disabled={busy || !readiness?.ready}
            data-testid="publish-button"
          >
            Publish
          </button>

          {revisions.length > 0 && (
            <ul aria-label="Published revisions">
              {revisions.map((r) => (
                <li key={r.revision_id}>
                  Revision {r.revision_number} · {r.revision_id} · hash{" "}
                  {r.snapshot_hash.slice(0, 16)}…
                </li>
              ))}
            </ul>
          )}

          {detail && (
            <div data-testid="revision-detail">
              <h4>
                Revision {detail.revision_number} — {detail.revision_id}
              </h4>
              <dl data-testid="consumption-closure">
                <dt>retained_blob/v{detail.closure.contract_version} closure</dt>
                <dd>
                  blob {detail.closure.blob_hash} ·{" "}
                  {detail.closure.size_bytes} bytes ·{" "}
                  {detail.closure.media_type ?? "no media type"}
                </dd>
                <dt>canonical snapshot hash</dt>
                <dd>{detail.snapshot_hash}</dd>
                <dt>physical integrity</dt>
                <dd>{detail.physical_integrity}</dd>
              </dl>
              <ul data-testid="source-provenance" aria-label="source provenance">
                {detail.sources.map((s) => (
                  <li key={s.asset_id}>source Asset {s.asset_id}</li>
                ))}
              </ul>
            </div>
          )}
        </div>
      )}
    </section>
  );
}
