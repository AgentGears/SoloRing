"use client";

// Current Working State (M2D §5): canonical identity, compact presentation.
// Full hash stays copyable; the timestamp shows a human-readable local form
// with the exact ISO value as secondary text. All values are server-truth.

import { useEffect, useState } from "react";

export default function WorkingStatePanel({
  workingSnapshotHash,
  updatedAt,
}: {
  // M7B compatibility: null when continuity state is unresolved — never a
  // fabricated hash.
  workingSnapshotHash: string | null;
  updatedAt: string;
}) {
  const [copied, setCopied] = useState(false);
  // Local time is formatted only after mount: server and browser locales can
  // differ, and rendering it during SSR would cause a hydration mismatch.
  // The exact ISO value below is the authoritative form either way.
  const [local, setLocal] = useState<string | null>(null);
  useEffect(() => {
    setLocal(new Date(updatedAt).toLocaleString());
  }, [updatedAt]);

  async function copy() {
    if (!workingSnapshotHash) return;
    try {
      await navigator.clipboard.writeText(workingSnapshotHash);
      setCopied(true);
      setTimeout(() => setCopied(false), 1200);
    } catch {
      // Clipboard unavailable (permissions/host); the full value is still
      // rendered in secondary text for manual copy.
    }
  }

  if (!workingSnapshotHash) {
    return (
      <div className="card">
        <div className="empty">
          Continuity state unresolved — no authoritative working snapshot
          exists yet.
        </div>
        <div className="meta">updated {local ?? updatedAt}</div>
      </div>
    );
  }

  const compact = `${workingSnapshotHash.slice(0, 8)}…${workingSnapshotHash.slice(-6)}`;

  return (
    <div className="card">
      <div className="row">
        <div>
          <span className="hash-compact">{compact}</span>{" "}
          <span className="meta">canonical working snapshot</span>
        </div>
        <button className="btn btn-small" onClick={copy}>
          {copied ? "Copied" : "Copy hash"}
        </button>
      </div>
      <div className="meta">updated {local ?? updatedAt}</div>
      <div className="hash">{workingSnapshotHash}</div>
    </div>
  );
}
