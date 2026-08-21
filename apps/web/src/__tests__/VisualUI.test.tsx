/**
 * M8 §81 gate — Visual Identity UI tests (fetch-boundary mocks for the
 * authoring/curation/promotion islands; pure render for the inspection
 * and provenance panels). Covers §69–73: facet workspace, value-policy
 * editor, realization creation, working-set curation (add/remove/
 * reorder/view-key/primary), revision history + approval, soft-delete
 * envelope, Take promotion (working state ONLY), the §72 inspector row
 * payload, and the §73 current-vs-captured distinction.
 */
import { cleanup, fireEvent, render, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import AddToVisualIdentity from "@/components/AddToVisualIdentity";
import TakesPanel from "@/components/TakesPanel";
import VisualContinuityPanel from "@/components/VisualContinuityPanel";
import { VisualIdentityPanel } from "@/components/VisualIdentityPanel";
import VisualProvenanceList from "@/components/VisualProvenanceList";
import type { Asset, ContinuityFeature, Entity, TakeItem } from "@/lib/types";
import type {
  VisualAnchor,
  VisualContinuityState,
  VisualFacet,
} from "@/lib/visualTypes";

vi.mock("next/navigation", () => ({
  useRouter: () => ({ refresh: vi.fn() }),
}));

const FACET: VisualFacet = {
  id: "facet-1",
  project_id: "proj-1",
  target_kind: "entity",
  entity_id: "eva-1",
  feature_id: null,
  facet_key: "face",
  label: null,
  description: null,
  requirement: "required",
  created_at: "2026-01-01",
  updated_at: "2026-01-01",
};

const ENTITY: Entity = {
  id: "eva-1",
  project_id: "proj-1",
  kind: "character",
  name: "Eva",
  description: null,
  created_at: "2026-01-01",
  updated_at: "2026-01-01",
  approved_revision_id: "rev-1",
};

const FEATURE: ContinuityFeature = {
  id: "feat-1",
  entity_id: "eva-1",
  key: "forehead_injury",
  kind: "injury",
  value_type: "enum",
  name: "Injury",
  description: null,
  enum_values_json: '["none","fresh","healing","scarred"]',
  unit: null,
  supersedes_feature_id: null,
  created_at: "2026-01-01",
  updated_at: "2026-01-01",
};

const ASSET: Asset = {
  id: "asset-2",
  project_id: "proj-1",
  take_id: null,
  kind: "reference",
  blob_hash: "b".repeat(64),
  detected_media_type: "image/png",
  upload_mime_type: "image/png",
  original_filename: "out.png",
  width: 64,
  height: 64,
  duration_ms: null,
  fps: null,
  created_at: "2026-01-01",
} as unknown as Asset;

const ANCHOR: VisualAnchor = {
  id: "anchor-1",
  visual_facet_id: "facet-1",
  entity_revision_id: "rev-1",
  feature_value_hash: null,
  feature_value_json: null,
  visual_context_entity_revision_id: null,
  approved_revision_id: null,
  created_at: "2026-01-01",
  updated_at: "2026-01-01",
};

function panelProps(over: Partial<Parameters<typeof VisualIdentityPanel>[0]> =
  {}) {
  return {
    projectId: "proj-1",
    facets: [FACET],
    anchorsByFacet: { "facet-1": [ANCHOR] },
    entities: [ENTITY],
    featuresByEntity: { "eva-1": [FEATURE] },
    assets: [ASSET],
    ...over,
  };
}

/** Route-dispatching fetch mock: [pattern, response] pairs in order. */
function mockFetch(routes: [string | RegExp, unknown][], ok = true) {
  const fetchMock = vi.fn(async (url: string, _init?: RequestInit) => {
    for (const [pattern, body] of routes) {
      const hit =
        typeof pattern === "string"
          ? url.includes(pattern)
          : pattern.test(url);
      if (hit) {
        return {
          ok,
          status: 200,
          json: async () => body,
        };
      }
    }
    return {
      ok: false,
      status: 404,
      json: async () => ({ error_code: "NOT_ROUTED", message: String(url) }),
    };
  });
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

describe("VisualIdentityPanel authoring (M8 §69–70)", () => {
  let fetchMock: ReturnType<typeof vi.fn>;

  beforeEach(() => {
    fetchMock = vi.fn(async () => ({
      ok: true,
      status: 201,
      json: async () => ({ ...FACET }),
    }));
    vi.stubGlobal("fetch", fetchMock);
  });
  afterEach(() => {
    vi.unstubAllGlobals();
    cleanup();
  });

  it("renders facets with requirement badges and target entity", () => {
    const { container } = render(
      <VisualIdentityPanel {...panelProps()} />,
    );
    expect(container.textContent).toContain("face");
    expect(container.textContent).toContain("required");
    expect(container.textContent).toContain("Eva");
  });

  it("creates a facet with the exact payload (entity target)", async () => {
    const { container } = render(
      <VisualIdentityPanel {...panelProps({ facets: [] })} />,
    );
    const input = container.querySelector(
      "input[placeholder='facet key']",
    ) as HTMLInputElement;
    fireEvent.change(input, { target: { value: "hair" } });
    const targetSelect = container.querySelector(
      "select[aria-label='target']",
    ) as HTMLSelectElement;
    fireEvent.change(targetSelect, { target: { value: "eva-1" } });
    fireEvent.submit(input.closest("form")!);
    await waitFor(() => expect(fetchMock).toHaveBeenCalled());
    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toContain("/api/projects/proj-1/visual-facets");
    expect(init.method).toBe("POST");
    expect(JSON.parse(init.body as string)).toEqual({
      target_kind: "entity",
      entity_id: "eva-1",
      facet_key: "hair",
    });
  });

  it("toggles requirement via PATCH (requirement editor)", async () => {
    const { container } = render(
      <VisualIdentityPanel {...panelProps()} />,
    );
    fireEvent.click(
      [...container.querySelectorAll("button")].find(
        (b) => b.textContent === "→ optional",
      )!,
    );
    await waitFor(() => expect(fetchMock).toHaveBeenCalled());
    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toContain("/api/visual-facets/facet-1");
    expect(init.method).toBe("PATCH");
    expect(JSON.parse(init.body as string)).toEqual({
      requirement: "optional",
    });
  });

  it("renders a facet delete guard envelope verbatim (409)", async () => {
    fetchMock.mockImplementation(async () => ({
      ok: false,
      status: 409,
      json: async () => ({
        error_code: "VISUAL_FACET_DELETE_BLOCKED",
        message: "VisualFacet is required; change requirement first.",
      }),
    }));
    const { container } = render(
      <VisualIdentityPanel {...panelProps()} />,
    );
    fireEvent.click(
      [...container.querySelectorAll("button")].find(
        (b) => b.textContent === "Delete facet",
      )!,
    );
    await waitFor(() =>
      expect(container.textContent).toContain("VISUAL_FACET_DELETE_BLOCKED"),
    );
  });

  it("creates a realization for the current EntityRevision (§69)", async () => {
    const { container } = render(
      <VisualIdentityPanel {...panelProps()} />,
    );
    fireEvent.click(
      [...container.querySelectorAll("button")].find(
        (b) => b.textContent === "Create realization for current state",
      )!,
    );
    await waitFor(() => expect(fetchMock).toHaveBeenCalled());
    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toContain("/api/visual-facets/facet-1/anchors");
    expect(init.method).toBe("POST");
    expect(JSON.parse(init.body as string)).toEqual({
      entity_revision_id: "rev-1",
    });
  });

  it("creates a FEATURE realization via the owning entity's context (§69, r2-gate B6)", async () => {
    const featureFacet: VisualFacet = {
      ...FACET,
      id: "facet-f2",
      target_kind: "feature",
      entity_id: null,
      feature_id: "feat-1",
    };
    const { container } = render(
      <VisualIdentityPanel
        {...panelProps({ facets: [featureFacet], anchorsByFacet: {} })}
      />,
    );
    // Pick the realization value first — the button enables ONLY then.
    const valueSelect = container.querySelector(
      "select[aria-label='feature value to realize']",
    ) as HTMLSelectElement;
    expect(valueSelect).not.toBeNull();
    const button = [...container.querySelectorAll("button")].find(
      (b) => b.textContent === "Create realization for current state",
    )!;
    expect((button as HTMLButtonElement).disabled).toBe(true);
    fireEvent.change(valueSelect, { target: { value: "scarred" } });
    expect((button as HTMLButtonElement).disabled).toBe(false);
    fireEvent.click(button);
    await waitFor(() => expect(fetchMock).toHaveBeenCalled());
    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toContain("/api/visual-facets/facet-f2/anchors");
    expect(init.method).toBe("POST");
    // The context is the OWNING entity's approved revision — derived
    // through featuresByEntity, since feature facets carry entity_id
    // = null (the r2 code left this button disabled by construction).
    expect(JSON.parse(init.body as string)).toEqual({
      value: "scarred",
      visual_context_entity_revision_id: "rev-1",
    });
  });

  it("renders anchors with approved/unapproved state", () => {
    const { container } = render(
      <VisualIdentityPanel {...panelProps()} />,
    );
    expect(container.textContent).toContain("no approved revision");
  });
});

describe("Value policy editor (M8 §69)", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
    cleanup();
  });

  it("loads policies, edits one, and PUTs the full set", async () => {
    const fetchMock = mockFetch([
      [
        "/value-policies",
        [
          {
            feature_value_json: '"fresh"',
            feature_value_hash: "h1",
            policy: "required",
          },
        ],
      ],
      ["/value-policies", []],
    ]);
    const featureFacet: VisualFacet = {
      ...FACET,
      id: "facet-f",
      target_kind: "feature",
      entity_id: null,
      feature_id: "feat-1",
    };
    const { container } = render(
      <VisualIdentityPanel
        {...panelProps({ facets: [featureFacet], anchorsByFacet: {} })}
      />,
    );
    fireEvent.click(
      [...container.querySelectorAll("button")].find(
        (b) => b.textContent === "Value policies…",
      )!,
    );
    await waitFor(() =>
      expect(container.textContent).toContain("none"),
    );
    const select = container.querySelector(
      "select[aria-label='policy for fresh']",
    ) as HTMLSelectElement;
    fireEvent.change(select, { target: { value: "not_applicable" } });
    fireEvent.click(
      [...container.querySelectorAll("button")].find(
        (b) => b.textContent === "Save value policies",
      )!,
    );
    await waitFor(() =>
      expect(
        fetchMock.mock.calls.some(
          ([url, init]) =>
            String(url).includes("/value-policies") &&
            (init as RequestInit).method === "PUT",
        ),
      ).toBeTruthy(),
    );
    const put = fetchMock.mock.calls.find(
      ([url, init]) =>
        String(url).includes("/value-policies") &&
        (init as RequestInit).method === "PUT",
    ) as [string, RequestInit];
    expect(JSON.parse(put[1].body as string)).toEqual({
      // §16 full-set PUT: every enum value ships, unedited ones at the
      // default policy.
      policies: [
        { value: "none", policy: "required" },
        { value: "fresh", policy: "not_applicable" },
        { value: "healing", policy: "required" },
        { value: "scarred", policy: "required" },
      ],
    });
  });
});

