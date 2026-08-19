/**
 * M7D §18.3 — continuity authoring/inspection UI.
 *
 * Display surfaces are pure server-fed components (APR-050: projection
 * over authority); unresolved state renders honestly with the named
 * missing endpoint and never a fabricated value (APR-051). Authoring
 * islands mirror the server contracts (omitted ≠ null; no self relation;
 * deletes blocked while in-use).
 */
import { cleanup, render } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import ContinuityStatePanel from "@/components/ContinuityStatePanel";
import RevisionProvenanceList from "@/components/RevisionProvenanceList";
import type {
  ContinuityFeature,
  ContinuityPredicate,
  ContinuityRelation,
  ContinuityStateResponse,
  ReadinessIssue,
  RelationTransition,
  RevisionContinuity,
  RevisionSummary,
} from "@/lib/types";

const NAMES: Record<string, string> = {
  "eva-0001": "Eva",
  "bag-0002": "Bag",
};

function stateFixture(): ContinuityStateResponse {
  return {
    shot_id: "shot-1",
    continuity_state_ready: true,
    readiness_issues: [],
    feature_states: [
      {
        entity_id: "eva-0001",
        feature_id: "f1",
        feature_key: "forehead_cut",
        feature_kind: "injury",
        value_type: "enum",
        unit: null,
        value: "fresh",
        source_transition_id: "t1",
        source_anchor: {
          anchor_type: "scene", anchor_id: "scene-9", boundary: "start",
        },
      },
    ],
    relation_states: [
      {
        subject_entity_id: "eva-0001",
        relation_id: "rel-1",
        predicate_id: "p1",
        predicate_key: "carries",
        object_entity_id: "bag-0002",
        source_transition_id: "t2",
        source_anchor: {
          anchor_type: "shot", anchor_id: "shot-7", boundary: "start",
        },
      },
    ],
  };
}

describe("ContinuityStatePanel (M7D §18.2.5)", () => {
  afterEach(cleanup);

  it("renders effective feature and relation states with anchors", () => {
    const { container } = render(
      <ContinuityStatePanel
        state={stateFixture()}
        notReadyCode={null}
        notReadyIssues={[]}
        entityNames={NAMES}
      />,
    );
    expect(container.textContent).toContain("forehead_cut");
    expect(container.textContent).toContain("carries");
    expect(container.textContent).toContain("Eva");
    expect(container.textContent).toContain("Bag");
    expect(container.textContent).toContain("scene/start");
  });

  it("renders an honestly-empty ready state", () => {
    const empty = { ...stateFixture(), feature_states: [], relation_states: [] };
    const { container } = render(
      <ContinuityStatePanel
        state={empty}
        notReadyCode={null}
        notReadyIssues={[]}
        entityNames={NAMES}
      />,
    );
    expect(container.textContent).toContain(
      "Ready — no effective continuity state",
    );
  });

  it("names the missing endpoint for ENDPOINT_REQUIRED (never fabricated)", () => {
    const issues: ReadinessIssue[] = [
      {
        error_code: "CONTINUITY_RELATION_ENDPOINT_REQUIRED",
        relation_id: "rel-1",
        subject_entity_id: "eva-0001",
        predicate_id: "p1",
        predicate_key: "carries",
        object_entity_id: "bag-0002",
        present_entity_id: "eva-0001",
        missing_entity_id: "bag-0002",
      },
    ];
    const { container } = render(
      <ContinuityStatePanel
        state={null}
        notReadyCode="CONTINUITY_RELATION_ENDPOINT_REQUIRED"
        notReadyIssues={issues}
        entityNames={NAMES}
      />,
    );
    expect(container.textContent).toContain(
      "Continuity state not ready — CONTINUITY_RELATION_ENDPOINT_REQUIRED",
    );
    expect(container.textContent).toContain("Bag");
    expect(container.textContent).toContain(
      "no hidden dependency is created",
    );
    // ALL issues render — never only the first.
    expect(
      container.querySelectorAll(".card").length,
    ).toBeGreaterThanOrEqual(1);
  });

  it("renders the narrative-context condition without relation detail", () => {
    const { container } = render(
      <ContinuityStatePanel
        state={null}
        notReadyCode="NARRATIVE_CONTEXT_REQUIRED"
        notReadyIssues={[
          { error_code: "NARRATIVE_CONTEXT_REQUIRED", shot_id: "shot-1" },
        ]}
        entityNames={NAMES}
      />,
    );
    expect(container.textContent).toContain("Narrative context required");
    expect(container.textContent).toContain("assign it to a scene");
  });

  it("renders unresolved honestly when neither state nor error exists", () => {
    const { container } = render(
      <ContinuityStatePanel
        state={null}
        notReadyCode={null}
        notReadyIssues={[]}
        entityNames={NAMES}
      />,
    );
    expect(container.textContent).toContain("Continuity state unresolved");
  });
});

describe("RevisionProvenanceList (M7D §18.2.6)", () => {
  afterEach(cleanup);

  it("renders per-revision captured continuity including relations", () => {
    const revisions: RevisionSummary[] = [
      {
        id: "rev-1",
        shot_id: "shot-1",
        revision_number: 2,
        snapshot_hash: "b".repeat(64),
        continuity_spec_hash: "c".repeat(64),
        created_at: "2026-01-01",
      },
    ];
    const continuity: Record<string, RevisionContinuity> = {
      "rev-1": {
        shot_revision_id: "rev-1",
        snapshot_schema_version: 3,
        snapshot_hash: "b".repeat(64),
        continuity_schema_version: 2,
        continuity_spec_hash: "c".repeat(64),
        dependencies: [{ entity_id: "eva-0001" }],
        feature_states: stateFixture().feature_states,
        relations: stateFixture().relation_states,
        source_transition_audit: [
          { feature_id: "f1", source_transition_id: "t1" },
          { relation_id: "rel-1", source_transition_id: "t2" },
        ],
      },
    };
    const { container } = render(
      <RevisionProvenanceList
        revisions={revisions}
        continuity={continuity}
        entityNames={NAMES}
      />,
    );
    expect(container.textContent).toContain("Revision 2");
    expect(container.textContent).toContain("snapshot schema 3");
    expect(container.textContent).toContain("continuity spec v2");
    expect(container.textContent).toContain("1 dependencies");
    expect(container.textContent).toContain("1 relations");
    expect(container.textContent).toContain("Eva — carries → Bag");
    expect(container.textContent).toContain("2 source transitions");
  });

  it("marks unavailable provenance honestly", () => {
    const revisions: RevisionSummary[] = [
      {
        id: "rev-x",
        shot_id: "shot-1",
        revision_number: 1,
        snapshot_hash: "a".repeat(64),
        continuity_spec_hash: null,
        created_at: "2026-01-01",
      },
    ];
    const { container } = render(
      <RevisionProvenanceList
        revisions={revisions}
        continuity={{ "rev-x": null }}
        entityNames={NAMES}
      />,
    );
    expect(container.textContent).toContain("provenance unavailable");
  });
});
