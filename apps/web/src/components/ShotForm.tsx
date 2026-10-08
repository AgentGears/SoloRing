"use client";

// Shot editor form (M2C §4.7): title + every ShotIntent field. Optional blank
// inputs are sent as null (server normalization is canonical); after a
// successful save the local state reconciles to the normalized server
// response, and router.refresh() updates the server-rendered hash/updated_at.

import { useRouter } from "next/navigation";
import { useState } from "react";

import { patchShot } from "@/lib/api.client";
import { ApiError, asApiError } from "@/lib/api.shared";
import { durationInput, durationToTransport } from "@/lib/exactDuration";
import type { ShotDetail } from "@/lib/types";
import ErrorBanner from "./ErrorBanner";

const TEXT_FIELDS: { key: keyof ShotDetail; label: string }[] = [
  { key: "title", label: "Title" },
  { key: "subject", label: "Subject" },
  { key: "action", label: "Action" },
  { key: "environment", label: "Environment" },
  { key: "framing", label: "Framing" },
  { key: "camera_motion", label: "Camera motion" },
  { key: "lens", label: "Lens" },
  { key: "mood", label: "Mood" },
];

function initialForm(shot: ShotDetail): Record<string, string> {
  const form: Record<string, string> = {};
  for (const { key } of TEXT_FIELDS) {
    const v = shot[key];
    form[key] = typeof v === "string" ? v : "";
  }
  // RR21-M17CC-01: initialize from the EXACT decimal transport
  // coordinate — never from the lossy `number` (String(number)
  // already lost the exact integer for durations above 2^53)
  form.duration_ms = durationInput(shot.duration_ms_dec);
  return form;
}

export default function ShotForm({ shot }: { shot: ShotDetail }) {
  const router = useRouter();
  const [form, setForm] = useState<Record<string, string>>(() => initialForm(shot));
  const [busy, setBusy] = useState(false);
  const [savedAt, setSavedAt] = useState<string | null>(null);
  const [error, setError] = useState<ApiError | null>(null);

  function set(key: string, value: string) {
    setForm((f) => ({ ...f, [key]: value }));
  }

  async function save(e: React.FormEvent) {
    e.preventDefault();
    if (busy) return;
    if (!form.subject.trim()) {
      setError(new ApiError("VALIDATION_ERROR", "Subject must not be empty.", 422));
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const payload: Record<string, string | null> = {};
      for (const { key } of TEXT_FIELDS) {
        const v = form[key];
        payload[key] = key === "subject" ? v : v.trim() === "" ? null : v;
      }
      // RR21-M17CC-01: the exact decimal string travels to the
      // backend's deliberate canonical-decimal admission contract —
      // NEVER through Number()/IEEE-754 (which silently rounds
      // lawful durations above 2^53). An untouched form re-submits
      // the exact transport string it was initialized from, so an
      // unrelated-field save preserves the exact integer.
      try {
        payload.duration_ms = durationToTransport(form.duration_ms);
      } catch (err) {
        setBusy(false);
        setError(new ApiError(
          "VALIDATION_ERROR",
          err instanceof Error ? err.message : String(err),
          422,
        ));
        return;
      }

      // The PATCH response is the normalized truth; reconcile local state.
      const updated = await patchShot(shot.id, payload);
      setForm(initialForm(updated));
      setSavedAt(updated.updated_at);
      router.refresh(); // refresh server-rendered hash / updated_at panels
    } catch (err) {
      setError(asApiError(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <form className="card" onSubmit={save}>
      {error ? <ErrorBanner error={error} onDismiss={() => setError(null)} /> : null}
      <div className="form-grid">
        {TEXT_FIELDS.map(({ key, label }) => (
          <label key={String(key)} className="field">
            <span>
              {label}
              {key === "subject" ? " *" : ""}
            </span>
            <input
              value={form[key]}
              onChange={(e) => set(key, e.target.value)}
              maxLength={key === "subject" ? 20000 : undefined}
            />
          </label>
        ))}
        <label className="field field-temporal">
          <span>Duration (ms) — temporal metadata, not prompt text</span>
          <input
            inputMode="numeric"
            value={form.duration_ms}
            onChange={(e) => set("duration_ms", e.target.value)}
            placeholder="empty = unset; 0 is legal"
          />
        </label>
      </div>
      <div className="row">
        <button className="btn" type="submit" disabled={busy}>
          {busy ? "Saving…" : "Save shot"}
        </button>
        {savedAt ? <span className="meta">saved at {savedAt}</span> : null}
      </div>
    </form>
  );
}