describe("AnchorCuration working-set editor (M8 §70)", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
    cleanup();
  });

  const DETAIL = {
    ...ANCHOR,
    approved_revision_id: "rev-1",
    items: [
      {
        asset_id: "asset-1",
        role: "primary",
        view_key: "front",
        position: 0,
      },
      {
        asset_id: "asset-2",
        role: "supporting",
        view_key: null,
        position: 1,
      },
    ],
    working_snapshot_hash: "w".repeat(64),
    approved_snapshot_hash: "w".repeat(64),
    working_state_differs_from_approved: false,
  };

  function renderCuration(routes: [string | RegExp, unknown][]) {
    const fetchMock = mockFetch(routes);
    const { container } = render(
      <VisualIdentityPanel {...panelProps()} />,
    );
    fireEvent.click(
      [...container.querySelectorAll("button")].find(
        (b) => b.textContent === "Curate",
      )!,
    );
    fireEvent.click(
      [...container.querySelectorAll("button")].find(
        (b) => b.textContent === "Load working state",
      )!,
    );
    return { fetchMock, container };
  }

  it("loads working state, revisions, and separates approved authority", async () => {
    const { container } = renderCuration([
      [
        "/visual-anchors/anchor-1/revisions",
        [
          {
            id: "rev-1",
            visual_anchor_id: "anchor-1",
            revision_number: 2,
            snapshot_hash: "s".repeat(64),
            created_at: "2026-01-01",
          },
        ],
      ],
      ["/visual-anchors/anchor-1", DETAIL],
    ]);
    await waitFor(() =>
      expect(container.textContent).toContain("Revision history"),
    );
    expect(container.textContent).toContain("revision 2");
    expect(container.textContent).toContain("APPROVED authority");
    expect(container.textContent).toContain("primary reference:");
    expect(container.textContent).toContain("2 references");
  });

  it("reorders, edits view key, removes an item, and PUTs order", async () => {
    const { fetchMock, container } = renderCuration([
      ["/visual-anchors/anchor-1/revisions", []],
      ["/visual-anchors/anchor-1/items", DETAIL],
      ["/visual-anchors/anchor-1", DETAIL],
    ]);
    await waitFor(() =>
      expect(container.textContent).toContain("2 references"),
    );
    // Move the second item up (reorder).
    fireEvent.click(
      [...container.querySelectorAll("button[aria-label='Move up']")].at(-1)!,
    );
    // Edit the (now first) item's view key.
    const viewInput = container.querySelector(
      "input[aria-label='view key']",
    ) as HTMLInputElement;
    fireEvent.change(viewInput, { target: { value: "left-profile" } });
    // Remove the last item.
    fireEvent.click(
      [...container.querySelectorAll("button[aria-label='Remove item']")].at(
        -1,
      )!,
    );
    fireEvent.click(
      [...container.querySelectorAll("button")].find(
        (b) => b.textContent === "Save working set",
      )!,
    );
    await waitFor(() =>
      expect(
        fetchMock.mock.calls.some(
          ([url, init]) =>
            String(url).includes("/visual-anchors/anchor-1/items") &&
            (init as RequestInit).method === "PUT",
        ),
      ).toBeTruthy(),
    );
    const put = fetchMock.mock.calls.find(
      ([url, init]) =>
        String(url).includes("/visual-anchors/anchor-1/items") &&
        (init as RequestInit).method === "PUT",
    ) as [string, RequestInit];
    expect(JSON.parse(put[1].body as string)).toEqual({
      items: [
        {
          asset_id: "asset-2",
          role: "supporting",
          view_key: "left-profile",
        },
      ],
    });
  });

  it("approves from revision history with the expected pointer", async () => {
    const { fetchMock, container } = renderCuration([
      [
        "/visual-anchors/anchor-1/revisions",
        [
          {
            id: "rev-9",
            visual_anchor_id: "anchor-1",
            revision_number: 3,
            snapshot_hash: "s".repeat(64),
            created_at: "2026-01-01",
          },
        ],
      ],
      ["/visual-anchors/anchor-1", DETAIL],
    ]);
    await waitFor(() =>
      expect(container.textContent).toContain("revision 3"),
    );
    fireEvent.click(
      [...container.querySelectorAll("button")].find(
        (b) => b.textContent === "Approve",
      )!,
    );
    await waitFor(() =>
      expect(
        fetchMock.mock.calls.some(
          ([url]) => String(url).includes("/visual-anchor-revisions/rev-9/approve"),
        ),
      ).toBeTruthy(),
    );
    const call = fetchMock.mock.calls.find(
      ([url]) => String(url).includes("/visual-anchor-revisions/rev-9/approve"),
    ) as [string, RequestInit];
    expect(JSON.parse(call[1].body as string)).toEqual({
      expected_approved_revision_id: "rev-1",
    });
  });

  it("surfaces the soft-delete guard envelope verbatim (409)", async () => {
    const fetchMock = mockFetch([
      ["/visual-anchors/anchor-1", DETAIL],
      ["/visual-anchors/anchor-1/revisions", []],
    ]);
    fetchMock.mockImplementation(async (url: string, init?: RequestInit) => {
      const method = init?.method ?? "GET";
      if (
        String(url).endsWith("/visual-anchors/anchor-1") &&
        method === "GET"
      ) {
        return { ok: true, status: 200, json: async () => DETAIL };
      }
      if (String(url).includes("/revisions")) {
        return { ok: true, status: 200, json: async () => [] };
      }
      return {
        ok: false,
        status: 409,
        json: async () => ({
          error_code: "VISUAL_ANCHOR_DELETE_BLOCKED",
          message: "Unapprove before deleting.",
        }),
      };
    });
    const { container } = render(
      <VisualIdentityPanel {...panelProps()} />,
    );
    fireEvent.click(
      [...container.querySelectorAll("button")].find(
        (b) => b.textContent === "Curate",
      )!,
    );
    fireEvent.click(
      [...container.querySelectorAll("button")].find(
        (b) => b.textContent === "Load working state",
      )!,
    );
    await waitFor(() =>
      expect(container.textContent).toContain("Delete realization"),
    );
    fireEvent.click(
      [...container.querySelectorAll("button")].find(
        (b) => b.textContent === "Delete realization",
      )!,
    );
    await waitFor(() =>
      expect(container.textContent).toContain(
        "VISUAL_ANCHOR_DELETE_BLOCKED",
      ),
    );
  });
});

