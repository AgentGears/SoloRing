"use client";

/**
 * M8 §69–70 — VisualFacet workspace + VisualAnchor curation (client
 * island; the server remains the sole authority — APR-050). The working
 * set, captured revisions, and approved authority stay explicitly
 * separated (§70); soft-delete surfaces the server's 409 envelope
 * verbatim rather than hiding the guard.
 */

import { useRouter } from "next/navigation";
import { useState } from "react";

import {
  approveRevision,
  captureRevision,
  createVisualAnchor,
  createVisualFacet,
  deleteVisualAnchor,
  deleteVisualFacet,
  getVisualAnchor,
  listValuePolicies,
  listVisualAnchorRevisions,
  patchVisualFacet,
  putValuePolicies,
  putWorkingSet,
  unapproveAnchor,
} from "@/lib/api.client";
import { asApiError, type ApiError } from "@/lib/api.shared";
import type { Asset, ContinuityFeature, Entity } from "@/lib/types";
import type {
  ValuePolicy,
  VisualAnchor,
  VisualAnchorDetail,
  VisualAnchorRevisionSummary,
  VisualFacet,
} from "@/lib/visualTypes";
import ErrorBanner from "./ErrorBanner";

const ROLES = ["primary", "supporting", "detail", "context"];
const POLICIES = ["required", "optional", "not_applicable"];

function short(id: string | null): string {
  return id ? `${id.slice(0, 8)}…` : "—";
}

/** One editable working row: role select, view-key input, reorder,
 * remove — §70's set primary / set role / set view key / reorder. */
function WorkingItemRow({
  item,
  assetNames,
  onRole,
  onViewKey,
  onMoveUp,
  onMoveDown,
  onRemove,
  first,
  last,
}: {
  item: { asset_id: string; role: string; view_key: string | null };
  assetNames: Record<string, string>;
  onRole: (role: string) => void;
  onViewKey: (view: string) => void;
  onMoveUp: () => void;
  onMoveDown: () => void;
  onRemove: () => void;
  first: boolean;
  last: boolean;
}) {
  return (
    <div className="card row">
      <div>
        <span className="hash">{short(item.asset_id)}</span>
        {assetNames[item.asset_id] ? (
          <span className="meta"> · {assetNames[item.asset_id]}</span>
        ) : null}
      </div>
      <div className="row">
        <select value={item.role} onChange={(e) => onRole(e.target.value)}
                aria-label="role">
          {ROLES.map((r) => (
            <option key={r} value={r}>{r}</option>
          ))}
        </select>
        <input
          placeholder="view key"
          value={item.view_key ?? ""}
          onChange={(e) => onViewKey(e.target.value)}
          aria-label="view key"
          maxLength={64}
        />
        <button className="btn btn-small" onClick={onMoveUp}
                disabled={first} aria-label="Move up">↑</button>
        <button className="btn btn-small" onClick={onMoveDown}
                disabled={last} aria-label="Move down">↓</button>
        <button className="btn btn-small" onClick={onRemove}
                aria-label="Remove item">Remove</button>
      </div>
    </div>
  );
}

