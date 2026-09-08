"use client";

import { useCallback, useEffect, useState } from "react";

import {
  BindingReadiness,
  BindingRead,
  getJson,
  ProductionWorldStatus,
  adoptAuthoritySubject,
  bindingReadiness,
  createSpatialInterpretation,
  createSpatialInterpretationTransform,
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

  async function adopt(kind: "production_instance" | "creative_entity",
                       creativeEntityId?: string) {
    setBusy(true);
    setError(null);
    try {
      await adoptAuthoritySubject(compositionId, occurrenceId, kind,
                                  creativeEntityId);
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
          {" "}
          <button type="button" disabled={busy}
                  title="Adoption is irreversible; correction requires identity evolution"
                  onClick={() => {
                    const eid = window.prompt(
                      "Exact CreativeEntity UUID (irreversible):");
                    if (eid) void adopt("creative_entity", eid.trim());
                  }}>
            Adopt Creative Entity subject
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
    { available: boolean; hash?: string;
      transform?: { translation_mm: number[]; rotation_udeg: number[] } }
    | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [tx, setTx] = useState("0, 0, 0");
  const [rot, setRot] = useState("0, 0, 0");

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
          {state.transform ? (
            <p data-testid="interpretation-transform">
              realization-local to subject-local:
              {" "}translation_mm=[
              {state.transform.translation_mm.join(", ")}]
              {" "}rotation_udeg=[
              {state.transform.rotation_udeg.join(", ")}]
            </p>
          ) : null}
          <small>Fixed M10 basis, millimeters, microdegrees, 1:1 scale.</small>
        </>
      ) : (
        <>
          <p>absent</p>
          <div>
            <label>
              translation_mm
              <input value={tx} onChange={(e) => setTx(e.target.value)}
                     placeholder="0, 0, 0" />
            </label>
            <label>
              rotation_udeg
              <input value={rot} onChange={(e) => setRot(e.target.value)}
                     placeholder="0, 0, 0" />
            </label>
          </div>
          <button type="button" disabled={busy} onClick={() => {
            const translation = tx.split(",").map((v) =>
              Number.parseInt(v.trim(), 10));
            const rotation = rot.split(",").map((v) =>
              Number.parseInt(v.trim(), 10));
            if (translation.length !== 3 || rotation.length !== 3
                || translation.some(Number.isNaN)
                || rotation.some(Number.isNaN)) {
              setError("transform fields must be three integers each");
              return;
            }
            setBusy(true);
            createSpatialInterpretationTransform(revisionId, translation,
                                                 rotation)
              .then((r) => setState({ available: true,
                                      hash: r.interpretation_hash,
                                      transform: {
                                        translation_mm: translation,
                                        rotation_udeg: rotation } }))
              .catch((e) => setError(String(e)))
              .finally(() => setBusy(false));
          }}>
            Create schema-1 interpretation
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
          {status.production_world ? (
            <>
              <p>Composition Revision
                <code>{
                  status.production_world.binding.value
                    .composition_revision.revision_id}</code>
                {" / "}
                <code>{
                  status.production_world.binding.value
                    .composition_revision.snapshot_hash.slice(0, 16)}…</code>
              </p>
              <p>SpatialWorld Revision
                <code>{
                  status.production_world.binding.value
                    .spatial_world_revision.revision_id}</code>
                {" / "}
                <code>{
                  status.production_world.binding.value
                    .spatial_world_revision.snapshot_hash.slice(0, 16)}…</code>
              </p>
              <p>Production world hash
                <code>{status.production_world_hash?.slice(0, 16)}…</code>
              </p>
              <p data-testid="pi-feature-summary">
                PI state entries:
                {" "}{status.production_world.instance_feature_states?.length
                  ?? 0}
              </p>
              <p data-testid="pi-staging-summary">
                PI staging entries:
                {" "}{status.production_world.instance_spatial_states?.length
                  ?? 0}
                {" "}(
                {status.production_world.instance_spatial_states
                  ?.filter((e) => e.requirement === "required").length ?? 0}
                {" "}required)
              </p>
            </>
          ) : null}
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


/** §25.3: PI spatial staging authoring — track creation + a set
 *  transition at an explicit narrative anchor (M10 affordances). */
export function PIStagingAuthoring({
  worldId, occurrenceId,
}: { worldId: string; occurrenceId: string }) {
  const [requirement, setRequirement] = useState("optional");
  const [anchorType, setAnchorType] = useState("sequence");
  const [anchorId, setAnchorId] = useState("");
  const [boundary, setBoundary] = useState("start");
  const [tx, setTx] = useState("0, 0, 0");
  const [status, setStatus] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function createTrack() {
    setBusy(true);
    setError(null);
    try {
      const res = await fetch(
        `${process.env.NEXT_PUBLIC_API_ORIGIN ?? ""}/spatial-worlds/`
        + `${worldId}/production-instance-tracks`,
        { method: "POST", headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ occurrence_id: occurrenceId,
                                 requirement }) });
      if (!res.ok) throw new Error(`track create ${res.status}`);
      setStatus(`track ${await res.json().then((r) => r.id)} created`);
    } catch (e) {
      setError(String(e));
    } finally {
      setBusy(false);
    }
  }

  async function setTransition() {
    setBusy(true);
    setError(null);
    try {
      const tracks = await getJson<{ id: string }[]>(
        `${process.env.NEXT_PUBLIC_API_ORIGIN ?? ""}/spatial-worlds/`
        + `${worldId}/production-instance-tracks`);
      const mine = tracks.find(() => true);
      if (!mine) throw new Error("create a track first");
      const translation = tx.split(",").map((v) =>
        Number.parseInt(v.trim(), 10));
      if (translation.length !== 3 || translation.some(Number.isNaN)) {
        throw new Error("translation must be three integers");
      }
      const res = await fetch(
        `${process.env.NEXT_PUBLIC_API_ORIGIN ?? ""
        }/production-instance-spatial-tracks/${mine.id}/transitions`,
        { method: "POST", headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ anchor_type: anchorType,
                                 anchor_id: anchorId.trim(), boundary,
                                 operation: "set",
                                 transform: { translation_mm: translation,
                                              rotation_udeg: [0, 0, 0] } }) });
      if (!res.ok) throw new Error(`transition ${res.status}`);
      setStatus("staging set");
    } catch (e) {
      setError(String(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <section aria-label="production instance staging authoring">
      <h4>Production Instance staging</h4>
      <label>
        requirement
        <select value={requirement}
                onChange={(e) => setRequirement(e.target.value)}>
          <option value="required">required</option>
          <option value="optional">optional</option>
        </select>
      </label>{" "}
      <button type="button" disabled={busy} onClick={() =>
        void createTrack()}>
        Create PI track in this world
      </button>
      <div>
        <label>
          anchor
          <select value={anchorType}
                  onChange={(e) => setAnchorType(e.target.value)}>
            <option value="sequence">sequence</option>
            <option value="scene">scene</option>
            <option value="shot">shot</option>
          </select>
        </label>{" "}
        <input placeholder="anchor UUID" value={anchorId}
               onChange={(e) => setAnchorId(e.target.value)} />{" "}
        <select value={boundary}
                onChange={(e) => setBoundary(e.target.value)}>
          <option value="start">start</option>
          <option value="end">end</option>
        </select>{" "}
        <input placeholder="0, 0, 0" value={tx}
               onChange={(e) => setTx(e.target.value)} />{" "}
        <button type="button" disabled={busy || !anchorId.trim()}
                onClick={() => void setTransition()}>
          Set staging at anchor
        </button>
      </div>
      {status ? <p data-testid="pi-staging-status">{status}</p> : null}
      {error ? <div role="alert">{error}</div> : null}
    </section>
  );
}

/** §25.5: read-only captured-history inspector for schema-6 revisions. */
export function CapturedProductionWorldInspector({
  revisionId,
}: { revisionId: string }) {
  const [data, setData] = useState<{
    captured: boolean;
    production_world_hash?: string;
    binding?: {
      binding_id: string; binding_hash: string;
      composition_revision_id: string; composition_revision_hash: string;
      spatial_world_revision_id: string;
      spatial_world_revision_hash: string;
    };
    captured_feature_states?: unknown[];
    captured_spatial_states?: unknown[];
  } | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    getJson<{
      captured: boolean;
      production_world_hash?: string;
      binding?: {
        binding_id: string; binding_hash: string;
        composition_revision_id: string; composition_revision_hash: string;
        spatial_world_revision_id: string;
        spatial_world_revision_hash: string;
      };
      captured_feature_states?: unknown[];
      captured_spatial_states?: unknown[];
    }>(`${process.env.NEXT_PUBLIC_API_ORIGIN ?? ""
      }/shot-revisions/${revisionId}/production-world`)
      .then(setData)
      .catch((e) => setError(String(e)));
  }, [revisionId]);

  if (error) return <div role="alert">{error}</div>;
  if (data === null) return <p>loading captured history…</p>;
  if (!data.captured) return <p>No captured production world.</p>;
  return (
    <section aria-label="captured production world" data-history="true">
      <h5>Captured production world (history — read-only)</h5>
      {data.binding ? (
        <>
          <p>captured binding
            <code>{data.binding.binding_id}</code>
            {" / "}<code>{data.binding.binding_hash.slice(0, 16)}…</code>
          </p>
          <p>captured Composition Revision
            <code>{data.binding.composition_revision_id}</code>
            {" / "}<code>{
              data.binding.composition_revision_hash.slice(0, 16)}…</code>
          </p>
          <p>captured SpatialWorld Revision
            <code>{data.binding.spatial_world_revision_id}</code>
            {" / "}<code>{
              data.binding.spatial_world_revision_hash.slice(0, 16)}…</code>
          </p>
        </>
      ) : null}
      <p>captured PI state entries:
        {" "}{data.captured_feature_states?.length ?? 0}</p>
      <p>captured PI staging entries:
        {" "}{data.captured_spatial_states?.length ?? 0}</p>
    </section>
  );
}
