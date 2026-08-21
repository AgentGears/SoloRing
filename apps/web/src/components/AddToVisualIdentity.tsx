"use client";

/**
 * M8 §71 — Generated Take promotion: "Add to Visual Identity…".
 *
 * The user chooses the VisualFacet/VisualAnchor target; the output
 * Asset joins the target's WORKING set only — no revision is captured
 * and no approval occurs here. The authority chain stays explicit.
 */

import { useRouter } from "next/navigation";
import { useState } from "react";

import { getVisualAnchor, putWorkingSet } from "@/lib/api.client";
import { asApiError, type ApiError } from "@/lib/api.shared";
import type {
  VisualAnchor,
  VisualFacet,
} from "@/lib/visualTypes";
import ErrorBanner from "./ErrorBanner";

const ROLES = ["supporting", "detail", "context", "primary"];

export default function AddToVisualIdentity({
  assetId,
  facets,
  anchorsByFacet,
}: {
  assetId: string;
  facets: VisualFacet[];
  anchorsByFacet: Record<string, VisualAnchor[]>;
}) {
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const [facetId, setFacetId] = useState("");
  const [anchorId, setAnchorId] = useState("");
  const [role, setRole] = useState("supporting");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<ApiError | null>(null);
  const [done, setDone] = useState(false);

  const anchors = facetId ? anchorsByFacet[facetId] ?? [] : [];

  async function add() {
    if (busy || !anchorId) return;
    setBusy(true);
    setError(null);
    try {
      const detail = await getVisualAnchor(anchorId);
      // Working state ONLY (§71): append, save, and stop — capture and
      // approval remain separate explicit acts.
      await putWorkingSet(anchorId, [
        ...detail.items.map((it) => ({
          asset_id: it.asset_id,
          role: it.role,
          view_key: it.view_key,
        })),
        { asset_id: assetId, role, view_key: null },
      ]);
      setDone(true);
      router.refresh();
    } catch (err) {
      setError(asApiError(err));
    } finally {
      setBusy(false);
    }
  }

  if (done) {
    return (
      <span className="meta">
        added to working set — capture/approval remain explicit
      </span>
    );
  }

  return (
    <div>
      <button className="btn btn-small" onClick={() => setOpen(!open)}>
        Add to Visual Identity…
      </button>
      {open ? (
        <div className="card">
          <div className="meta">
            Working state only: no revision is captured and no approval
            occurs automatically.
          </div>
          <div className="row">
            <select
              value={facetId}
              onChange={(e) => {
                setFacetId(e.target.value);
                setAnchorId("");
              }}
              aria-label="visual facet"
            >
              <option value="">facet…</option>
              {facets.map((f) => (
                <option key={f.id} value={f.id}>
                  {f.facet_key} ({f.target_kind})
                </option>
              ))}
            </select>
            <select
              value={anchorId}
              onChange={(e) => setAnchorId(e.target.value)}
              aria-label="state realization"
              disabled={!facetId}
            >
              <option value="">realization…</option>
              {anchors.map((a) => (
                <option key={a.id} value={a.id}>
                  {a.entity_revision_id
                    ? `revision ${a.entity_revision_id.slice(0, 8)}…`
                    : `value ${a.feature_value_json}`}
                </option>
              ))}
            </select>
            <select
              value={role}
              onChange={(e) => setRole(e.target.value)}
              aria-label="role"
            >
              {ROLES.map((r) => (
                <option key={r} value={r}>{r}</option>
              ))}
            </select>
            <button
              className="btn"
              onClick={add}
              disabled={busy || !anchorId}
            >
              Add to working set
            </button>
          </div>
          {error ? (
            <ErrorBanner error={error} onDismiss={() => setError(null)} />
          ) : null}
        </div>
      ) : null}
    </div>
  );
}
