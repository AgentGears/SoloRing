"use client";

/**
 * M16 §17 — Shot event timeline + persistent consequence review.
 *
 * The browser is a projection/UI layer only: every readiness, fold,
 * handoff-equality, downstream-state, and staleness value rendered here
 * comes from the server projection (GET /shots/{id}/intra-shot). The
 * panel never computes continuity semantics client-side (APR-050).
 *
 * §17.2: consequence review is a section visually and semantically
 * separate from Take approval — Take selection is never a prerequisite
 * for review, and the UI never suggests approval adopted anything.
 */

import { useCallback, useEffect, useMemo, useState } from "react";

import {
  adoptEventPersistence,
  declineEventPersistence,
  getIntraShotProjection,
  listIntraShotProposals,
  reviewIntraShotProposal,
} from "@/lib/api.client";
import { asApiError } from "@/lib/api.shared";
import type {
  IntraShotDecision,
  IntraShotIssue,
  IntraShotProjection,
  IntraShotProposalView,
} from "@/lib/types";

function stateSummary(value: unknown): string {
  if (value === null || value === undefined) return "absent";
  if (typeof value === "object" && value !== null) {
    const v = value as { present?: boolean; value?: unknown };
    if (v.present === false) return "absent";
    if ("value" in v) return JSON.stringify(v.value);
  }
  return JSON.stringify(value);
}

function IssueRow({ issue }: { issue: IntraShotIssue }) {
  // §17.1: an invalidated before-chain shows the event id/coordinate,
  // the stored before, and the newly expected state — never a generic
  // "not ready"
  if (issue.code === "INTRA_SHOT_EVENT_BEFORE_STATE_MISMATCH") {
    return (
      <div className="card row" data-testid="intra-shot-issue">
        <div>
          <strong>Event before-state no longer matches current authority</strong>
          <div className="meta">
            event {issue.event_id} at {issue.time_ms}ms
            {issue.ordinal !== undefined
              ? ` (ordinal ${issue.ordinal})`
              : ""}
            {" "}— stored before {stateSummary(issue.stored_before)},
            current authority expects{" "}
            {stateSummary(issue.expected_state)}. Re-author the event
            against current truth; no silent rebase exists.
          </div>
        </div>
      </div>
    );
  }
  if (issue.code === "INTRA_SHOT_PERSISTENT_EVENT_NOT_TERMINAL") {
    // §17.2: the legal recovery action, not a dead-end error
    return (
      <div className="card row" data-testid="intra-shot-issue">
        <div>
          <strong>
            A require_handoff marker is only legal on the terminal event
            for its target
          </strong>
          <div className="meta">
            event {issue.event_id} is no longer terminal. Recovery:
            PATCH the earlier marker to transient, or deliberately
            change the event set.
          </div>
        </div>
      </div>
    );
  }
  return (
    <div className="card row" data-testid="intra-shot-issue">
      <div>
        <strong>{issue.code}</strong>
        <div className="meta">{issue.message}</div>
      </div>
    </div>
  );
}

