"use client";

import { useCallback, useEffect, useState } from "react";

import {
  BindingReadiness,
  BindingRead,
  ProductionWorldStatus,
  adoptAuthoritySubject,
  bindingReadiness,
  createSpatialInterpretation,
  deleteProductionWorldSelection,
  getAuthoritySubject,
  getShotProductionWorld,
  getSpatialInterpretation,
  publishBinding,
  putProductionWorldSelection,
} from "@/lib/api.client";

/** §25.2: authority-subject display + explicit adoption (irreversible). */
export function AuthoritySubjectRow({
  compositionId, occurrenceId,
}: { compositionId: string; occurrenceId: string }) {
  const [subject, setSubject] = useState<{
    subject_kind: string; subject_id: string | null } | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      const s = await getAuthoritySubject(compositionId, occurrenceId);
      setSubject({ subject_kind: s.subject_kind, subject_id: s.subject_id });
    } catch (e) {
      setError(String(e));
    }
  }, [compositionId, occurrenceId]);

  useEffect(() => { void load(); }, [load]);

  async function adopt(kind: "production_instance") {
    setBusy(true);
    setError(null);
    try {
      await adoptAuthoritySubject(compositionId, occurrenceId, kind);
      await load();
    } catch (e) {
      setError(String(e));
    } finally {
      setBusy(false);
    }
  }

  if (subject === null) {
    return <li>occurrence {occurrenceId.slice(0, 8)}…: loading…</li>;
  }
  const label = subject.subject_kind === "composition_local"
    ? "Composition-local"
    : subject.subject_kind === "creative_entity"
      ? `Creative Entity ${subject.subject_id?.slice(0, 8) ?? ""}…`
      : "Production Instance";
  return (
    <li>
      occurrence {occurrence_id_label(occurrenceId)}: <strong>{label}</strong>
      {subject.subject_kind === "composition_local" ? (
        <>
          {" "}
          <button type="button" disabled={busy}
                  title="Adoption is irreversible; correction requires identity evolution"
                  onClick={() => void adopt("production_instance")}>
            Adopt Production Instance subject
          </button>
          <small>
            {" "}Consequential and one-way: cannot be edited or rebound in
            place; correction requires identity evolution.
          </small>
        </>
      ) : null}
      {error ? <div role="alert">{error}</div> : null}
    </li>
  );
}

function occurrence_id_label(id: string) {
  return `${id.slice(0, 8)}…`;
}

