"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

import { createProject, deleteProject } from "@/lib/api.client";
import { asApiError, type ApiError } from "@/lib/api.shared";
import type { Project } from "@/lib/types";
import ErrorBanner from "./ErrorBanner";

export function ProjectCreateForm() {
  const router = useRouter();
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
      await createProject(name, description || null);
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
    <form className="card form-row" onSubmit={submit}>
      {error ? <ErrorBanner error={error} onDismiss={() => setError(null)} /> : null}
      <input
        placeholder="Project name"
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
        {busy ? "Creating…" : "Create project"}
      </button>
    </form>
  );
}

export function ProjectDeleteButton({ project }: { project: Project }) {
  const router = useRouter();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<ApiError | null>(null);

  async function remove() {
    if (busy) return;
    if (!window.confirm(`Delete project "${project.name}"?`)) return;
    setBusy(true);
    setError(null);
    try {
      await deleteProject(project.id);
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
