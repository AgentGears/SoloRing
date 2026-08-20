/**
 * M7D §18.3 — continuity authoring/inspection UI.
 *
 * Display surfaces are pure server-fed components (APR-050: projection
 * over authority); unresolved state renders honestly with the named
 * missing endpoint and never a fabricated value (APR-051). Authoring
 * islands are exercised through a fetch-boundary mock (the frozen plan's
 * sanctioned mocking level): payload shapes, the omitted ≠ null value
 * matrix, and 422/409 envelope rendering.
 */
import { cleanup, fireEvent, render, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ContinuityFeaturesPanel } from "@/components/ContinuityFeaturesPanel";
import ContinuityStatePanel from "@/components/ContinuityStatePanel";
import { ProjectContinuityPanel } from "@/components/ProjectContinuityPanel";
import RevisionProvenanceList from "@/components/RevisionProvenanceList";
import { ApiError } from "@/lib/api.shared";
import type {
  ContinuityFeature,
  ContinuityFeatureTransition,
  ContinuityPredicate,
  ContinuityRelation,
  ContinuityStateResponse,
  Entity,
  ReadinessIssue,
  RelationTransition,
  RevisionContinuity,
  RevisionSummary,
  ShotListItem,
} from "@/lib/types";

vi.mock("next/navigation", () => ({
  useRouter: () => ({ refresh: vi.fn() }),
}));

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
        loadError={null}
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
        loadError={null}
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
        loadError={null}
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
  });

  it("renders the narrative-context condition without relation detail", () => {
    const { container } = render(
      <ContinuityStatePanel
        state={null}
        notReadyCode="NARRATIVE_CONTEXT_REQUIRED"
        notReadyIssues={[
          { error_code: "NARRATIVE_CONTEXT_REQUIRED", shot_id: "shot-1" },
        ]}
        loadError={null}
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
        loadError={null}
        entityNames={NAMES}
      />,
    );
    expect(container.textContent).toContain("Continuity state unresolved");
  });

  it("renders a NON-semantic failure as a load error, never as readiness (r2 B6)", () => {
    const { container } = render(
      <ContinuityStatePanel
        state={null}
        notReadyCode={null}
        notReadyIssues={[]}
        loadError={{
          code: "INTERNAL_INVARIANT_VIOLATION",
          message: "stored rows disagree",
        }}
        entityNames={NAMES}
      />,
    );
    expect(container.textContent).toContain("Continuity state failed to load");
    expect(container.textContent).toContain("INTERNAL_INVARIANT_VIOLATION");
    expect(container.textContent).toContain(
      "NOT a continuity-readiness condition",
    );
    expect(container.textContent).not.toContain("not ready");
  });
});