describe("AddToVisualIdentity promotion (M8 §71)", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
    cleanup();
  });

  it("appends the output Asset to the chosen working set ONLY", async () => {
    const detail = {
      ...ANCHOR,
      items: [
        {
          asset_id: "asset-1",
          role: "primary",
          view_key: "front",
          position: 0,
        },
      ],
    };
    const fetchMock = mockFetch([
      ["/visual-anchors/anchor-1", detail],
      ["/visual-anchors/anchor-1/items", detail],
    ]);
    const { container } = render(
      <AddToVisualIdentity
        assetId="takeout-1"
        facets={[FACET]}
        anchorsByFacet={{ "facet-1": [ANCHOR] }}
      />,
    );
    fireEvent.click(
      [...container.querySelectorAll("button")].find(
        (b) => b.textContent === "Add to Visual Identity…",
      )!,
    );
    fireEvent.change(
      container.querySelector("select[aria-label='visual facet']")!,
      { target: { value: "facet-1" } },
    );
    fireEvent.change(
      container.querySelector("select[aria-label='state realization']")!,
      { target: { value: "anchor-1" } },
    );
    fireEvent.change(container.querySelector("select[aria-label='role']")!, {
      target: { value: "detail" },
    });
    fireEvent.click(
      [...container.querySelectorAll("button")].find(
        (b) => b.textContent === "Add to working set",
      )!,
    );
    await waitFor(() =>
      expect(container.textContent).toContain("working set"),
    );
    const put = fetchMock.mock.calls.find(
      ([url, init]) =>
        String(url).includes("/visual-anchors/anchor-1/items") &&
        (init as RequestInit).method === "PUT",
    ) as [string, RequestInit];
    expect(JSON.parse(put[1].body as string)).toEqual({
      items: [
        { asset_id: "asset-1", role: "primary", view_key: "front" },
        { asset_id: "takeout-1", role: "detail", view_key: null },
      ],
    });
    // §71: NO revision capture and NO approval may be issued here.
    expect(
      fetchMock.mock.calls.some(([url, init]) => {
        const u = String(url);
        return (
          (u.includes("/revisions") && (init as RequestInit).method === "POST") ||
          u.includes("/approve")
        );
      }),
    ).toBe(false);
  });

  it("TakesPanel offers promotion only for takes with an output Asset", () => {
    const take: TakeItem = {
      id: "take-1",
      shot_id: "shot-1",
      generation_id: "gen-1",
      output_key: "video",
      rejected_at: null,
      created_at: "2026-01-01",
      is_approved: false,
      asset_id: "takeout-1",
      blob_hash: null,
      detected_media_type: null,
      output_kind: "video",
      blob_url: null,
    };
    const withAsset = render(
      <TakesPanel
        shotId="shot-1"
        initialTakes={[take]}
        visualTargets={{ facets: [FACET], anchorsByFacet: {} }}
      />,
    );
    expect(withAsset.container.textContent).toContain(
      "Add to Visual Identity…",
    );
    cleanup();
    const withoutAsset = render(
      <TakesPanel
        shotId="shot-1"
        initialTakes={[{ ...take, asset_id: null } as TakeItem]}
        visualTargets={{ facets: [FACET], anchorsByFacet: {} }}
      />,
    );
    expect(withoutAsset.container.textContent).not.toContain(
      "Add to Visual Identity…",
    );
  });
});