function AnchorCuration({
  anchor,
  assets,
  assetNames,
}: {
  anchor: VisualAnchor;
  assets: Asset[];
  assetNames: Record<string, string>;
}) {
  const router = useRouter();
  const [current, setCurrent] = useState<VisualAnchorDetail | null>(null);
  const [draft, setDraft] = useState<
    { asset_id: string; role: string; view_key: string | null }[]
  >([]);
  const [history, setHistory] = useState<VisualAnchorRevisionSummary[]>([]);
  const [addAsset, setAddAsset] = useState("");
  const [addRole, setAddRole] = useState("supporting");
  const [addView, setAddView] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<ApiError | null>(null);

  async function load() {
    if (busy) return;
    setBusy(true);
    setError(null);
    try {
      const detail = await getVisualAnchor(anchor.id);
      setCurrent(detail);
      setDraft(detail.items.map((it) => ({
        asset_id: it.asset_id, role: it.role, view_key: it.view_key,
      })));
      setHistory(await listVisualAnchorRevisions(anchor.id));
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

  function mutateDraft(fn: (d: typeof draft) => typeof draft) {
    setDraft(fn(draft));
  }

  async function saveWorking() {
    if (busy || current === null) return;
    setBusy(true);
    setError(null);
    try {
      const detail = await putWorkingSet(anchor.id, draft);
      setCurrent(detail);
      setDraft(detail.items.map((it) => ({
        asset_id: it.asset_id, role: it.role, view_key: it.view_key,
      })));
      router.refresh();
    } catch (err) {
      setError(asApiError(err));
    } finally {
      setBusy(false);
    }
  }

  async function captureOnly() {
    if (busy) return;
    setBusy(true);
    setError(null);
    try {
      await captureRevision(anchor.id);
      setHistory(await listVisualAnchorRevisions(anchor.id));
      router.refresh();
    } catch (err) {
      setError(asApiError(err));
    } finally {
      setBusy(false);
    }
  }

  async function approveFromHistory(revisionId: string) {
    if (busy || current === null) return;
    setBusy(true);
    setError(null);
    try {
      await approveRevision(revisionId, current.approved_revision_id);
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

  async function softDelete() {
    if (busy) return;
    setBusy(true);
    setError(null);
    try {
      await deleteVisualAnchor(anchor.id);
      router.refresh();
    } catch (err) {
      setError(asApiError(err));
    } finally {
      setBusy(false);
    }
  }

  const available = assets.filter(
    (a) => !draft.some((d) => d.asset_id === a.id),
  );
  const primary = draft.find((d) => d.role === "primary");

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

      {draft.map((it, i) => (
        <WorkingItemRow
          key={it.asset_id}
          item={it}
          assetNames={assetNames}
          first={i === 0}
          last={i === draft.length - 1}
          onRole={(role) => mutateDraft((d) =>
            d.map((x, j) => (j === i ? { ...x, role } : x)))}
          onViewKey={(view) => mutateDraft((d) =>
            d.map((x, j) =>
              j === i ? { ...x, view_key: view.trim() || null } : x))}
          onMoveUp={() => mutateDraft((d) => {
            if (i === 0) return d;
            const copy = [...d];
            [copy[i - 1], copy[i]] = [copy[i], copy[i - 1]];
            return copy;
          })}
          onMoveDown={() => mutateDraft((d) => {
            if (i === d.length - 1) return d;
            const copy = [...d];
            [copy[i + 1], copy[i]] = [copy[i], copy[i + 1]];
            return copy;
          })}
          onRemove={() => mutateDraft((d) => d.filter((_, j) => j !== i))}
        />
      ))}

      <div className="card row">
        <select value={addAsset} onChange={(e) => setAddAsset(e.target.value)}
                aria-label="asset to add">
          <option value="">add existing/generated Asset…</option>
          {available.map((a) => (
            <option key={a.id} value={a.id}>
              {a.original_filename ?? a.id.slice(0, 8)}
            </option>
          ))}
        </select>
        <select value={addRole} onChange={(e) => setAddRole(e.target.value)}
                aria-label="role for new item">
          {ROLES.map((r) => (
            <option key={r} value={r}>{r}</option>
          ))}
        </select>
        <input
          placeholder="view key"
          value={addView}
          onChange={(e) => setAddView(e.target.value)}
          maxLength={64}
        />
        <button
          className="btn"
          disabled={busy || !addAsset}
          onClick={() => {
            mutateDraft((d) => [...d, {
              asset_id: addAsset, role: addRole,
              view_key: addView.trim() || null,
            }]);
            setAddAsset("");
            setAddView("");
          }}
        >
          Add to working set
        </button>
      </div>

      <div className="meta">
        primary reference:{" "}
        {primary ? <span className="hash">{short(primary.asset_id)}</span> : "none set"}
        {" · "}
        {draft.length === 0
          ? "no working items"
          : `${draft.length} reference${draft.length === 1 ? "" : "s"}`}
      </div>

      {error ? (
        <ErrorBanner error={error} onDismiss={() => setError(null)} />
      ) : null}

      <div className="row">
        <button className="btn" onClick={saveWorking} disabled={busy}>
          Save working set
        </button>{" "}
        <button className="btn" onClick={captureOnly} disabled={busy}>
          Capture revision
        </button>{" "}
        {current.approved_revision_id ? (
          <button className="btn" onClick={unapprove} disabled={busy}>
            Unapprove
          </button>
        ) : null}{" "}
        <button className="btn" onClick={softDelete} disabled={busy}>
          Delete realization
        </button>
      </div>

      <h4>Revision history</h4>
      {history.length === 0 ? (
        <div className="meta">No captured revisions yet.</div>
      ) : (
        history.map((h) => (
          <div className="card row" key={h.id}>
            <div>
              <strong>revision {h.revision_number}</strong>
              <div className="meta">
                <span className="hash">{h.snapshot_hash.slice(0, 12)}…</span>
                {" · "}{h.created_at}
                {current.approved_revision_id === h.id
                  ? " · APPROVED authority"
                  : ""}
              </div>
            </div>
            {current.approved_revision_id === h.id ? null : (
              <button
                className="btn"
                onClick={() => approveFromHistory(h.id)}
                disabled={busy}
              >
                Approve
              </button>
            )}
          </div>
        ))
      )}
    </div>
  );
}

/** §69 feature-value policy editor (PUT full set). */
function ValuePolicyEditor({
  facetId,
  enumValues,
}: {
  facetId: string;
  enumValues: string[];
}) {
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const [policies, setPolicies] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<ApiError | null>(null);

  async function load() {
    setBusy(true);
    setError(null);
    try {
      const rows = await listValuePolicies(facetId);
      setPolicies(Object.fromEntries(
        rows.map((r: ValuePolicy) => [r.feature_value_json, r.policy]),
      ));
      setOpen(true);
    } catch (err) {
      setError(asApiError(err));
    } finally {
      setBusy(false);
    }
  }

  async function save(values: string[]) {
    if (busy) return;
    setBusy(true);
    setError(null);
    try {
      await putValuePolicies(
        facetId,
        values.map((v) => ({ value: v, policy: policies[v] ?? "required" })),
      );
      router.refresh();
    } catch (err) {
      setError(asApiError(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div>
      <button className="btn btn-small" onClick={load} disabled={busy}>
        Value policies…
      </button>
      {error ? (
        <ErrorBanner error={error} onDismiss={() => setError(null)} />
      ) : null}
      {open ? (
        <PolicyEditorBody
          enumValues={enumValues}
          policies={policies}
          setPolicies={setPolicies}
          busy={busy}
          onSave={save}
        />
      ) : null}
    </div>
  );
}

function PolicyEditorBody({
  enumValues,
  policies,
  setPolicies,
  busy,
  onSave,
}: {
  enumValues: string[];
  policies: Record<string, string>;
  setPolicies: (p: Record<string, string>) => void;
  busy: boolean;
  onSave: (values: string[]) => void;
}) {
  return (
    <div className="card">
      {enumValues.length === 0 ? (
        <div className="meta">
          The owning feature exposes no enum values to override.
        </div>
      ) : (
        enumValues.map((v) => (
          <div className="card row" key={v}>
            <div>{v}</div>
            <select
              value={policies[v] ?? "required"}
              onChange={(e) =>
                setPolicies({ ...policies, [v]: e.target.value })
              }
              aria-label={`policy for ${v}`}
            >
              {POLICIES.map((p) => (
                <option key={p} value={p}>{p}</option>
              ))}
            </select>
          </div>
        ))
      )}
      <button
        className="btn"
        disabled={busy}
        onClick={() => onSave(enumValues)}
      >
        Save value policies
      </button>
    </div>
  );
}

function FacetRow({
  facet,
  anchors,
  entities,
  featuresByEntity,
  assets,
  assetNames,
}: {
  facet: VisualFacet;
  anchors: VisualAnchor[];
  entities: Entity[];
  featuresByEntity: Record<string, ContinuityFeature[]>;
  assets: Asset[];
  assetNames: Record<string, string>;
}) {
  const router = useRouter();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<ApiError | null>(null);
  const [openAnchor, setOpenAnchor] = useState<string | null>(null);
  const [createValue, setCreateValue] = useState("");

  const entity = facet.entity_id
    ? entities.find((e) => e.id === facet.entity_id)
    : undefined;
  // §69: a FEATURE facet's visual context is its OWNING entity — derived
  // through the feature, because feature facets carry entity_id = null.
  const ownerEntity = facet.feature_id
    ? entities.find((e) =>
        (featuresByEntity[e.id] ?? []).some(
          (fw) => fw.id === facet.feature_id,
        ),
      )
    : undefined;
  const contextEntity = entity ?? ownerEntity;
  const contextRevision = contextEntity?.approved_revision_id ?? null;
  const features = facet.entity_id
    ? featuresByEntity[facet.entity_id] ?? []
    : [];
  const feature = facet.feature_id
    ? Object.values(featuresByEntity).flat().find(
        (f) => f.id === facet.feature_id,
      )
    : undefined;
  const enumValues: string[] = (() => {
    if (!feature?.enum_values_json) return [];
    try {
      const parsed = JSON.parse(feature.enum_values_json);
      return Array.isArray(parsed) ? parsed.map(String) : [];
    } catch {
      return [];
    }
  })();

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

  /** §69: create a realization for the current EntityRevision / current
   * Feature value — the server derives and validates the exact state
   * binding; nothing is captured or approved here. Feature facets take
   * their visual context from the OWNING entity (feature facets carry
   * entity_id = null). */
  async function createRealization() {
    if (busy) return;
    setBusy(true);
    setError(null);
    try {
      if (facet.target_kind === "entity") {
        if (!entity?.approved_revision_id) {
          throw new Error(
            "The entity has no approved revision to realize.",
          );
        }
        await createVisualAnchor(facet.id, {
          entity_revision_id: entity.approved_revision_id,
        });
      } else {
        if (!contextRevision || !createValue) {
          throw new Error(
            "Pick a feature value (the owning entity needs an approved revision).",
          );
        }
        await createVisualAnchor(facet.id, {
          value: createValue,
          visual_context_entity_revision_id: contextRevision,
        });
      }
      setCreateValue("");
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
            <span className="meta">
              ({facet.target_kind}
              {entity ? `: ${entity.name}` : ""})
            </span>
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
          {facet.target_kind === "feature" ? (
            <ValuePolicyEditor facetId={facet.id} enumValues={enumValues} />
          ) : null}{" "}
          <button
            className="btn"
            onClick={createRealization}
            disabled={
              busy ||
              (facet.target_kind === "entity"
                ? !entity?.approved_revision_id
                : !contextRevision || !createValue)
            }
          >
            Create realization for current state
          </button>{" "}
          <button className="btn" onClick={removeFacet} disabled={busy}>
            Delete facet
          </button>
        </div>
      </div>
      {facet.target_kind === "feature" && enumValues.length > 0 ? (
        <div className="card row">
          <span className="meta">realization value:</span>
          <select
            value={createValue}
            onChange={(e) => setCreateValue(e.target.value)}
            aria-label="feature value to realize"
          >
            <option value="">pick value…</option>
            {enumValues.map((v) => (
              <option key={v} value={v}>{v}</option>
            ))}
          </select>
        </div>
      ) : null}
      {anchors.map((anchor) => (
        <div key={anchor.id}>
          <div className="card row">
            <div>
              <strong>
                {anchor.entity_revision_id
                  ? `EntityRevision ${short(anchor.entity_revision_id)}`
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
            <AnchorCuration
              anchor={anchor}
              assets={assets}
              assetNames={assetNames}
            />
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
  entities,
  featuresByEntity,
  assets,
}: {
  projectId: string;
  facets: VisualFacet[];
  anchorsByFacet: Record<string, VisualAnchor[]>;
  entities: Entity[];
  featuresByEntity: Record<string, ContinuityFeature[]>;
  assets: Asset[];
}) {
  const router = useRouter();
  const [targetKind, setTargetKind] = useState("entity");
  const [targetId, setTargetId] = useState("");
  const [facetKey, setFacetKey] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<ApiError | null>(null);

  const assetNames = Object.fromEntries(
    assets.map((a) => [a.id, a.original_filename ?? a.id.slice(0, 8)]),
  );
  const allFeatures = Object.values(featuresByEntity).flat();

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (busy) return;
    setBusy(true);
    setError(null);
    try {
      await createVisualFacet(projectId, {
        target_kind: targetKind,
        facet_key: facetKey.trim(),
        ...(targetKind === "entity"
          ? { entity_id: targetId || undefined }
          : { feature_id: targetId || undefined }),
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
            entities={entities}
            featuresByEntity={featuresByEntity}
            assets={assets}
            assetNames={assetNames}
          />
        ))
      )}
      <form className="card form-row" onSubmit={submit}>
        {error ? (
          <ErrorBanner error={error} onDismiss={() => setError(null)} />
        ) : null}
        <select
          value={targetKind}
          onChange={(e) => {
            setTargetKind(e.target.value);
            setTargetId("");
          }}
          aria-label="target kind"
        >
          <option value="entity">entity</option>
          <option value="feature">feature</option>
        </select>
        <select
          value={targetId}
          onChange={(e) => setTargetId(e.target.value)}
          aria-label="target"
          required
        >
          <option value="">pick target…</option>
          {targetKind === "entity"
            ? entities.map((en) => (
                <option key={en.id} value={en.id}>
                  {en.name} ({en.kind})
                </option>
              ))
            : allFeatures.map((f) => (
                <option key={f.id} value={f.id}>
                  {f.key}
                </option>
              ))}
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
          disabled={busy || !facetKey.trim() || !targetId}
        >
          Create facet
        </button>
      </form>
    </section>
  );
}
