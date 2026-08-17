"use client";

// Minimal stable-error surface (M2 §4.3): code + message only.

import type { ApiError } from "@/lib/api.shared";

export default function ErrorBanner({
  error,
  onDismiss,
}: {
  error: ApiError;
  onDismiss?: () => void;
}) {
  return (
    <div className="error-banner" role="alert">
      <div>
        <strong>{error.code}</strong>
        <span> — {error.message}</span>
      </div>
      {onDismiss ? (
        <button className="btn btn-small" onClick={onDismiss} aria-label="Dismiss error">
          ×
        </button>
      ) : null}
    </div>
  );
}
