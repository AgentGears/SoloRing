"use client";

/**
 * M7D §18.2.1–18.2.2 — Feature + FeatureTransition authoring for one
 * Entity (client island; the server remains the sole authority —
 * APR-050). Omitted ≠ null is mirrored: the value input is only sent for
 * `set`, and `value:null` is never submitted.
 */

import { useRouter } from "next/navigation";
import { useState } from "react";

import {
  createContinuityFeature,
  createFeatureTransition,
  deleteContinuityFeature,
  deleteFeatureTransition,
  patchFeatureTransition,
} from "@/lib/api.client";
import { ApiError, asApiError } from "@/lib/api.shared";
import type {
  ContinuityFeature,
  ContinuityFeatureTransition,
} from "@/lib/types";
import ErrorBanner from "./ErrorBanner";

const KINDS = [
  "injury",
  "surface_condition",
  "damage",
  "wardrobe_condition",
  "configuration",
  "status",
  "custom",
];
const VALUE_TYPES = ["boolean", "enum", "integer", "decimal", "text"];
const ANCHOR_TYPES = ["sequence", "scene", "shot"];
const BOUNDARIES = ["start", "end"];

function ValueInputHint({ valueType }: { valueType: string }) {
  const hints: Record<string, string> = {
    boolean: "true or false",
    integer: "JSON integer, e.g. 17",
    decimal: "JSON string, e.g. \"1.5\"",
    enum: "exact member of the declared enum",
    text: "already-trimmed text, 1–4096 chars",
  };
  return <span className="meta"> value ({hints[valueType] ?? valueType})</span>;
}

function TransitionForm({
  feature,
}: {
  feature: ContinuityFeature;
}) {
  const router = useRouter();
  const [anchorType, setAnchorType] = useState("shot");
  const [anchorId, setAnchorId] = useState("");
  const [boundary, setBoundary] = useState("start");
  const [operation, setOperation] = useState("set");
  const [valueText, setValueText] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<ApiError | null>(null);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (busy) return;
    setBusy(true);
    setError(null);
    try {
      const payload: {
        anchor_type: string;
        anchor_id: string;
        boundary: string;
        operation: string;
        value?: unknown;
      } = {
        anchor_type: anchorType,
        anchor_id: anchorId.trim(),
        boundary,
        operation,
      };
      if (operation === "set") {
        // The server is the authority; the client only mirrors the
        // transport contract (JSON text → parsed value, never null).
        payload.value = JSON.parse(valueText);
      }
      await createFeatureTransition(feature.id, payload);
      setValueText("");
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
        onChange={(e) => setAnchorType(e.target.value)}
      >
        {ANCHOR_TYPES.map((t) => (
          <option key={t} value={t}>
            {t}
          </option>
        ))}
      </select>
      <input
        placeholder="Anchor UUID"
        value={anchorId}
        onChange={(e) => setAnchorId(e.target.value)}
        required
      />
      <select value={boundary} onChange={(e) => setBoundary(e.target.value)}>
        {BOUNDARIES.map((b) => (
          <option key={b} value={b}>
            {b}
          </option>
        ))}
      </select>
      <select value={operation} onChange={(e) => setOperation(e.target.value)}>
        <option value="set">set</option>
        <option value="clear">clear</option>
      </select>
      {operation === "set" ? (
        <>
          <input
            placeholder="JSON value"
            value={valueText}
            onChange={(e) => setValueText(e.target.value)}
            required
          />
          <ValueInputHint valueType={feature.value_type} />
        </>
      ) : null}
      <button
        className="btn"
        type="submit"
        disabled={busy || !anchorId.trim()}
      >
        Add transition
      </button>
    </form>
  );
}

