"use client";

/**
 * M15 post-apply history messaging (frozen R6 §20.4): current-only
 * scope, identity/state preservation, history-unchanged guarantee,
 * the product-honesty boundary, and the explicit publish next action.
 */

export default function M15HistoryMessage({
  updatedCount,
  staleRemaining = [],
}: {
  updatedCount: number;
  staleRemaining?: { compositionId: string; occurrenceId: string }[];
}) {
  return (
    <div
      className="m15-history-message"
      data-testid="m15-history-message"
      role="status"
    >
      <p>
        {updatedCount} current working use
        {updatedCount === 1 ? "" : "s"} updated.
      </p>
      <p>Occurrence identity preserved.</p>
      <p>Persistent state/spatial subjects unchanged.</p>
      <p>Published and captured history unchanged.</p>
      <p>
        Compatibility did not certify geometric fit or visual identity.
      </p>
      <p>
        Publish a new Composition Revision to make this reusable-set
        change publishable.
      </p>
      {staleRemaining.length > 0 && (
        <p data-testid="m15-stale-remainder">
          {staleRemaining.length} remaining use
          {staleRemaining.length === 1 ? " is" : "s are"} now stale in
          this Composition — reassessment required before continuing.
        </p>
      )}
    </div>
  );
}