describe("VisualContinuityPanel (M8 §72, pure display)", () => {
  afterEach(cleanup);

  function state(
    over: Partial<VisualContinuityState> = {},
  ): VisualContinuityState {
    return {
      shot_id: "shot-1",
      continuity_state_ready: true,
      visual_continuity_ready: true,
      visual_reference_pack_hash: null,
      visual_continuity_issues: [],
      facet_statuses: [],
      ...over,
    };
  }

  function status(over: Partial<VisualContinuityState["facet_statuses"][number]>) {
    return {
      visual_facet_id: "f1",
      facet_key: "face",
      target_kind: "entity" as const,
      entity_id: "eva-1",
      feature_id: null,
      requirement: "required",
      resolved: "approved" as const,
      visual_anchor_id: "a1",
      approved_revision_id: "rev1",
      primary_asset_id: null,
      item_count: 0,
      issue: null,
      entity_revision_id: "rev-1",
      feature_value_hash: null,
      feature_value_json: null,
      visual_context_entity_revision_id: null,
      ...over,
    };
  }

  it("renders approved rows with semantic state, anchor, primary Asset, and reference count", () => {
    const { container } = render(
      <VisualContinuityPanel
        state={state({
          visual_reference_pack_hash: "a".repeat(64),
          facet_statuses: [
            status({
              primary_asset_id: "asset-9",
              item_count: 3,
            }),
            status({
              visual_facet_id: "f2",
              facet_key: "cut",
              target_kind: "feature",
              entity_id: null,
              feature_id: "feat",
              requirement: "not_applicable",
              resolved: "not_applicable",
              visual_anchor_id: null,
              approved_revision_id: null,
              entity_revision_id: null,
              feature_value_json: '"scarred"',
              feature_value_hash: "vh".repeat(32),
              visual_context_entity_revision_id: "rev-1",
            }),
          ],
        })}
        entityNames={{ "eva-1": "Eva" }}
      />,
    );
    expect(container.textContent).toContain("Eva / face");
    expect(container.textContent).toContain("state: revision rev-1…");
    expect(container.textContent).toContain("anchor a1…");
    expect(container.textContent).toContain("asset-9".slice(0, 8));
    expect(container.textContent).toContain("3 references");
    expect(container.textContent).toContain("value scarred @ rev-1…");
    expect(container.textContent).toContain("no matching anchor");
    expect(container.textContent).toContain("not applicable");
    expect(container.querySelector(".hash")).not.toBeNull();
  });

  it("renders semantic-blocked honestly with no partial resolution", () => {
    const { container } = render(
      <VisualContinuityPanel
        state={state({
          continuity_state_ready: false,
          visual_continuity_ready: false,
          visual_continuity_issues: [
            { error_code: "NARRATIVE_CONTEXT_REQUIRED" },
          ],
        })}
      />,
    );
    expect(container.textContent).toContain("blocked by semantic state");
    expect(container.textContent).toContain("NARRATIVE_CONTEXT_REQUIRED");
  });

  it("renders visual blockers with per-facet issue detail", () => {
    const { container } = render(
      <VisualContinuityPanel
        state={state({
          visual_continuity_ready: false,
          visual_continuity_issues: [
            { error_code: "VISUAL_REALIZATION_REQUIRED" },
          ],
          facet_statuses: [
            status({
              facet_key: "signage",
              entity_id: "lobby",
              resolved: "missing",
              visual_anchor_id: null,
              approved_revision_id: null,
              issue: { error_code: "VISUAL_REALIZATION_REQUIRED" },
            }),
          ],
        })}
        entityNames={{ lobby: "Grand Meridian Lobby" }}
      />,
    );
    expect(container.textContent).toContain("NOT ready");
    expect(container.textContent).toContain(
      "Grand Meridian Lobby / signage",
    );
    expect(container.textContent).toContain("missing realization");
    expect(container.textContent).toContain("VISUAL_REALIZATION_REQUIRED");
  });

  it("renders the honest empty-pack NULL-hash case", () => {
    const { container } = render(
      <VisualContinuityPanel state={state()} />,
    );
    expect(container.textContent).toContain("empty pack");
    expect(container.querySelector(".hash")).toBeNull();
  });

  it("renders unresolved when no state exists", () => {
    const { container } = render(<VisualContinuityPanel state={null} />);
    expect(container.textContent).toContain("unresolved");
  });
});

