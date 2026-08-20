"use client";

/**
 * M8 §69–70 — VisualFacet workspace + anchor curation (client island;
 * server remains the sole authority — APR-050).
 */

import { useRouter } from "next/navigation";
import { useState } from "react";

import {
  approveRevision,
  captureRevision,
  createVisualFacet,
  deleteVisualFacet,
  getVisualAnchor,
  patchVisualFacet,
  putWorkingSet,
  unapproveAnchor,
} from "@/lib/api.client";
import { asApiError, type ApiError } from "@/lib/api.shared";
import type { VisualFacet } from "@/lib/visualTypes";
import type { VisualAnchor, VisualAnchorDetail } from "@/lib/visualTypes";
import ErrorBanner from "./ErrorBanner";

const ROLES = ["primary", "supporting", "detail", "context"];

function AnchorCuration({ anchor }: { anchor: VisualAnchor }) {
  const router = useRouter();
  const [current, setCurrent] = useState<VisualAnchorDetail | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<ApiError | null>(null);
  const [selected, setSelected] = useState<Record<string, string>>({});

  async function load() {
    if (busy) return;
    setBusy(true);
    setError(null);
    try {
      setCurrent(await getVisualAnchor(anchor.id));
    } catch (err) {
      setError(asApiError(err));
    } finally {
      setBusy(false);
    }
  }

  if (current === null) {
    return (
      <div className="card row">
        <button className="btn" onClick={load} disabled={busy}>
          Load working state
        </button>
        {error ? (
          <ErrorBanner error={error} onDismiss={() => setError(null)} />
        ) : null}
      </div>
    );
  }

  async function saveWorking() {
    if (busy || current === null) return;
    setBusy(true);
    setError(null);
    try {
      const items = current.items.map((it) => ({
        asset_id: it.asset_id,
        role: selected[it.asset_id] ?? it.role,
        view_key: it.view_key,
      }));
      setCurrent(await putWorkingSet(anchor.id, items));
      router.refresh();
    } catch (err) {
      setError(asApiError(err));
    } finally {
      setBusy(false);
    }
  }

  async function captureAndApprove() {
    if (busy || current === null) return;
    setBusy(true);
    setError(null);
    try {
      const rev = await captureRevision(anchor.id);
      await approveRevision(rev.id, current.approved_revision_id);
      setCurrent(await getVisualAnchor(anchor.id));
      router.refresh();
    } catch (err) {
      setError(asApiError(err));
    } finally {
      setBusy(false);
    }
  }

  async function unapprove() {
    if (busy || current === null) return;
    setBusy(true);
    setError(null);
    try {
      await unapproveAnchor(anchor.id, current.approved_revision_id);
      setCurrent(await getVisualAnchor(anchor.id));
      router.refresh();
    } catch (err) {
      setError(asApiError(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="card">
      <div className="meta">
        working{" "}
        <span className="hash">
          {current.working_snapshot_hash?.slice(0, 12) ?? "unresolved"}…
        </span>
        {" · "}
        approved{" "}
        <span className="hash">
          {current.approved_snapshot_hash?.slice(0, 12) ?? "none"}…
        </span>
        {current.working_state_differs_from_approved === true
          ? " · working DIFFERS from approved"
          : ""}
      </div>
      {current.items.map((it) => (
        <div className="card row" key={it.asset_id}>
          <div>
            <span className="hash">{it.asset_id.slice(0, 8)}…</span> ·{" "}
            {it.view_key ?? "no view"}
          </div>
          <select
            value={selected[it.asset_id] ?? it.role}
            onChange={(e) =>
              setSelected({ ...selected, [it.asset_id]: e.target.value })
            }
          >
            {ROLES.map((r) => (
              <option key={r} value={r}>
                {r}
              </option>
            ))}
          </select>
        </div>
      ))}
      {error ? (
        <ErrorBanner error={error} onDismiss={() => setError(null)} />
      ) : null}
      <div className="row">
        <button className="btn" onClick={saveWorking} disabled={busy}>
          Save working set
        </button>{" "}
        <button className="btn" onClick={captureAndApprove} disabled={busy}>
          Capture + approve revision
        </button>{" "}
        {current.approved_revision_id ? (
          <button className="btn" onClick={unapprove} disabled={busy}>
            Unapprove
          </button>
        ) : null}
      </div>
    </div>
  );
}

function FacetRow({
  facet,
  anchors,
}: {
  facet: VisualFacet;
  anchors: VisualAnchor[];
}) {
  const router = useRouter();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<ApiError | null>(null);
  const [openAnchor, setOpenAnchor] = useState<string | null>(null);

  async function toggleRequirement() {
    if (busy) return;
    setBusy(true);
    setError(null);
    try {
      await patchVisualFacet(facet.id, {
        requirement:
          facet.requirement === "required" ? "optional" : "required",
      });
      router.refresh();
    } catch (err) {
      setError(asApiError(err));
    } finally {
      setBusy(false);
    }
  }

  async function removeFacet() {
    if (busy) return;
    setBusy(true);
    setError(null);
    try {
      await deleteVisualFacet(facet.id);
      router.refresh();
    } catch (err) {
      setError(asApiError(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div>
      <div className="card row">
        <div>
          <strong>
            {facet.facet_key}{" "}
            <span className="meta">({facet.target_kind})</span>
          </strong>
          <div className="meta">
            {facet.requirement === "required" ? "✓ required" : "○ optional"}
            {facet.label ? ` · ${facet.label}` : ""}
            {anchors.length > 0
              ? ` · ${anchors.length} realization${anchors.length === 1 ? "" : "s"}`
              : ""}
          </div>
          {error ? (
            <ErrorBanner error={error} onDismiss={() => setError(null)} />
          ) : null}
        </div>
        <div>
          <button className="btn" onClick={toggleRequirement} disabled={busy}>
            {facet.requirement === "required" ? "→ optional" : "→ required"}
          </button>{" "}
          <button className="btn" onClick={removeFacet} disabled={busy}>
            Delete facet
          </button>
        </div>
      </div>
      {anchors.map((anchor) => (
        <div key={anchor.id}>
          <div className="card row">
            <div>
              <strong>
                {anchor.entity_revision_id
                  ? `EntityRevision ${anchor.entity_revision_id.slice(0, 8)}…`
                  : `value ${anchor.feature_value_json}`}
              </strong>
              <div className="meta">
                {anchor.approved_revision_id
                  ? "APPROVED authority"
                  : "no approved revision"}
              </div>
            </div>
            <button
              className="btn"
              onClick={() =>
                setOpenAnchor(openAnchor === anchor.id ? null : anchor.id)
              }
            >
              {openAnchor === anchor.id ? "Close" : "Curate"}
            </button>
          </div>
          {openAnchor === anchor.id ? (
            <AnchorCuration anchor={anchor} />
          ) : null}
        </div>
      ))}
    </div>
  );
}

export function VisualIdentityPanel({
  projectId,
  facets,
  anchorsByFacet,
}: {
  projectId: string;
  facets: VisualFacet[];
  anchorsByFacet: Record<string, VisualAnchor[]>;
}) {
  const router = useRouter();
  const [targetKind, setTargetKind] = useState("entity");
  const [facetKey, setFacetKey] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<ApiError | null>(null);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (busy) return;
    setBusy(true);
    setError(null);
    try {
      await createVisualFacet(projectId, {
        target_kind: targetKind,
        facet_key: facetKey.trim(),
      });
      setFacetKey("");
      router.refresh();
    } catch (err) {
      setError(asApiError(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <section>
      {facets.length === 0 ? (
        <div className="empty">No visual facets yet.</div>
      ) : (
        facets.map((f) => (
          <FacetRow
            key={f.id}
            facet={f}
            anchors={anchorsByFacet[f.id] ?? []}
          />
        ))
      )}
      <form className="card form-row" onSubmit={submit}>
        {error ? (
          <ErrorBanner error={error} onDismiss={() => setError(null)} />
        ) : null}
        <select
          value={targetKind}
          onChange={(e) => setTargetKind(e.target.value)}
        >
          <option value="entity">entity</option>
          <option value="feature">feature</option>
        </select>
        <input
          placeholder="facet key"
          value={facetKey}
          onChange={(e) => setFacetKey(e.target.value)}
          required
        />
        <button
          className="btn"
          type="submit"
          disabled={busy || !facetKey.trim()}
        >
          Create facet
        </button>
      </form>
    </section>
  );
}
