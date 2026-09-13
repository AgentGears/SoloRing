"use client";

/**
 * M15 revision-tracking badge (frozen R6 §20.2): explicit
 * Pinned / Track compatible modes with the authored policy version.
 * Tracking offers explicit assessment only — never auto-follow.
 */

export type TrackingMode = "PINNED" | "TRACK_COMPATIBLE";

export default function M15TrackingBadge({
  mode,
  policyVersion,
  busy,
  onChange,
}: {
  mode: TrackingMode;
  policyVersion: number;
  busy: boolean;
  onChange: (mode: TrackingMode, expectedVersion: number) => void;
}) {
  const isTracked = mode === "TRACK_COMPATIBLE";
  return (
    <div className="m15-tracking" data-testid="tracking-badge">
      <span data-testid="tracking-mode">
        {isTracked ? "Track compatible" : "Pinned"}
      </span>
      <span data-testid="tracking-version">v{policyVersion}</span>
      <span data-testid="tracking-note">
        {isTracked
          ? "Offers newer revisions for explicit assessment"
          : "No update offers"}
      </span>
      <button
        type="button"
        data-testid="tracking-toggle"
        disabled={busy}
        onClick={() =>
          onChange(isTracked ? "PINNED" : "TRACK_COMPATIBLE", policyVersion)
        }
      >
        {isTracked ? "Switch to Pinned" : "Switch to Track compatible"}
      </button>
    </div>
  );
}