describe("RevisionProvenanceList (M7D §18.2.6)", () => {
  afterEach(cleanup);

  function provenanceFixture(): RevisionContinuity {
    return {
      shot_revision_id: "rev-1",
      snapshot_schema_version: 3,
      snapshot_hash: "b".repeat(64),
      continuity_schema_version: 2,
      continuity_spec_hash: "c".repeat(64),
      dependencies: [{ entity_id: "eva-0001" }],
      feature_states: [
        {
          entity_id: "eva-0001",
          feature_id: "f1",
          feature_key: "forehead_cut",
          feature_kind: "injury",
          value_type: "enum",
          unit: null,
          value: "fresh",
          value_hash: "d".repeat(64),
          source_anchor: {
            anchor_type: "scene", anchor_id: "scene-9", boundary: "start",
          },
        },
      ],
      relations: [
        {
          subject_entity_id: "eva-0001",
          relation_id: "rel-1",
          predicate_id: "p1",
          predicate_key: "carries",
          object_entity_id: "bag-0002",
          source_anchor: {
            anchor_type: "shot", anchor_id: "shot-7", boundary: "start",
          },
        },
      ],
      source_transition_audit: [
        { feature_id: "f1", source_transition_id: "t1" },
        { relation_id: "rel-1", source_transition_id: "t2" },
      ],
    };
  }

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
    const { container } = render(
      <RevisionProvenanceList
        revisions={revisions}
        continuity={{ "rev-1": provenanceFixture() }}
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

  it("renders fail-closed provenance errors VISIBLY, never as absence (r2 B6)", () => {
    const revisions: RevisionSummary[] = [
      {
        id: "rev-e",
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
        continuity={{
          "rev-e": new ApiError(
            "INTERNAL_INVARIANT_VIOLATION",
            "immutable rows disagree",
            500,
          ),
        }}
        entityNames={NAMES}
      />,
    );
    expect(container.textContent).toContain("Provenance failed to load");
    expect(container.textContent).toContain("INTERNAL_INVARIANT_VIOLATION");
    expect(container.textContent).toContain("not hidden as absence");
  });
});

// --- Authoring islands (fetch-boundary mock, r2 B5) -------------------------------

function jsonResponse(status: number, body: unknown) {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: async () => body,
  };
}

const FEATURE: ContinuityFeature = {
  id: "feat-1",
  entity_id: "eva-0001",
  key: "forehead_cut",
  kind: "injury",
  value_type: "enum",
  name: "Cut",
  description: "old",
  enum_values_json: '["fresh","healing"]',
  unit: null,
  supersedes_feature_id: null,
  created_at: "2026-01-01",
  updated_at: "2026-01-01",
};

const FEATURE_TRANSITION: ContinuityFeatureTransition = {
  id: "ft-1",
  feature_id: "feat-1",
  anchor_type: "scene",
  anchor_id: "scene-9",
  boundary: "start",
  operation: "set",
  value_json: '"fresh"',
  value_hash: "h",
  created_at: "2026-01-01",
  updated_at: "2026-01-01",
};

describe("ContinuityFeaturesPanel authoring (M7D §18.2.1–18.2.2)", () => {
  let fetchMock: ReturnType<typeof vi.fn>;

  beforeEach(() => {
    fetchMock = vi.fn(async () =>
      jsonResponse(201, { ...FEATURE, id: "new" }),
    );
    vi.stubGlobal("fetch", fetchMock);
  });
  afterEach(() => {
    vi.unstubAllGlobals();
    cleanup();
  });

  function panel() {
    return render(
      <ContinuityFeaturesPanel
        entityId="eva-0001"
        features={[FEATURE]}
        transitionsByFeature={{ "feat-1": [FEATURE_TRANSITION] }}
      />,
    );
  }

  it("creates a Feature with the exact payload (r3 B5)", async () => {
    const { container } = panel();
    const key = container.querySelector(
      "input[placeholder='key [a-z][a-z0-9_]{0,63}']",
    ) as HTMLInputElement;
    fireEvent.change(key, { target: { value: "wound" } });
    const name = container.querySelector(
      "input[placeholder='Display name']",
    ) as HTMLInputElement;
    fireEvent.change(name, { target: { value: "Wound" } });
    const enums = container.querySelector(
      "input[placeholder='Enum members, comma-separated']",
    ) as HTMLInputElement;
    fireEvent.change(enums, { target: { value: "small, large" } });
    fireEvent.submit(key.closest("form")!);
    await waitFor(() => expect(fetchMock).toHaveBeenCalled());
    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toContain("/api/entities/eva-0001/continuity-features");
    expect(init.method).toBe("POST");
    expect(JSON.parse(init.body as string)).toEqual({
      key: "wound",
      kind: "injury",
      value_type: "enum",
      name: "Wound",
      enum_values: ["small", "large"],
    });
  });

  it("DELETEs a Feature when no transitions hold it (r3 B5)", async () => {
    fetchMock.mockImplementation(async () => jsonResponse(204, null));
    const { container } = render(
      <ContinuityFeaturesPanel
        entityId="eva-0001"
        features={[FEATURE]}
        transitionsByFeature={{}}
      />,
    );
    const del = [...container.querySelectorAll("button")].find(
      (b) => b.textContent === "Delete",
    )!;
    expect(del.disabled).toBe(false);
    fireEvent.click(del);
    await waitFor(() => expect(fetchMock).toHaveBeenCalled());
    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toContain("/api/continuity-features/feat-1");
    expect(init.method).toBe("DELETE");
  });

  it("DELETEs a FeatureTransition (r3 B5)", async () => {
    fetchMock.mockImplementation(async () => jsonResponse(204, null));
    const { container } = panel();
    const deletes = [...container.querySelectorAll("button")].filter(
      (b) => b.textContent === "Delete",
    );
    // First is the feature's (disabled while the transition is active).
    expect(deletes[0].disabled).toBe(true);
    fireEvent.click(deletes[1]);
    await waitFor(() => expect(fetchMock).toHaveBeenCalled());
    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toContain("/api/continuity-feature-transitions/ft-1");
    expect(init.method).toBe("DELETE");
  });

  it("renders the feature and its transition with in-use delete disabled", () => {
    const { container } = panel();
    expect(container.textContent).toContain("forehead_cut");
    expect(container.textContent).toContain("scene/start");
    const del = [...container.querySelectorAll("button")].find(
      (b) => b.textContent === "Delete" && b.title.includes("blocked"),
    );
    expect(del?.disabled).toBe(true);
  });

  it("PATCHes feature metadata; empty description is an explicit null", async () => {
    const { container } = panel();
    fireEvent.click(
      [...container.querySelectorAll("button")].find(
        (b) => b.textContent === "Edit",
      )!,
    );
    const nameInput = container.querySelector(
      "input[placeholder='Display name']",
    ) as HTMLInputElement;
    fireEvent.change(nameInput, { target: { value: "Scar" } });
    const descInput = container.querySelector(
      "input[placeholder='Description (empty clears)']",
    ) as HTMLInputElement;
    fireEvent.change(descInput, { target: { value: "" } });
    fireEvent.submit(descInput.closest("form")!);
    await waitFor(() => expect(fetchMock).toHaveBeenCalled());
    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toContain("/api/continuity-features/feat-1");
    expect(init.method).toBe("PATCH");
    expect(JSON.parse(init.body as string)).toEqual({
      name: "Scar",
      description: null,
    });
  });

  it("creates a set transition with the parsed JSON value", async () => {
    const { container } = panel();
    const anchor = container.querySelector(
      "input[placeholder='Anchor UUID']",
    ) as HTMLInputElement;
    fireEvent.change(anchor, { target: { value: "scene-9" } });
    const value = container.querySelector(
      "input[placeholder='JSON value']",
    ) as HTMLInputElement;
    fireEvent.change(value, { target: { value: '"healing"' } });
    fireEvent.submit(anchor.closest("form")!);
    await waitFor(() => expect(fetchMock).toHaveBeenCalled());
    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toContain("/api/continuity-features/feat-1/transitions");
    expect(init.method).toBe("POST");
    expect(JSON.parse(init.body as string)).toEqual({
      anchor_type: "shot",
      anchor_id: "scene-9",
      boundary: "start",
      operation: "set",
      value: "healing",
    });
  });

  it("creates a clear transition with value OMITTED (never null)", async () => {
    const { container } = panel();
    const anchor = container.querySelector(
      "input[placeholder='Anchor UUID']",
    ) as HTMLInputElement;
    fireEvent.change(anchor, { target: { value: "scene-9" } });
    const form = anchor.closest("form")!;
    fireEvent.change(form.querySelector("select:last-of-type")!, {
      target: { value: "clear" },
    });
    fireEvent.submit(form);
    await waitFor(() => expect(fetchMock).toHaveBeenCalled());
    const [, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    const body = JSON.parse(init.body as string);
    expect(body.operation).toBe("clear");
    expect("value" in body).toBe(false);
  });

  it("PATCHes a transition as a full prospective row (anchor + operation + value)", async () => {
    const { container } = panel();
    const editButtons = [...container.querySelectorAll("button")].filter(
      (b) => b.textContent === "Edit",
    );
    // The FIRST Edit belongs to the feature; the transition's is second.
    fireEvent.click(editButtons[1]);
    // The transition edit form precedes the create form in DOM order.
    const anchor = container.querySelectorAll(
      "input[placeholder='Anchor UUID']",
    )[0] as HTMLInputElement;
    fireEvent.change(anchor, { target: { value: "shot-7" } });
    fireEvent.submit(anchor.closest("form")!);
    await waitFor(() => expect(fetchMock).toHaveBeenCalled());
    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toContain("/api/continuity-feature-transitions/ft-1");
    expect(init.method).toBe("PATCH");
    expect(JSON.parse(init.body as string)).toEqual({
      anchor_type: "scene",
      anchor_id: "shot-7",
      boundary: "start",
      operation: "set",
      value: "fresh",
    });
  });

  it("renders a 422 envelope verbatim (server is the authority)", async () => {
    fetchMock.mockImplementation(async () =>
      jsonResponse(422, {
        error_code: "INVALID_CONTINUITY_VALUE",
        message: "value must be an exact member of the enum",
      }),
    );
    const { container } = panel();
    const anchor = container.querySelector(
      "input[placeholder='Anchor UUID']",
    ) as HTMLInputElement;
    fireEvent.change(anchor, { target: { value: "scene-9" } });
    const value = container.querySelector(
      "input[placeholder='JSON value']",
    ) as HTMLInputElement;
    fireEvent.change(value, { target: { value: '"nope"' } });
    fireEvent.submit(anchor.closest("form")!);
    await waitFor(() =>
      expect(container.textContent).toContain("INVALID_CONTINUITY_VALUE"),
    );
    expect(container.textContent).toContain(
      "value must be an exact member of the enum",
    );
  });
});

const PREDICATE: ContinuityPredicate = {
  id: "pred-1",
  project_id: "proj-1",
  key: "carries",
  name: "Carries",
  description: null,
  created_at: "2026-01-01",
  updated_at: "2026-01-01",
};

const RELATION: ContinuityRelation = {
  id: "rel-1",
  project_id: "proj-1",
  subject_entity_id: "eva-0001",
  predicate_id: "pred-1",
  predicate_key: "carries",
  object_entity_id: "bag-0002",
  created_at: "2026-01-01",
};

const RT: RelationTransition = {
  id: "rt-1",
  relation_id: "rel-1",
  anchor_type: "shot",
  anchor_id: "shot-7",
  boundary: "start",
  state: "active",
  created_at: "2026-01-01",
  updated_at: "2026-01-01",
};

const ENTITIES: Entity[] = [
  {
    id: "eva-0001",
    project_id: "proj-1",
    kind: "character",
    name: "Eva",
    description: null,
    created_at: "2026-01-01",
    updated_at: "2026-01-01",
    approved_revision_id: null,
  },
  {
    id: "bag-0002",
    project_id: "proj-1",
    kind: "prop",
    name: "Bag",
    description: null,
    created_at: "2026-01-01",
    updated_at: "2026-01-01",
    approved_revision_id: null,
  },
];

const SHOTS: ShotListItem[] = [
  {
    id: "shot-7",
    project_id: "proj-1",
    shot_number: 1,
    title: null,
    subject: "x",
    scene_id: null,
    scene_position: null,
    created_at: "2026-01-01",
    updated_at: "2026-01-01",
  },
];

// r3 B5 fixtures: an unreferenced predicate and a transition-less
// relation so the enabled DELETE paths are exercisable.
const PREDICATE2: ContinuityPredicate = {
  id: "pred-2",
  project_id: "proj-1",
  key: "holds",
  name: "Holds",
  description: null,
  created_at: "2026-01-01",
  updated_at: "2026-01-01",
};

const RELATION2: ContinuityRelation = {
  id: "rel-2",
  project_id: "proj-1",
  subject_entity_id: "bag-0002",
  predicate_id: "pred-2",
  predicate_key: "holds",
  object_entity_id: "eva-0001",
  created_at: "2026-01-01",
};

function cardWith(container: HTMLElement, text: string) {
  const card = [...container.querySelectorAll(".card")].find((c) =>
    c.textContent?.includes(text),
  );
  expect(card).toBeDefined();
  return card!;
}

describe("ProjectContinuityPanel authoring (M7D §18.2.3–18.2.4)", () => {
  let fetchMock: ReturnType<typeof vi.fn>;

  beforeEach(() => {
    fetchMock = vi.fn(async () => jsonResponse(201, { ...RELATION }));
    vi.stubGlobal("fetch", fetchMock);
  });
  afterEach(() => {
    vi.unstubAllGlobals();
    cleanup();
  });

  function panel(extraPredicates: ContinuityPredicate[] = [],
                 extraRelations: ContinuityRelation[] = []) {
    return render(
      <ProjectContinuityPanel
        projectId="proj-1"
        entities={ENTITIES}
        predicates={[PREDICATE, ...extraPredicates]}
        relations={[RELATION, ...extraRelations]}
        transitionsByRelation={{ "rel-1": [RT] }}
        shots={SHOTS}
      />,
    );
  }

  it("renders predicates and relations with names", () => {
    const { container } = panel();
    expect(container.textContent).toContain("carries");
    expect(container.textContent).toContain("Eva — carries → Bag");
    expect(container.textContent).toContain("1 active transition");
  });

  it("PATCHes predicate metadata with the immutable key never sent", async () => {
    const { container } = panel();
    fireEvent.click(
      [...container.querySelectorAll("button")].find(
        (b) => b.textContent === "Edit",
      )!,
    );
    const nameInput = container.querySelector(
      "input[placeholder='Display name']",
    ) as HTMLInputElement;
    fireEvent.change(nameInput, { target: { value: "Hauls" } });
    fireEvent.submit(nameInput.closest("form")!);
    await waitFor(() => expect(fetchMock).toHaveBeenCalled());
    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toContain("/api/continuity-predicates/pred-1");
    expect(init.method).toBe("PATCH");
    expect(JSON.parse(init.body as string)).toEqual({
      name: "Hauls",
      description: null,
    });
  });

  it("creates a relation with the exact identity payload", async () => {
    const { container } = panel();
    const selects = [
      ...container.querySelectorAll(
        "form select",
      ),
    ].slice(-3); // subject / predicate / object of the relation form
    fireEvent.change(selects[0], { target: { value: "eva-0001" } });
    fireEvent.change(selects[1], { target: { value: "pred-1" } });
    fireEvent.change(selects[2], { target: { value: "bag-0002" } });
    fireEvent.submit(selects[0].closest("form")!);
    await waitFor(() => expect(fetchMock).toHaveBeenCalled());
    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toContain("/api/projects/proj-1/continuity-relations");
    expect(init.method).toBe("POST");
    expect(JSON.parse(init.body as string)).toEqual({
      subject_entity_id: "eva-0001",
      predicate_id: "pred-1",
      object_entity_id: "bag-0002",
    });
  });

  it("blocks a self relation client-side (server remains the authority)", () => {
    const { container } = panel();
    const selects = [
      ...container.querySelectorAll("form select"),
    ].slice(-3);
    fireEvent.change(selects[0], { target: { value: "eva-0001" } });
    fireEvent.change(selects[1], { target: { value: "pred-1" } });
    fireEvent.change(selects[2], { target: { value: "eva-0001" } });
    expect(container.textContent).toContain(
      "A relation cannot connect an entity to itself",
    );
    const createBtn = [...container.querySelectorAll("button")].find(
      (b) => b.textContent === "Create relation",
    );
    expect(createBtn?.disabled).toBe(true);
  });

  it("creates a relation transition with the state payload", async () => {
    const { container } = panel();
    const shotSelect = container.querySelector(
      "form select[required] option[value='shot-7']",
    )?.parentElement as HTMLSelectElement;
    fireEvent.change(shotSelect, { target: { value: "shot-7" } });
    fireEvent.submit(shotSelect.closest("form")!);
    await waitFor(() => expect(fetchMock).toHaveBeenCalled());
    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toContain("/api/continuity-relations/rel-1/transitions");
    expect(JSON.parse(init.body as string)).toEqual({
      anchor_type: "shot",
      anchor_id: "shot-7",
      boundary: "start",
      state: "active",
    });
  });

  it("flips a relation transition state via PATCH", async () => {
    const { container } = panel();
    fireEvent.click(
      [...container.querySelectorAll("button")].find(
        (b) => b.textContent === "→ inactive",
      )!,
    );
    await waitFor(() => expect(fetchMock).toHaveBeenCalled());
    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toContain("/api/continuity-relation-transitions/rt-1");
    expect(init.method).toBe("PATCH");
    expect(JSON.parse(init.body as string)).toEqual({ state: "inactive" });
  });

  it("renders a 409 conflict envelope verbatim", async () => {
    fetchMock.mockImplementation(async () =>
      jsonResponse(409, {
        error_code: "CONTINUITY_RELATION_IN_USE",
        message: "ContinuityRelation rel-1 has active RelationTransitions.",
      }),
    );
    const { container } = panel();
    fireEvent.click(
      [...container.querySelectorAll("button")].find(
        (b) => b.textContent === "→ inactive",
      )!,
    );
    await waitFor(() =>
      expect(container.textContent).toContain("CONTINUITY_RELATION_IN_USE"),
    );
  });

  it("creates a Predicate with the exact payload (r3 B5)", async () => {
    const { container } = panel();
    const key = container.querySelector(
      "input[placeholder='key [a-z][a-z0-9_]{0,63}']",
    ) as HTMLInputElement;
    fireEvent.change(key, { target: { value: "allies_with" } });
    const name = container.querySelector(
      "input[placeholder='Display name']",
    ) as HTMLInputElement;
    fireEvent.change(name, { target: { value: "Allies" } });
    fireEvent.submit(key.closest("form")!);
    await waitFor(() => expect(fetchMock).toHaveBeenCalled());
    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toContain("/api/projects/proj-1/continuity-predicates");
    expect(init.method).toBe("POST");
    expect(JSON.parse(init.body as string)).toEqual({
      key: "allies_with",
      name: "Allies",
      description: null,
    });
  });

  it("DELETEs an unreferenced Predicate (r3 B5)", async () => {
    fetchMock.mockImplementation(async () => jsonResponse(204, null));
    const { container } = panel([PREDICATE2]);
    const del = [...cardWith(container, "holds").querySelectorAll("button")]
      .find((b) => b.textContent === "Delete")!;
    expect(del.disabled).toBe(false);
    fireEvent.click(del);
    await waitFor(() => expect(fetchMock).toHaveBeenCalled());
    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toContain("/api/continuity-predicates/pred-2");
    expect(init.method).toBe("DELETE");
  });

  it("DELETEs a Relation without transitions (r3 B5)", async () => {
    fetchMock.mockImplementation(async () => jsonResponse(204, null));
    const { container } = panel([PREDICATE2], [RELATION2]);
    // The relation card's exact label (the predicate card shares the
    // "holds" key text but renders no arrow).
    const del = [...cardWith(container, "Bag — holds")
      .querySelectorAll("button")]
      .find((b) => b.textContent === "Delete")!;
    expect(del.disabled).toBe(false);
    fireEvent.click(del);
    await waitFor(() => expect(fetchMock).toHaveBeenCalled());
    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toContain("/api/continuity-relations/rel-2");
    expect(init.method).toBe("DELETE");
  });

  it("PATCHes a RelationTransition's FULL anchor/boundary row (r3 B5)", async () => {
    const { container } = panel();
    const card = cardWith(container, "shot/start");
    fireEvent.click(
      [...card.querySelectorAll("button")].find(
        (b) => b.textContent === "Edit",
      )!,
    );
    const form = card.querySelector("form")!;
    const selects = form.querySelectorAll("select");
    // selects: [anchor_type, boundary, state] once anchor_type ≠ shot.
    fireEvent.change(selects[0], { target: { value: "scene" } });
    const anchor = form.querySelector("input") as HTMLInputElement;
    fireEvent.change(anchor, { target: { value: "scene-9" } });
    fireEvent.change(form.querySelectorAll("select")[1], {
      target: { value: "end" },
    });
    fireEvent.submit(form);
    await waitFor(() => expect(fetchMock).toHaveBeenCalled());
    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toContain("/api/continuity-relation-transitions/rt-1");
    expect(init.method).toBe("PATCH");
    expect(JSON.parse(init.body as string)).toEqual({
      anchor_type: "scene",
      anchor_id: "scene-9",
      boundary: "end",
      state: "active",
    });
  });

  it("DELETEs a RelationTransition (r3 B5)", async () => {
    fetchMock.mockImplementation(async () => jsonResponse(204, null));
    const { container } = panel();
    const card = cardWith(container, "shot/start");
    fireEvent.click(
      [...card.querySelectorAll("button")].find(
        (b) => b.textContent === "Delete",
      )!,
    );
    await waitFor(() => expect(fetchMock).toHaveBeenCalled());
    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toContain("/api/continuity-relation-transitions/rt-1");
    expect(init.method).toBe("DELETE");
  });
});
