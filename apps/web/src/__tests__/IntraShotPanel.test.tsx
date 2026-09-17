/**
 * M16 §17 — Shot event timeline + consequence review UI cells
 * (frozen §22 UI:01-06). The browser is a projection layer: every test
 * feeds the SERVER projection through the fetch boundary (the frozen
 * plan's sanctioned mocking level) and asserts the panel renders or
 * guards — never computes — continuity semantics.
 */
import { cleanup, fireEvent, render, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import IntraShotPanel from "@/components/IntraShotPanel";

function projectionFixture(overrides: Record<string, unknown> = {}) {
  return {
    shot_id: "shot-1",
    duration_ms: 5000,
    intra_shot_ready: false,
    event_set_hash: "a".repeat(64),
    events: [
      {
        id: "ev-1",
        time_ms: 3100,
        ordinal: 0,
        target_kind: "entity_feature",
        target_id: "f1",
        before: { present: false },
        after: { present: true, value: "fresh",
                 value_hash: "b".repeat(64) },
        persistence_mode: "require_handoff",
        source_kind: "authored",
        source_proposal_id: null,
        event_hash: "c".repeat(64),
      },
    ],
    terminal_targets: [
      {
        target_kind: "entity_feature",
        target_id: "f1",
        terminal_state: { present: true, value: "fresh",
                          value_hash: "b".repeat(64) },
        persistence_mode: "require_handoff",
      },
    ],
    handoffs: [
      {
        target_kind: "entity_feature",
        target_id: "f1",
        matched: true,
        required_semantic: null,
        boundary_value: "fresh",
      },
    ],
    issues: [],
    next_cursor: null,
    ...overrides,
  };
}

function proposalsFixture(items: Array<Record<string, unknown>> = []) {
  return { shot_id: "shot-1", proposals: items, next_cursor: null };
}

function proposalFixture(overrides: Record<string, unknown> = {}) {
  return {
    id: "p1",
    source_kind: "take",
    source_shot_revision_id: "r1",
    source_shot_revision_hash: "d".repeat(64),
    proposer_kind: "analyzer",
    candidate_event: {
      time_ms: 4200,
      ordinal: 0,
      target: { kind: "entity_feature", id: "f2" },
      before: { present: false },
      after: { present: true, value: "torn",
               value_hash: "e".repeat(64) },
    },
    persistence_suggestion: "persist",
    proposal_hash: "f".repeat(64),
    review_decision: null,
    ...overrides,
  };
}

function stubFetch(
  projection: Record<string, unknown>,
  proposals: Record<string, unknown>,
) {
  return vi.fn(async (input: RequestInfo | URL) => {
    const url = String(input);
    if (url.includes("/intra-shot/proposals")) {
      return new Response(JSON.stringify(proposals), {
        status: 200,
        headers: { "content-type": "application/json" },
      });
    }
    return new Response(JSON.stringify(projection), {
      status: 200,
      headers: { "content-type": "application/json" },
    });
  });
}

let fetchMock: ReturnType<typeof stubFetch>;

beforeEach(() => {
  fetchMock = stubFetch(projectionFixture(), proposalsFixture());
  vi.stubGlobal("fetch", fetchMock);
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("IntraShotPanel (M16 §17)", () => {
  it("M16:UI:01 — timeline displays server-projected time/start/terminal/handoff state", async () => {
    const { getByTestId } = render(
      <IntraShotPanel shotId="shot-1" />,
    );
    await waitFor(() =>
      expect(getByTestId("intra-shot-event")).toBeTruthy(),
    );
    const ev = getByTestId("intra-shot-event").textContent ?? "";
    expect(ev).toContain("3100ms");
    expect(ev).toContain("absent");
    expect(ev).toContain("fresh");
    expect(ev).toContain("persistence requested");
    expect(ev).toContain("handoff matched");
    expect(getByTestId("intra-shot-terminal").textContent ?? "")
      .toContain("fresh");
    expect(
      getByTestId("intra-shot-terminal").textContent ?? "",
    ).toContain("require_handoff");
    expect(getByTestId("intra-shot-ready").textContent ?? "").toContain(
      "intra_shot_ready: false",
    );
  });

  it("M16:UI:02 — UI prevents ordinary submission at time zero/end while retaining server validation", async () => {
    const { getByTestId, getByText } = render(
      <IntraShotPanel shotId="shot-1" />,
    );
    await waitFor(() =>
      expect(getByTestId("intra-shot-time-input")).toBeTruthy(),
    );
    const input = getByTestId(
      "intra-shot-time-input",
    ) as HTMLInputElement;
    fireEvent.change(input, { target: { value: "0" } });
    await waitFor(() =>
      expect(getByTestId("intra-shot-time-guard")).toBeTruthy(),
    );
    expect(getByTestId("intra-shot-time-guard").textContent ?? "").toContain(
      "server validation remains authoritative",
    );
    fireEvent.change(input, { target: { value: "5000" } });
    await waitFor(() =>
      expect(
        getByTestId("intra-shot-time-guard").textContent ?? "",
      ).toContain("Shot end"),
    );
    // a legal interior time clears the guard
    fireEvent.change(input, { target: { value: "1200" } });
    await waitFor(() =>
      expect(getByText("stage time")).toBeTruthy(),
    );
  });

  it("M16:UI:03 — before-state mismatch displays event coordinate/stored before/expected state", async () => {
    fetchMock = stubFetch(
      projectionFixture({
        issues: [
          {
            code: "INTRA_SHOT_EVENT_BEFORE_STATE_MISMATCH",
            message: "event before-state does not equal the exact folded current state",
            event_id: "ev-9",
            time_ms: 2200,
            ordinal: 0,
            stored_before: { present: false },
            expected_state: { present: true, value: "healing",
                              value_hash: "g".repeat(64) },
          },
        ],
      }),
      proposalsFixture(),
    );
    vi.stubGlobal("fetch", fetchMock);
    const { getAllByTestId } = render(
      <IntraShotPanel shotId="shot-1" />,
    );
    await waitFor(() =>
      expect(getAllByTestId("intra-shot-issue").length).toBe(1),
    );
    const text = getAllByTestId("intra-shot-issue")[0].textContent ?? "";
    expect(text).toContain("ev-9");
    expect(text).toContain("2200ms");
    expect(text).toContain("stored before absent");
    expect(text).toContain("current authority expects \"healing\"");
  });

  it("M16:UI:04 — proposal review is visually separate from Take approval", async () => {
    fetchMock = stubFetch(
      projectionFixture(),
      proposalsFixture([proposalFixture()]),
    );
    vi.stubGlobal("fetch", fetchMock);
    const { getByTestId, getByText, getAllByText } = render(
      <IntraShotPanel shotId="shot-1" />,
    );
    await waitFor(() =>
      expect(getByTestId("intra-shot-proposal")).toBeTruthy(),
    );
    // the review section states its independence from Take approval
    expect(getByText(/independent of Take approval/i)).toBeTruthy();
    expect(
      getByText(/approving a Take never adopts a consequence/i),
    ).toBeTruthy();
    // review controls render without any Take selection state
    expect(getAllByText("Adopt persistence").length).toBeGreaterThan(0);
    expect(getAllByText("Adopt event only").length).toBeGreaterThan(0);
    expect(getAllByText("Ignore proposal").length).toBeGreaterThan(0);
  });

  it("M16:UI:05 — adopt_event_only explicitly warns persistence suggestion is discarded", async () => {
    fetchMock = stubFetch(
      projectionFixture(),
      proposalsFixture([proposalFixture()]),
    );
    vi.stubGlobal("fetch", fetchMock);
    const { getByTestId, getAllByText } = render(
      <IntraShotPanel shotId="shot-1" />,
    );
    await waitFor(() =>
      expect(getByTestId("intra-shot-proposal")).toBeTruthy(),
    );
    fireEvent.click(getAllByText("Adopt event only")[0]);
    await waitFor(() =>
      expect(
        getByTestId("intra-shot-event-only-confirm"),
      ).toBeTruthy(),
    );
    const warn =
      getByTestId("intra-shot-event-only-confirm").textContent ?? "";
    expect(warn).toContain("TRANSIENT");
    expect(warn).toContain("persistence suggestion is discarded");
    expect(warn).toContain("nothing persists downstream");
  });

  it("M16:UI:06 — stale proposal, transient-vs-boundary divergence, and nonterminal-persistence recovery actions are server-derived and visible", async () => {
    fetchMock = stubFetch(
      projectionFixture({
        intra_shot_ready: false,
        events: [
          {
            id: "ev-2",
            time_ms: 1500,
            ordinal: 0,
            target_kind: "entity_feature",
            target_id: "f1",
            before: { present: false },
            after: { present: true, value: "healing",
                     value_hash: "g".repeat(64) },
            persistence_mode: "require_handoff",
            source_kind: "authored",
            source_proposal_id: null,
            event_hash: "h".repeat(64),
          },
        ],
        terminal_targets: [
          {
            target_kind: "entity_feature",
            target_id: "f1",
            terminal_state: { present: true, value: "healing",
                              value_hash: "g".repeat(64) },
            persistence_mode: "require_handoff",
          },
        ],
        handoffs: [
          {
            target_kind: "entity_feature",
            target_id: "f1",
            matched: false,
            // §17.2: a transient terminal event and an independent
            // Shot/end transition disagree — BOTH values are shown and
            // the boundary is labeled separate A2 authority
            required_semantic: { present: true, value: "healing",
                                 value_hash: "g".repeat(64) },
            boundary_value: "scarred",
          },
        ],
        issues: [
          {
            code: "INTRA_SHOT_PERSISTENT_EVENT_NOT_TERMINAL",
            message: "require_handoff is legal only on the terminal event",
            event_id: "ev-2",
          },
        ],
      }),
      proposalsFixture([proposalFixture()]),
    );
    vi.stubGlobal("fetch", fetchMock);
    const { getAllByTestId, getByTestId } = render(
      <IntraShotPanel shotId="shot-1" />,
    );
    await waitFor(() =>
      expect(getAllByTestId("intra-shot-issue").length).toBe(1),
    );
    const recovery =
      getAllByTestId("intra-shot-issue")[0].textContent ?? "";
    expect(recovery).toContain("PATCH the earlier marker to transient");
    const ev = getByTestId("intra-shot-event").textContent ?? "";
    // the divergence renders both values, labeled as separate
    // authority (no matched handoff is claimed)
    expect(ev).toContain("no matched handoff");
  });
});
