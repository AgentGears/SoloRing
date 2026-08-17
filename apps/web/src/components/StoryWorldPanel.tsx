"use client";

// Story World surface (M6A plan §29): identity, immutable revision history,
// explicit approval. No story-state or realization controls exist here.

import { useRouter } from "next/navigation";
import Link from "next/link";
import { useState } from "react";

import {
  approveEntityRevision,
  createEntity,
  createEntityRevision,
  patchEntity,
} from "@/lib/api.client";
import { asApiError, type ApiError } from "@/lib/api.shared";
import type { Entity, EntityRevisionSummary } from "@/lib/types";
import ErrorBanner from "./ErrorBanner";

const KINDS = ["character", "location", "prop", "costume", "vehicle"] as const;

const KIND_LABELS: Record<string, string> = {
  character: "Characters",
  location: "Locations",
  prop: "Props",
  costume: "Costumes",
  vehicle: "Vehicles",
};

export function StoryWorldPanel({
  projectId,
  entities,
}: {
  projectId: string;
  entities: Entity[];
}) {
  const router = useRouter();
  const [kind, setKind] = useState<string>("character");
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<ApiError | null>(null);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (busy) return;
    setBusy(true);
    setError(null);
    try {
      await createEntity(projectId, kind, name, description || null);
      setName("");
      setDescription("");
      router.refresh();
    } catch (err) {
      setError(asApiError(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <section>
      {KINDS.map((k) => {
        const ofKind = entities.filter((e) => e.kind === k);
        return (
          <div key={k}>
            <h3>{KIND_LABELS[k]}</h3>
            {ofKind.length === 0 ? (
              <div className="empty">No {k}s yet.</div>
            ) : (
              ofKind.map((e) => (
                <div className="card row" key={e.id}>
                  <div>
                    <Link href={`/entities/${e.id}`}>
                      <strong>{e.name}</strong>
                    </Link>
                    {e.approved_revision_id ? (
                      <span className="meta"> · approved design set</span>
                    ) : (
                      <span className="meta"> · no approved revision</span>
                    )}
                  </div>
                </div>
              ))
            )}
          </div>
        );
      })}

      <form className="card form-row" onSubmit={submit}>
        {error ? (
          <ErrorBanner error={error} onDismiss={() => setError(null)} />
        ) : null}
        <select value={kind} onChange={(e) => setKind(e.target.value)}>
          {KINDS.map((k) => (
            <option key={k} value={k}>
              {k}
            </option>
          ))}
        </select>
        <input
          placeholder="Entity name"
          value={name}
          onChange={(e) => setName(e.target.value)}
          required
          maxLength={500}
        />
        <input
          placeholder="Description (optional)"
          value={description}
          onChange={(e) => setDescription(e.target.value)}
        />
        <button className="btn" type="submit" disabled={busy || !name.trim()}>
          Create entity
        </button>
      </form>
    </section>
  );
}

export function EntityRenameForm({ entity }: { entity: Entity }) {
  const router = useRouter();
  const [name, setName] = useState(entity.name);
  const [description, setDescription] = useState(entity.description ?? "");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<ApiError | null>(null);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (busy) return;
    setBusy(true);
    setError(null);
    try {
      await patchEntity(entity.id, {
        name,
        description: description || null,
      });
      router.refresh();
    } catch (err) {
      setError(asApiError(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <form className="card form-row" onSubmit={submit}>
      {error ? (
        <ErrorBanner error={error} onDismiss={() => setError(null)} />
      ) : null}
      <input
        placeholder="Name"
        value={name}
        onChange={(e) => setName(e.target.value)}
        required
        maxLength={500}
      />
      <input
        placeholder="Description (optional)"
        value={description}
        onChange={(e) => setDescription(e.target.value)}
      />
      <button className="btn" type="submit" disabled={busy || !name.trim()}>
        Save identity
      </button>
    </form>
  );
}

export function RevisionCreateForm({ entityId }: { entityId: string }) {
  const router = useRouter();
  const [description, setDescription] = useState("");
  const [notes, setNotes] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<ApiError | null>(null);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (busy) return;
    setBusy(true);
    setError(null);
    try {
      await createEntityRevision(entityId, {
        schema_version: 1,
        description: description || null,
        notes: notes || null,
      });
      setDescription("");
      setNotes("");
      router.refresh();
    } catch (err) {
      setError(asApiError(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <form className="card form-row" onSubmit={submit}>
      {error ? (
        <ErrorBanner error={error} onDismiss={() => setError(null)} />
      ) : null}
      <input
        placeholder="Design description"
        value={description}
        onChange={(e) => setDescription(e.target.value)}
      />
      <input
        placeholder="Notes (optional)"
        value={notes}
        onChange={(e) => setNotes(e.target.value)}
      />
      <button className="btn" type="submit" disabled={busy}>
        Create design revision
      </button>
    </form>
  );
}

export function ApproveRevisionButton({
  entity,
  revision,
}: {
  entity: Entity;
  revision: EntityRevisionSummary;
}) {
  const router = useRouter();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<ApiError | null>(null);

  if (entity.approved_revision_id === revision.id) {
    return <span className="meta">APPROVED</span>;
  }

  async function approve() {
    if (busy) return;
    setBusy(true);
    setError(null);
    try {
      // CAS: the CURRENT approved id is the expected value; a concurrent
      // approval surfaces as ENTITY_APPROVAL_CONFLICT, never silent canon.
      await approveEntityRevision(
        entity.id,
        revision.id,
        entity.approved_revision_id,
      );
      router.refresh();
    } catch (err) {
      setError(asApiError(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <span>
      {error ? (
        <ErrorBanner error={error} onDismiss={() => setError(null)} />
      ) : null}
      <button className="btn btn-small" onClick={approve} disabled={busy}>
        Approve
      </button>
    </span>
  );
}
