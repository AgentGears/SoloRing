"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

import { createShot, deleteShot } from "@/lib/api.client";
import { asApiError, type ApiError } from "@/lib/api.shared";
import type { ShotListItem } from "@/lib/types";
import ErrorBanner from "./ErrorBanner";

export function ShotCreateForm({ projectId }: { projectId: string }) {
  const router = useRouter();
  const [subject, setSubject] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<ApiError | null>(null);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (busy) return;
    setBusy(true);
    setError(null);
    try {
      await createShot(projectId, subject);
      setSubject("");
      router.refresh();
    } catch (err) {
      setError(asApiError(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <form className="card form-row" onSubmit={submit}>
      {error ? <ErrorBanner error={error} onDismiss={() => setError(null)} /> : null}
      <input
        placeholder="New shot subject"
        value={subject}
        onChange={(e) => setSubject(e.target.value)}
        required
        maxLength={20000}
      />
      <button className="btn" type="submit" disabled={busy || !subject.trim()}>
        {busy ? "Adding…" : "Add shot"}
      </button>
    </form>
  );
}

export function ShotDeleteButton({ shot }: { shot: ShotListItem }) {
  const router = useRouter();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<ApiError | null>(null);

  async function remove() {
    if (busy) return;
    if (!window.confirm(`Delete shot ${shot.shot_number}?`)) return;
    setBusy(true);
    setError(null);
    try {
      await deleteShot(shot.id);
      router.refresh();
    } catch (err) {
      setError(asApiError(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      {error ? <ErrorBanner error={error} onDismiss={() => setError(null)} /> : null}
      <button className="btn btn-danger btn-small" onClick={remove} disabled={busy}>
        Delete
      </button>
    </>
  );
}