export default function IntraShotPanel({ shotId }: { shotId: string }) {
  const [projection, setProjection] = useState<IntraShotProjection | null>(
    null,
  );
  const [proposals, setProposals] = useState<
    IntraShotProposalView[] | null
  >(null);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [confirming, setConfirming] = useState<string | null>(null);
  const [newTime, setNewTime] = useState("");
  const [timeGuard, setTimeGuard] = useState<string | null>(null);

  const reload = useCallback(async () => {
    try {
      const [p, list] = await Promise.all([
        getIntraShotProjection(shotId),
        listIntraShotProposals(shotId),
      ]);
      setProjection(p);
      setProposals(list.proposals);
      setError(null);
    } catch (e) {
      setError(asApiError(e).message);
    }
  }, [shotId]);

  useEffect(() => {
    void reload();
  }, [reload]);

  const events = projection?.events ?? [];
  const duration = projection?.duration_ms ?? null;

  // §17.1: client controls prevent submitting time zero / time-at-end
  // as an ordinary affordance; the server remains authoritative
  const checkTime = useCallback(
    (raw: string) => {
      setNewTime(raw);
      setTimeGuard(null);
      const t = Number(raw);
      if (raw === "" || !Number.isFinite(t)) return false;
      if (t <= 0) {
        setTimeGuard(
          "time zero is not an interior event time — server validation remains authoritative",
        );
        return false;
      }
      if (duration !== null && t >= duration) {
        setTimeGuard(
          "time at or past the Shot end is not an interior event time — server validation remains authoritative",
        );
        return false;
      }
      return true;
    },
    [duration],
  );

  const act = useCallback(
    async (label: string, fn: () => Promise<unknown>) => {
      try {
        await fn();
        setConfirming(null);
        setNotice(label);
        await reload();
      } catch (e) {
        setError(asApiError(e).message);
      }
    },
    [reload],
  );

  const pendingProposals = useMemo(
    () => (proposals ?? []).filter((p) => p.review_decision === null),
    [proposals],
  );

  if (error && !projection) {
    return (
      <section className="card">
        <h3>Intra-Shot consequences</h3>
        <p className="error">{error}</p>
      </section>
    );
  }
  if (!projection || proposals === null) {
    return (
      <section className="card">
        <h3>Intra-Shot consequences</h3>
        <p className="meta">loading…</p>
      </section>
    );
  }

  return (
    <section className="card" data-testid="intra-shot-panel">
      <h3>Intra-Shot consequences</h3>
      {error && <p className="error">{error}</p>}
      {notice && <p className="meta" data-testid="intra-shot-notice">{notice}</p>}

      {/* §17.1 timeline: duration, start summary, markers, terminal */}
      <h4>
        Event timeline{" "}
        <span className="meta">
          duration {duration === null ? "unset" : `${duration}ms`}
        </span>
      </h4>
      <p className="meta" data-testid="intra-shot-start">
        Shot/start state: resolved by the server from predecessor
        authority; the first event&apos;s stored before records it.
      </p>
      <p className="meta" data-testid="intra-shot-ready">
        intra_shot_ready: {String(projection.intra_shot_ready)}
        {projection.event_set_hash
          ? ` · event set ${projection.event_set_hash.slice(0, 12)}…`
          : " · no event set"}
      </p>
      <ul>
        {events.map((e) => (
          <li key={e.id} data-testid="intra-shot-event">
            <strong>{e.time_ms}ms</strong>{" "}
            <span className="meta">
              {e.target_kind} {e.target_id.slice(0, 8)}…{" "}
              {stateSummary(e.before)} → {stateSummary(e.after)} ·{" "}
              {e.persistence_mode === "require_handoff"
                ? "persistence requested"
                : "transient"}
              {" · "}
              {projection.handoffs.find(
                (h) =>
                  h.target_kind === e.target_kind &&
                  h.target_id === e.target_id,
              )?.matched === true
                ? "handoff matched"
                : "no matched handoff"}
            </span>
          </li>
        ))}
        {events.length === 0 && (
          <li className="meta">no events (event-free is ready)</li>
        )}
      </ul>
      <p className="meta" data-testid="intra-shot-terminal">
        Terminal fold:{" "}
        {projection.terminal_targets
          .map(
            (t) =>
              `${t.target_kind} ${stateSummary(t.terminal_state)}` +
              ` (${t.persistence_mode})`,
          )
          .join("; ") || "nothing to fold"}
      </p>

      {projection.issues.length > 0 && (
        <>
          <h4>Issues (server-derived)</h4>
          {projection.issues.map((i, n) => (
            <IssueRow key={n} issue={i} />
          ))}
        </>
      )}

      {/* §17.2 review controls — separate from Take approval */}
      <h4>Persistent consequence review</h4>
      <p className="meta">
        Reviewing a consequence is independent of Take approval: Take
        selection is not a prerequisite, and approving a Take never
        adopts a consequence.
      </p>

      {/* §17.4 downstream preview — server projection only */}
      {projection.handoffs.filter((h) => h.matched).length > 0 && (
        <div data-testid="intra-shot-downstream">
          <h4>Downstream preview</h4>
          <p className="meta">
            For each adopted persistent consequence, a later Shot
            resolves the value below at its start through the same
            M7/M13 resolver production capture uses — no client-side
            simulation:
          </p>
          <ul>
            {projection.handoffs
              .filter((h) => h.matched)
              .map((h) => (
                <li key={`${h.target_kind}:${h.target_id}`}>
                  {h.target_kind} {h.target_id.slice(0, 8)}… →{" "}
                  {stateSummary(h.boundary_value)} at a later Shot start
                </li>
              ))}
          </ul>
        </div>
      )}

      <h5>Direct event actions</h5>
      <ul>
        {events
          .filter((e) => e.persistence_mode === "require_handoff")
          .map((e) => (
            <li key={e.id} data-testid="intra-shot-direct-controls">
              <span className="meta">
                {e.time_ms}ms {e.target_kind} — persistence requested
              </span>{" "}
              <button
                onClick={() =>
                  act("persistence adopted", () =>
                    adoptEventPersistence(e.id, {
                      expected_event_hash: e.event_hash,
                      expected_event_set_hash:
                        projection.event_set_hash ?? "",
                    }),
                  )
                }
              >
                Adopt persistence
              </button>{" "}
              <button
                onClick={() =>
                  act("persistence declined", () =>
                    declineEventPersistence(e.id, {
                      expected_event_hash: e.event_hash,
                      expected_event_set_hash:
                        projection.event_set_hash ?? "",
                    }),
                  )
                }
              >
                Decline persistence
              </button>
            </li>
          ))}
      </ul>

      <h5>Proposals</h5>
      {pendingProposals.length === 0 && (
        <p className="meta">no unreviewed proposals</p>
      )}
      <ul>
        {pendingProposals.map((p) => {
          const stale =
            p.review_decision === null &&
            projection.event_set_hash !== null &&
            events.some((e) => e.source_proposal_id === p.id);
          void stale;
          return (
            <li key={p.id} data-testid="intra-shot-proposal">
              <span className="meta">
                {p.candidate_event.time_ms}ms{" "}
                {p.candidate_event.target.kind} · suggestion{" "}
                {p.persistence_suggestion} · source revision{" "}
                {p.source_shot_revision_id.slice(0, 8)}… (
                {p.proposer_kind})
              </span>{" "}
              {(["adopt_persistence", "adopt_event_only", "ignore"] as const)
                .map((d: IntraShotDecision) => (
                  <span key={d}>
                    <button
                      disabled={confirming === `${p.id}:${d}`}
                      onClick={() => {
                        if (
                          d === "adopt_event_only" &&
                          confirming !== `${p.id}:${d}`
                        ) {
                          setConfirming(`${p.id}:${d}`);
                          return;
                        }
                        void act(`proposal ${d}`, () =>
                          reviewIntraShotProposal(p.id, {
                            expected_proposal_hash: p.proposal_hash,
                            decision: d,
                          }),
                        );
                      }}
                    >
                      {d === "adopt_persistence"
                        ? "Adopt persistence"
                        : d === "adopt_event_only"
                          ? "Adopt event only"
                          : "Ignore proposal"}
                    </button>{" "}
                  </span>
                ))}
              {confirming === `${p.id}:adopt_event_only` && (
                <span
                  className="meta"
                  data-testid="intra-shot-event-only-confirm"
                >
                  Adopting event only creates a TRANSIENT event: the
                  proposal&apos;s persistence suggestion is discarded
                  and nothing persists downstream.{" "}
                  <button
                    onClick={() =>
                      void act("proposal adopt_event_only", () =>
                        reviewIntraShotProposal(p.id, {
                          expected_proposal_hash: p.proposal_hash,
                          decision: "adopt_event_only",
                        }),
                      )
                    }
                  >
                    confirm
                  </button>{" "}
                  <button onClick={() => setConfirming(null)}>
                    cancel
                  </button>
                </span>
              )}
            </li>
          );
        })}
      </ul>

      {/* §17.1 client time affordance guard (server authoritative) */}
      <h5>Add event (authoring affordance)</h5>
      <label className="meta">
        time (ms):{" "}
        <input
          value={newTime}
          onChange={(e) => void checkTime(e.target.value)}
          placeholder="interior time"
          data-testid="intra-shot-time-input"
        />
      </label>{" "}
      <button
        disabled={timeGuard !== null || newTime === ""}
        title="server validation remains authoritative"
        onClick={() => setNotice("event authoring uses the event route")}
      >
        stage time
      </button>
      {timeGuard && (
        <p className="meta" data-testid="intra-shot-time-guard">
          {timeGuard}
        </p>
      )}
    </section>
  );
}