/** §25.2: binding panel — readiness, publish, never client-authored. */
export function BindingPanel({
  compositionRevisionId, worldRevisionId,
}: { compositionRevisionId: string; worldRevisionId: string }) {
  const [readiness, setReadiness] = useState<BindingReadiness | null>(null);
  const [published, setPublished] = useState<BindingRead | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function refresh() {
    try {
      setReadiness(await bindingReadiness(
        compositionRevisionId, worldRevisionId));
    } catch (e) {
      setError(String(e));
    }
  }

  useEffect(() => { void refresh();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [compositionRevisionId, worldRevisionId]);

  async function publish() {
    setBusy(true);
    setError(null);
    try {
      setPublished(await publishBinding(
        compositionRevisionId, worldRevisionId));
      await refresh();
    } catch (e) {
      setError(String(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <section aria-label="composition spatial binding">
      <h4>Composition↔Spatial binding</h4>
      {readiness ? (
        <>
          <div data-testid="binding-ready">
            {readiness.ready ? "ready" : "blocked"}
          </div>
          <div>subjects: {readiness.subject_summaries.length}</div>
          <div>A4-bound: {readiness.entry_summaries.length}</div>
          <ul>
            {readiness.issues.map((i, n) => (
              <li key={n}>{i.code}</li>))}
          </ul>
          <div>
            proposed binding hash:
            <code>{readiness.proposed_binding_hash.slice(0, 16)}…</code>
          </div>
          {readiness.ready ? (
            <button type="button" disabled={busy} onClick={() =>
              void publish()}>
              Publish exact binding
            </button>
          ) : null}
        </>
      ) : <p>loading readiness…</p>}
      {published ? (
        <p data-testid="published-binding">
          published {published.binding_id}
        </p>
      ) : null}
      {error ? <div role="alert">{error}</div> : null}
    </section>
  );
}

/** §25.1: irreversible interpretation display + create. */
export function SpatialInterpretationSection({
  revisionId,
}: { revisionId: string }) {
  const [state, setState] = useState<
    { available: boolean; hash?: string } | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    void getSpatialInterpretation(revisionId).then((r) => {
      setState(r ? { available: true, hash: r.interpretation_hash }
                 : { available: false });
    }).catch((e) => setError(String(e)));
  }, [revisionId, getSpatialInterpretation]);

  if (state === null) return <p>loading interpretation…</p>;
  return (
    <section aria-label="spatial interpretation">
      <h4>Spatial interpretation</h4>
      {state.available ? (
        <>
          <p>available — hash
            <code>{state.hash?.slice(0, 16)}…</code></p>
          <small>Fixed M10 basis, millimeters, microdegrees, 1:1 scale.</small>
        </>
      ) : (
        <>
          <p>absent</p>
          <button type="button" disabled={busy} onClick={() => {
            setBusy(true);
            createSpatialInterpretation(revisionId, [0, 0, 0])
              .then((r) => setState({ available: true,
                                      hash: r.interpretation_hash }))
              .catch((e) => setError(String(e)))
              .finally(() => setBusy(false));
          }}>
            Create schema-1 interpretation (identity transform)
          </button>
          <small>
            {" "}Irreversible: an existing interpretation cannot be edited
            or deleted; correction requires a new Production Revision or a
            future versioned contract.
          </small>
        </>
      )}
      {error ? <div role="alert">{error}</div> : null}
    </section>
  );
}

/** §25.4: current Shot production-world status — stale shown distinctly;
 *  selection is explicit (no latest/auto-bind). */
export function ShotProductionWorldCard({ shotId }: { shotId: string }) {
  const [status, setStatus] = useState<ProductionWorldStatus | null>(null);
  const [bindingInput, setBindingInput] = useState("");
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      setStatus(await getShotProductionWorld(shotId));
    } catch (e) {
      setError(String(e));
    }
  }, [shotId]);
  useEffect(() => { void load(); }, [load]);

  async function select() {
    setError(null);
    try {
      await putProductionWorldSelection(
        shotId, bindingInput.trim(), status?.binding_id ?? null);
      await load();
    } catch (e) {
      setError(String(e));
    }
  }
  async function deselect() {
    if (!status?.binding_id) return;
    setError(null);
    try {
      await deleteProductionWorldSelection(shotId, status.binding_id);
      await load();
    } catch (e) {
      setError(String(e));
    }
  }

  if (status === null) return <p>loading production world…</p>;
  const state = !status.selected
    ? "absent"
    : status.ready ? "ready"
    : status.binding_current_complete === false ? "selected-but-stale"
    : "blocked";
  return (
    <section aria-label="production world">
      <h4>Production world (M13)</h4>
      <p data-testid="production-world-state">{state}</p>
      {status.selected ? (
        <>
          <p>binding <code>{status.binding_id}</code></p>
          <p>hash <code>{status.binding_hash?.slice(0, 16)}…</code></p>
          {state === "selected-but-stale" ? (
            <div role="alert">
              <p>Selected but stale. Workflow: inspect the current
                candidate → publish the exact new binding → CAS reselect
                this Shot. Selection never auto-upgrades.</p>
              <ul>
                {status.stale_details.map((d, i) => (
                  <li key={i}>{d.code}</li>))}
              </ul>
            </div>
          ) : null}
          <button type="button" onClick={() => void deselect()}>
            Remove selection (CAS)
          </button>
        </>
      ) : null}
      <div>
        <input
          placeholder="exact binding id" value={bindingInput}
          onChange={(e) => setBindingInput(e.target.value)} />
        <button type="button" disabled={!bindingInput.trim()}
                onClick={() => void select()}>
          Select exact binding
        </button>
      </div>
      {error ? <div role="alert">{error}</div> : null}
    </section>
  );
}
