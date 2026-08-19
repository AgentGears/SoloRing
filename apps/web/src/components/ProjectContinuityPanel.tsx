"use client";

/**
 * M7D §18.2.3–18.2.4 — Project-level Predicates + Relations +
 * RelationTransition authoring (client island; the server is the sole
 * authority — APR-050). Relations have NO edit form (0008 has no mutable
 * columns): changing endpoints means delete + recreate = a new identity.
 */

import { useRouter } from "next/navigation";
import { useState } from "react";

import {
  createPredicate,
  createRelation,
  createRelationTransition,
  deletePredicate,
  deleteRelation,
  deleteRelationTransition,
  patchRelationTransition,
} from "@/lib/api.client";
import { asApiError, type ApiError } from "@/lib/api.shared";
import type {
  ContinuityPredicate,
  ContinuityRelation,
  Entity,
  RelationTransition,
  ShotListItem,
} from "@/lib/types";
import ErrorBanner from "./ErrorBanner";

const ANCHOR_TYPES = ["sequence", "scene", "shot"];
const BOUNDARIES = ["start", "end"];

function RelationTransitionForm({
  relation,
  shots,
}: {
  relation: ContinuityRelation;
  shots: ShotListItem[];
}) {
  const router = useRouter();
  const [anchorType, setAnchorType] = useState("shot");
  const [anchorId, setAnchorId] = useState("");
  const [boundary, setBoundary] = useState("start");
  const [state, setState] = useState("active");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<ApiError | null>(null);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (busy) return;
    setBusy(true);
    setError(null);
    try {
      await createRelationTransition(relation.id, {
        anchor_type: anchorType,
        anchor_id: anchorType === "shot" && anchorId === "" && shots[0]
          ? shots[0].id
          : anchorId.trim(),
        boundary,
        state,
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
      <select
        value={anchorType}
        onChange={(e) => {
          setAnchorType(e.target.value);
          setAnchorId("");
        }}
      >
        {ANCHOR_TYPES.map((t) => (
          <option key={t} value={t}>
            {t}
          </option>
        ))}
      </select>
      {anchorType === "shot" ? (
        <select
          value={anchorId}
          onChange={(e) => setAnchorId(e.target.value)}
          required
        >
          <option value="" disabled>
            Select shot…
          </option>
          {shots.map((s) => (
            <option key={s.id} value={s.id}>
              Shot {s.shot_number}
              {s.title ? ` — ${s.title}` : ""}
            </option>
          ))}
        </select>
      ) : (
        <input
          placeholder={`${anchorType} UUID`}
          value={anchorId}
          onChange={(e) => setAnchorId(e.target.value)}
          required
        />
      )}
      <select value={boundary} onChange={(e) => setBoundary(e.target.value)}>
        {BOUNDARIES.map((b) => (
          <option key={b} value={b}>
            {b}
          </option>
        ))}
      </select>
      <select value={state} onChange={(e) => setState(e.target.value)}>
        <option value="active">active</option>
        <option value="inactive">inactive</option>
      </select>
      <button className="btn" type="submit" disabled={busy}>
        Add transition
      </button>
    </form>
  );
}

function RelationTransitionRow({
  transition,
}: {
  transition: RelationTransition;
}) {
  const router = useRouter();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<ApiError | null>(null);

  async function flip() {
    if (busy) return;
    setBusy(true);
    setError(null);
    try {
      await patchRelationTransition(transition.id, {
        state: transition.state === "active" ? "inactive" : "active",
      });
      router.refresh();
    } catch (err) {
      setError(asApiError(err));
    } finally {
      setBusy(false);
    }
  }

  async function remove() {
    if (busy) return;
    setBusy(true);
    setError(null);
    try {
      await deleteRelationTransition(transition.id);
      router.refresh();
    } catch (err) {
      setError(asApiError(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="card row">
      <div>
        <strong>
          {transition.anchor_type}/{transition.boundary} ·{" "}
          {transition.state}
        </strong>
        <div className="meta">
          anchor{" "}
          <span className="hash">{transition.anchor_id.slice(0, 8)}…</span> ·
          created {transition.created_at}
        </div>
        {error ? <ErrorBanner error={error} onDismiss={() => setError(null)} /> : null}
      </div>
      <div>
        <button className="btn" onClick={flip} disabled={busy}>
          {transition.state === "active" ? "→ inactive" : "→ active"}
        </button>{" "}
        <button className="btn" onClick={remove} disabled={busy}>
          Delete
        </button>
      </div>
    </div>
  );
}

export function ProjectContinuityPanel({
  projectId,
  entities,
  predicates,
  relations,
  transitionsByRelation,
  shots,
}: {
  projectId: string;
  entities: Entity[];
  predicates: ContinuityPredicate[];
  relations: ContinuityRelation[];
  transitionsByRelation: Record<string, RelationTransition[]>;
  shots: ShotListItem[];
}) {
  const router = useRouter();
  const names = new Map(entities.map((e) => [e.id, e.name]));
  const label = (id: string) => names.get(id) ?? `${id.slice(0, 8)}…`;

  const [predKey, setPredKey] = useState("");
  const [predName, setPredName] = useState("");
  const [subject, setSubject] = useState("");
  const [predicateId, setPredicateId] = useState("");
  const [object, setObject] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<ApiError | null>(null);

  async function submitPredicate(e: React.FormEvent) {
    e.preventDefault();
    if (busy) return;
    setBusy(true);
    setError(null);
    try {
      await createPredicate(projectId, predKey.trim(), predName.trim(), null);
      setPredKey("");
      setPredName("");
      router.refresh();
    } catch (err) {
      setError(asApiError(err));
    } finally {
      setBusy(false);
    }
  }

  async function removePredicate(id: string) {
    if (busy) return;
    setBusy(true);
    setError(null);
    try {
      await deletePredicate(id);
      router.refresh();
    } catch (err) {
      setError(asApiError(err));
    } finally {
      setBusy(false);
    }
  }

  const selfRelation = subject !== "" && subject === object;

  async function submitRelation(e: React.FormEvent) {
    e.preventDefault();
    if (busy || selfRelation) return;
    setBusy(true);
    setError(null);
    try {
      await createRelation(projectId, subject, predicateId, object);
      router.refresh();
    } catch (err) {
      setError(asApiError(err));
    } finally {
      setBusy(false);
    }
  }

  async function removeRelation(id: string) {
    if (busy) return;
    setBusy(true);
    setError(null);
    try {
      await deleteRelation(id);
      router.refresh();
    } catch (err) {
      setError(asApiError(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <section>
      <h3>Predicates</h3>
      {predicates.length === 0 ? (
        <div className="empty">No predicates yet.</div>
      ) : (
        predicates.map((p) => (
          <div className="card row" key={p.id}>
            <div>
              <strong>{p.key}</strong>
              <span className="meta"> · {p.name}</span>
            </div>
            <button
              className="btn"
              onClick={() => removePredicate(p.id)}
              disabled={
                busy ||
                relations.some((r) => r.predicate_id === p.id)
              }
              title="Delete blocked while relations reference the predicate"
            >
              Delete
            </button>
          </div>
        ))
      )}
      <form className="card form-row" onSubmit={submitPredicate}>
        {error ? (
          <ErrorBanner error={error} onDismiss={() => setError(null)} />
        ) : null}
        <input
          placeholder="key [a-z][a-z0-9_]{0,63}"
          value={predKey}
          onChange={(e) => setPredKey(e.target.value)}
          required
        />
        <input
          placeholder="Display name"
          value={predName}
          onChange={(e) => setPredName(e.target.value)}
          required
        />
        <button
          className="btn"
          type="submit"
          disabled={busy || !predKey.trim() || !predName.trim()}
        >
          Create predicate
        </button>
      </form>

      <h3>Relations</h3>
      {relations.length === 0 ? (
        <div className="empty">No relations yet.</div>
      ) : (
        relations.map((r) => {
          const transitions = transitionsByRelation[r.id] ?? [];
          return (
            <div key={r.id}>
              <div className="card row">
                <div>
                  <strong>
                    {label(r.subject_entity_id)} — {r.predicate_key} →{" "}
                    {label(r.object_entity_id)}
                  </strong>
                  <div className="meta">
                    {transitions.length} active transition
                    {transitions.length === 1 ? "" : "s"}
                  </div>
                </div>
                <button
                  className="btn"
                  onClick={() => removeRelation(r.id)}
                  disabled={busy || transitions.length > 0}
                  title="Delete blocked while transitions are active"
                >
                  Delete
                </button>
              </div>
              {transitions.map((t) => (
                <RelationTransitionRow key={t.id} transition={t} />
              ))}
              <RelationTransitionForm relation={r} shots={shots} />
            </div>
          );
        })
      )}
      <form className="card form-row" onSubmit={submitRelation}>
        {selfRelation ? (
          <div className="empty">
            A relation cannot connect an entity to itself.
          </div>
        ) : null}
        <select value={subject} onChange={(e) => setSubject(e.target.value)} required>
          <option value="" disabled>
            Subject entity…
          </option>
          {entities.map((e) => (
            <option key={e.id} value={e.id}>
              {e.name} ({e.kind})
            </option>
          ))}
        </select>
        <select
          value={predicateId}
          onChange={(e) => setPredicateId(e.target.value)}
          required
        >
          <option value="" disabled>
            Predicate…
          </option>
          {predicates.map((p) => (
            <option key={p.id} value={p.id}>
              {p.key}
            </option>
          ))}
        </select>
        <select value={object} onChange={(e) => setObject(e.target.value)} required>
          <option value="" disabled>
            Object entity…
          </option>
          {entities.map((e) => (
            <option key={e.id} value={e.id}>
              {e.name} ({e.kind})
            </option>
          ))}
        </select>
        <button
          className="btn"
          type="submit"
          disabled={busy || selfRelation || !subject || !predicateId || !object}
        >
          Create relation
        </button>
      </form>
    </section>
  );
}