describe("VisualProvenanceList (M8 §73, pure display)", () => {
  afterEach(cleanup);

  it("separates captured authority from current authority, with Blob identity", () => {
    const revisions = [
      { id: "sr-1", revision_number: 4, created_at: "2026-01-01" },
    ] as Parameters<typeof VisualProvenanceList>[0]["revisions"];
    const continuity = {
      "sr-1": {
        shot_revision_id: "sr-1",
        snapshot_schema_version: 4,
        snapshot_hash: "x".repeat(64),
        continuity_schema_version: 2,
        continuity_spec_hash: null,
        dependencies: [],
        feature_states: [],
        relations: [],
        source_transition_audit: [],
        visual: {
          visual_reference_pack_hash: "p".repeat(64),
          anchors: [
            {
              position: 0,
              visual_facet_id: "facet-1",
              facet_key: "face",
              visual_anchor_id: "anchor-1",
              captured_visual_anchor_revision_id: "var-1",
              captured_revision_number: 3,
              captured_snapshot_hash: "s".repeat(64),
              current_applicable_anchor_id: "anchor-2",
              current_approved_revision_id: "var-2",
              current_approved_revision_number: 5,
              target_kind: "entity",
              entity_id: "eva-1",
              entity_revision_id: "rev-3",
              feature_id: null,
              feature_value_hash: null,
              feature_value_json: null,
              visual_context_entity_revision_id: null,
              items: [
                {
                  asset_id: "asset-1",
                  blob_hash: "b".repeat(64),
                  role: "primary",
                  view_key: "front",
                  position: 0,
                },
              ],
            },
          ],
        },
      },
    };
    const { container } = render(
      <VisualProvenanceList revisions={revisions} continuity={continuity} />,
    );
    expect(container.textContent).toContain("VisualAnchorRevision: 3");
    expect(container.textContent).toContain("currently applicable");
    expect(container.textContent).toContain("changed since capture");
    expect(container.textContent).toContain("revision 5");
    expect(container.textContent).toContain("1 captured reference");
    // §73: captured Asset AND Blob identity stay visible.
    expect(container.textContent).toContain("asset-1".slice(0, 8));
    expect(container.textContent).toContain(
      "b".repeat(64).slice(0, 8),
    );
  });

  it("renders the empty-history case honestly", () => {
    const { container } = render(
      <VisualProvenanceList revisions={[]} continuity={{}} />,
    );
    expect(container.textContent).toContain("No schema-4 visual provenance");
  });
});