function TransitionRow({
  transition,
}: {
  transition: ContinuityFeatureTransition;
}) {
  const router = useRouter();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<ApiError | null>(null);

  async function flipOperation() {
    if (busy) return;
    setBusy(true);
    setError(null);
    try {
      if (transition.operation === "set") {
        await patchFeatureTransition(transition.id, { operation: "clear" });
      } else {
        setError(
          new ApiError(
            "CLIENT_MIRROR",
            "clear → set requires a value — delete and recreate the transition.",
            0,
          ),
        );
        return;
      }
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
      await deleteFeatureTransition(transition.id);
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
          {transition.operation}
          {transition.operation === "set" && transition.value_json
            ? ` = ${transition.value_json}`
            : ""}
        </strong>
        <div className="meta">
          anchor{" "}
          <span className="hash">{transition.anchor_id.slice(0, 8)}…</span> ·
          created {transition.created_at}
        </div>
        {error ? <ErrorBanner error={error} onDismiss={() => setError(null)} /> : null}
      </div>
      <div>
        <button className="btn" onClick={flipOperation} disabled={busy}>
          {transition.operation === "set" ? "→ clear" : "→ set (recreate)"}
        </button>{" "}
        <button className="btn" onClick={remove} disabled={busy}>
          Delete
        </button>
      </div>
    </div>
  );
}

export function ContinuityFeaturesPanel({
  entityId,
  features,
  transitionsByFeature,
}: {
  entityId: string;
  features: ContinuityFeature[];
  transitionsByFeature: Record<string, ContinuityFeatureTransition[]>;
}) {
  const router = useRouter();
  const [key, setKey] = useState("");
  const [kind, setKind] = useState("injury");
  const [valueType, setValueType] = useState("enum");
  const [name, setName] = useState("");
  const [enumValues, setEnumValues] = useState("");
  const [unit, setUnit] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<ApiError | null>(null);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (busy) return;
    setBusy(true);
    setError(null);
    try {
      const payload: Parameters<typeof createContinuityFeature>[1] = {
        key: key.trim(),
        kind,
        value_type: valueType,
        name: name.trim(),
      };
      if (valueType === "enum") {
        payload.enum_values = enumValues
          .split(",")
          .map((v) => v.trim())
          .filter((v) => v.length > 0);
      }
      if (unit.trim()) {
        payload.unit = unit.trim();
      }
      await createContinuityFeature(entityId, payload);
      setKey("");
      setName("");
      setEnumValues("");
      setUnit("");
      router.refresh();
    } catch (err) {
      setError(asApiError(err));
    } finally {
      setBusy(false);
    }
  }

  async function removeFeature(featureId: string) {
    if (busy) return;
    setBusy(true);
    setError(null);
    try {
      await deleteContinuityFeature(featureId);
      router.refresh();
    } catch (err) {
      setError(asApiError(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <section>
      {features.length === 0 ? (
        <div className="empty">No continuity features yet.</div>
      ) : (
        features.map((f) => {
          const transitions = transitionsByFeature[f.id] ?? [];
          return (
            <div key={f.id}>
              <div className="card row">
                <div>
                  <strong>
                    {f.key} ({f.kind} · {f.value_type})
                  </strong>
                  <div className="meta">
                    {f.name}
                    {f.unit ? ` · unit ${f.unit}` : ""}
                    {f.value_type === "enum" && f.enum_values_json
                      ? ` · ${f.enum_values_json}`
                      : ""}
                    {f.supersedes_feature_id
                      ? " · supersedes an earlier feature"
                      : ""}
                  </div>
                </div>
                <button
                  className="btn"
                  onClick={() => removeFeature(f.id)}
                  disabled={busy || transitions.length > 0}
                  title={
                    transitions.length > 0
                      ? "Delete blocked while transitions are active"
                      : "Soft-delete this feature"
                  }
                >
                  Delete
                </button>
              </div>
              {transitions.map((t) => (
                <TransitionRow key={t.id} transition={t} />
              ))}
              <TransitionForm feature={f} />
            </div>
          );
        })
      )}

      <form className="card form-row" onSubmit={submit}>
        {error ? (
          <ErrorBanner error={error} onDismiss={() => setError(null)} />
        ) : null}
        <input
          placeholder="key [a-z][a-z0-9_]{0,63}"
          value={key}
          onChange={(e) => setKey(e.target.value)}
          required
        />
        <select value={kind} onChange={(e) => setKind(e.target.value)}>
          {KINDS.map((k) => (
            <option key={k} value={k}>
              {k}
            </option>
          ))}
        </select>
        <select
          value={valueType}
          onChange={(e) => setValueType(e.target.value)}
        >
          {VALUE_TYPES.map((t) => (
            <option key={t} value={t}>
              {t}
            </option>
          ))}
        </select>
        <input
          placeholder="Display name"
          value={name}
          onChange={(e) => setName(e.target.value)}
          required
        />
        {valueType === "enum" ? (
          <input
            placeholder="Enum members, comma-separated"
            value={enumValues}
            onChange={(e) => setEnumValues(e.target.value)}
            required
          />
        ) : null}
        {valueType === "integer" || valueType === "decimal" ? (
          <input
            placeholder="Unit (optional)"
            value={unit}
            onChange={(e) => setUnit(e.target.value)}
          />
        ) : null}
        <button
          className="btn"
          type="submit"
          disabled={busy || !key.trim() || !name.trim()}
        >
          Create feature
        </button>
      </form>
    </section>
  );
}
