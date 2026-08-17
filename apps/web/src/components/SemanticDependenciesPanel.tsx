"use client";

// Semantic dependencies panel (M6C plan §50/§81): the Shot's WORKING
// dependency set on Story World entity identities, resolved against the
// currently approved revisions. Deliberately a SEPARATE section from
// Reference Assets — semantic canon vs representational evidence; the UI
// must not visually imply they are the same concept.

import { useRouter } from "next/navigation";
import { useState } from "react";

import { putSemanticDependencies } from "@/lib/api.client";
import { asApiError, type ApiError } from "@/lib/api.shared";
import type { Entity, SemanticDependency } from "@/lib/types";
import ErrorBanner from "./ErrorBanner";

export function SemanticDependenciesPanel({
  shotId,
  initialDependencies,
  entities,
}: {
  shotId: string;
  initialDependencies: SemanticDependency[];
  entities: Entity[];
}) {
  const router = useRouter();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<ApiError | null>(null);
  const [entityId, setEntityId] = useState("");
  const [role, setRole] = useState("");

  const ordered = [...initialDependencies].sort(
    (a, b) => a.role.localeCompare(b.role) || a.position - b.position,
  );
  const currentSet = ordered.map((d) => ({
    entity_id: d.entity_id,
    role: d.role,
  }));

  async function replace(next: { entity_id: string; role: string }[]) {
    if (busy) return;
    setBusy(true);
    setError(null);
    try {
      await putSemanticDependencies(shotId, next);
      router.refresh();
    } catch (err) {
      setError(asApiError(err));
    } finally {
      setBusy(false);
    }
  }

  async function add() {
    if (!entityId || !role.trim()) return;
    await replace([...currentSet, { entity_id: entityId, role: role.trim() }]);
    setEntityId("");
    setRole("");
  }

  return (
    <div>
      <p className="meta">
        Semantic canon: entity identities resolved against their currently
        approved design revisions at capture time. Distinct from reference
        assets below.
      </p>
      {error ? (
        <ErrorBanner error={error} onDismiss={() => setError(null)} />
      ) : null}
      {ordered.length === 0 ? (
        <div className="empty">No semantic dependencies.</div>
      ) : (
        ordered.map((d) => (
          <div className="card row" key={`${d.entity_id}:${d.role}`}>
            <div>
              <strong>{d.entity_name ?? d.entity_id}</strong>{" "}
              <span className="meta">({d.entity_kind})</span>
              <div className="meta">
                role: {d.role} · revision {d.resolved_revision_number} ·{" "}
                <span className="hash">
                  {d.resolved_revision_hash.slice(0, 12)}…
                </span>
              </div>
            </div>
            <button
              className="btn btn-small"
              onClick={() =>
                replace(
                  currentSet.filter(
                    (c) =>
                      !(c.entity_id === d.entity_id && c.role === d.role),
                  ),
                )
              }
              disabled={busy}
              aria-label={`Remove ${d.entity_name ?? d.entity_id}`}
            >
              ✕
            </button>
          </div>
        ))
      )}
      <div className="card form-row">
        <select
          value={entityId}
          onChange={(e) => setEntityId(e.target.value)}
          aria-label="Entity"
        >
          <option value="">Entity…</option>
          {entities
            .filter((e) => e.approved_revision_id)
            .map((e) => (
              <option key={e.id} value={e.id}>
                {e.name} ({e.kind})
              </option>
            ))}
        </select>
        <input
          placeholder="role (e.g. subject)"
          value={role}
          onChange={(e) => setRole(e.target.value)}
          maxLength={64}
        />
        <button
          className="btn"
          onClick={add}
          disabled={busy || !entityId || !role.trim()}
        >
          Attach
        </button>
      </div>
    </div>
  );
}
