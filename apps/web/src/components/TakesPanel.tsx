"use client";

// Takes panel (M3A): Generate + SSE observation + review/approval.
//
// Deliberately narrow per the M3A review: no recovery controls, no retry
// buttons, no cancellation, no executor handles. SSE is OBSERVATION only —
// events drive a status line; authoritative state always comes from the
// server via router.refresh().

import { useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";

import {
  approveTake,
  createGeneration,
  rejectTake,
  toBlobUrl,
} from "@/lib/api.client";
import { ApiError, asApiError } from "@/lib/api.shared";
import type { TakeItem } from "@/lib/types";
import ErrorBanner from "./ErrorBanner";

const TERMINAL = new Set(["succeeded", "failed", "interrupted", "cancelled"]);

interface GenStatus {
  id: string;
  status: string;
  progress_current: number | null;
  progress_total: number | null;
  error_code: string | null;
}

export default function TakesPanel({
  shotId,
  initialTakes,
}: {
  shotId: string;
  initialTakes: TakeItem[];
}) {
  const router = useRouter();
  const [gen, setGen] = useState<GenStatus | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<ApiError | null>(null);
  const esRef = useRef<EventSource | null>(null);

  useEffect(() => {
    return () => esRef.current?.close(); // teardown on unmount
  }, []);

  function observe(generationId: string) {
    esRef.current?.close();
    const es = new EventSource(`/api/generations/${generationId}/events`);
    esRef.current = es;
    es.onmessage = (ev) => {
      try {
        const payload = JSON.parse(ev.data);
        if (payload.error_code) {
          es.close();
          return;
        }
        setGen({
          id: payload.id,
          status: payload.status,
          progress_current: payload.progress_current,
          progress_total: payload.progress_total,
          error_code: payload.error_code,
        });
        if (TERMINAL.has(payload.status)) {
          es.close();
          router.refresh(); // authoritative takes/canon update
        }
      } catch {
        // malformed event: observation only; next poll refreshes
      }
    };
    es.onerror = () => {
      // Reconnection is the browser's job; refresh authoritative state too.
      router.refresh();
    };
  }

  async function generate() {
    if (busy) return; // no accidental double submission
    setBusy(true);
    setError(null);
    try {
      const created = await createGeneration(shotId);
      setGen({
        id: created.id,
        status: created.status,
        progress_current: null,
        progress_total: null,
        error_code: null,
      });
      observe(created.id);
    } catch (err) {
      setError(asApiError(err));
    } finally {
      setBusy(false);
    }
  }

  async function canon(takeId: string, action: "approve" | "reject") {
    setBusy(true);
    setError(null);
    try {
      if (action === "approve") {
        await approveTake(takeId);
      } else {
        await rejectTake(takeId);
      }
      router.refresh(); // canon panel + takes re-render from server truth
    } catch (err) {
      setError(asApiError(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div>
      {error ? <ErrorBanner error={error} onDismiss={() => setError(null)} /> : null}

      <div className="card form-row">
        <button className="btn" onClick={generate} disabled={busy}>
          {busy ? "Working…" : "Generate"}
        </button>
        {gen ? (
          <span className="meta">
            {gen.status === "running" &&
            gen.progress_total != null &&
            gen.progress_current != null
              ? `running ${gen.progress_current}/${gen.progress_total}`
              : gen.status}
            {gen.error_code ? ` — ${gen.error_code}` : ""}
          </span>
        ) : (
          <span className="meta">
            captures the current working state and queues a FakeExecutor run
          </span>
        )}
      </div>

      {initialTakes.length === 0 ? (
        <div className="empty">No candidate takes yet.</div>
      ) : (
        initialTakes.map((t) => {
          // Presentation rule (M5B-7): byte-level detection stays honest
          // (null for animated WebP); previewability falls back to the
          // CAPTURED logical kind, a provenance-backed signal. Animated
          // WebP renders (and animates) in <img> regardless of the served
          // Content-Type.
          const image =
            t.detected_media_type === "image/png" ||
            t.detected_media_type === "image/jpeg" ||
            (t.detected_media_type === null && t.output_kind === "video");
          const thumb = image && t.blob_url ? toBlobUrl(t.blob_url) : null;
          return (
            <div className="card row" key={t.id}>
              <div className="ref-row" style={{ border: "none", padding: 0 }}>
                {thumb ? (
                  <img src={thumb} alt={`take ${t.output_key}`} />
                ) : (
                  <div className="generic-icon">FILE</div>
                )}
                <div className="ref-meta">
                  <div className="name">
                    {t.output_key}{" "}
                    {t.is_approved ? (
                      <span className="badge badge-matches">approved</span>
                    ) : null}
                    {t.rejected_at ? (
                      <span className="badge badge-differs">rejected</span>
                    ) : null}
                  </div>
                  <div className="meta">
                    take {t.id.slice(0, 8)}… · {t.created_at}
                  </div>
                </div>
              </div>
              <div className="ref-controls">
                <button
                  className="btn btn-small"
                  onClick={() => canon(t.id, "approve")}
                  disabled={busy || t.rejected_at !== null}
                >
                  Approve
                </button>
                <button
                  className="btn btn-danger btn-small"
                  onClick={() => canon(t.id, "reject")}
                  disabled={busy || t.is_approved}
                >
                  Reject
                </button>
              </div>
            </div>
          );
        })
      )}
    </div>
  );
}
