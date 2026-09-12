"use client";

/**
 * M15 compatibility update summary (frozen R6 §20.3/§20.4): the
 * four-verdict impact grouping, explicit per-use review acceptance,
 * and the history-unchanged message. A projection surface only — the
 * backend owns every verdict; this component never computes one.
 */

import { useMemo, useState } from "react";

export type CompatibilityVerdict =
  | "COMPATIBLE_AS_IS"
  | "COMPATIBLE_VIA_DETERMINISTIC_TRANSLATION"
  | "REQUIRES_REVIEW"
  | "INCOMPATIBLE";

export interface CompatibilityUseRow {
  compositionId: string;
  occurrenceId: string;
  verdict: CompatibilityVerdict;
}

export const VERDICT_ORDER: CompatibilityVerdict[] = [
  "COMPATIBLE_AS_IS",
  "COMPATIBLE_VIA_DETERMINISTIC_TRANSLATION",
  "REQUIRES_REVIEW",
  "INCOMPATIBLE",
];

export const VERDICT_LABELS: Record<CompatibilityVerdict, string> = {
  COMPATIBLE_AS_IS: "Compatible as-is",
  COMPATIBLE_VIA_DETERMINISTIC_TRANSLATION:
    "Compatible via deterministic translation",
  REQUIRES_REVIEW: "Requires review",
  INCOMPATIBLE: "Incompatible",
};

function groupUses(uses: CompatibilityUseRow[]) {
  const groups = new Map<CompatibilityVerdict, CompatibilityUseRow[]>();
  for (const verdict of VERDICT_ORDER) groups.set(verdict, []);
  for (const use of uses) {
    const bucket = groups.get(use.verdict);
    if (bucket) bucket.push(use);
  }
  return groups;
}

export default function M15UpdateSummary({
  uses,
  onApply,
  applyBusy = false,
}: {
  uses: CompatibilityUseRow[];
  onApply?: (
    selected: { compositionId: string; occurrenceId: string }[],
  ) => void;
  applyBusy?: boolean;
}) {
  const groups = useMemo(() => groupUses(uses), [uses]);
  const [accepted, setAccepted] = useState<Set<string>>(new Set());

  const keyOf = (u: CompatibilityUseRow) =>
    `${u.compositionId}:${u.occurrenceId}`;

  const selected = uses.filter(
    (u) =>
      u.verdict === "COMPATIBLE_AS_IS" ||
      u.verdict === "COMPATIBLE_VIA_DETERMINISTIC_TRANSLATION" ||
      (u.verdict === "REQUIRES_REVIEW" && accepted.has(keyOf(u))),
  );

  return (
    <section aria-label="compatibility-update-summary" className="m15-summary">
      <h3>Compatibility update</h3>
      <p className="m15-scope-note" data-testid="history-message">
        This updates selected current working Composition uses only.
        Published Composition Revisions, existing Shot bindings, captured
        Shots, Generations, and Takes remain unchanged.
      </p>
      {VERDICT_ORDER.map((verdict) => {
        const rows = groups.get(verdict) ?? [];
        if (rows.length === 0) return null;
        return (
          <div
            key={verdict}
            className={`m15-verdict-group verdict-${verdict.toLowerCase()}`}
            data-verdict={verdict}
          >
            <h4>
              {VERDICT_LABELS[verdict]}{" "}
              <span className="m15-count">({rows.length})</span>
            </h4>
            <ul>
              {rows.map((u) => (
                <li
                  key={keyOf(u)}
                  data-testid="m15-use-row"
                  data-occurrence={u.occurrenceId}
                >
                  <span>
                    Composition {u.compositionId.slice(0, 8)} ·
                    occurrence {u.occurrenceId.slice(0, 8)}
                  </span>
                  {verdict === "REQUIRES_REVIEW" && (
                    <label>
                      <input
                        type="checkbox"
                        data-testid={`accept-${u.occurrenceId}`}
                        checked={accepted.has(keyOf(u))}
                        disabled={applyBusy}
                        onChange={(e) => {
                          setAccepted((prev) => {
                            const next = new Set(prev);
                            if (e.target.checked) next.add(keyOf(u));
                            else next.delete(keyOf(u));
                            return next;
                          });
                        }}
                      />
                      Accept review for this use
                    </label>
                  )}
                  {verdict === "INCOMPATIBLE" && (
                    <span
                      className="m15-blocked"
                      data-testid="incompatible-disabled"
                    >
                      Cannot be selected
                    </span>
                  )}
                </li>
              ))}
            </ul>
          </div>
        );
      })}
      <p className="m15-honesty" data-testid="compatibility-honesty">
        Compatibility did not certify geometric fit or visual identity.
      </p>
      {onApply && (
        <div>
          <button
            type="button"
            data-testid="apply-selected"
            disabled={selected.length === 0 || applyBusy}
            onClick={() =>
              onApply(
                selected.map((u) => ({
                  compositionId: u.compositionId,
                  occurrenceId: u.occurrenceId,
                })),
              )}
          >
            Apply selected current uses
          </button>
          <span data-testid="apply-note">
            Publish a new Composition Revision to make this
            reusable-set change publishable.
          </span>
        </div>
      )}
    </section>
  );
}
