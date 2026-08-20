/**
 * M8 §81 gate — Visual Identity UI tests (fetch-boundary mocks for the
 * authoring island; pure render for the inspection panel).
 */
import { cleanup, fireEvent, render, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import VisualContinuityPanel from "@/components/VisualContinuityPanel";
import { VisualIdentityPanel } from "@/components/VisualIdentityPanel";
import type { VisualContinuityState, VisualFacet } from "@/lib/visualTypes";

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

  it("renders facets with requirement badges", () => {
    const { container } = render(
      <VisualIdentityPanel
        projectId="proj-1"
        facets={[FACET]}
        anchorsByFacet={{}}
      />,
    );
    expect(container.textContent).toContain("face");
    expect(container.textContent).toContain("required");
  });

  it("creates a facet with the exact payload", async () => {
    const { container } = render(
      <VisualIdentityPanel
        projectId="proj-1"
        facets={[]}
        anchorsByFacet={{}}
      />,
    );
    const input = container.querySelector(
      "input[placeholder='facet key']",
    ) as HTMLInputElement;
    fireEvent.change(input, { target: { value: "hair" } });
    fireEvent.submit(input.closest("form")!);
    await waitFor(() => expect(fetchMock).toHaveBeenCalled());
    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toContain("/api/projects/proj-1/visual-facets");
    expect(init.method).toBe("POST");
    expect(JSON.parse(init.body as string)).toEqual({
      target_kind: "entity",
      facet_key: "hair",
    });
  });

  it("toggles requirement via PATCH (M8E requirement editor)", async () => {
    const { container } = render(
      <VisualIdentityPanel
        projectId="proj-1"
        facets={[FACET]}
        anchorsByFacet={{}}
      />,
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
      <VisualIdentityPanel
        projectId="proj-1"
        facets={[FACET]}
        anchorsByFacet={{}}
      />,
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

  it("renders anchors with approved/unapproved state", () => {
    const { container } = render(
      <VisualIdentityPanel
        projectId="proj-1"
        facets={[FACET]}
        anchorsByFacet={{
          "facet-1": [
            {
              id: "anchor-1",
              visual_facet_id: "facet-1",
              entity_revision_id: "rev-1",
              feature_value_hash: null,
              feature_value_json: null,
              visual_context_entity_revision_id: null,
              approved_revision_id: null,
              created_at: "2026-01-01",
              updated_at: "2026-01-01",
            },
          ],
        }}
      />,
    );
    expect(container.textContent).toContain("no approved revision");
  });
});

describe("VisualContinuityPanel (M8 §72, pure display)", () => {
  afterEach(cleanup);

  function state(
    over: Partial<VisualContinuityState>,
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

  it("renders approved + not-applicable statuses with the pack hash", () => {
    const { container } = render(
      <VisualContinuityPanel
        state={state({
          visual_reference_pack_hash: "a".repeat(64),
          facet_statuses: [
            {
              visual_facet_id: "f1",
              facet_key: "face",
              target_kind: "entity",
              entity_id: "eva",
              feature_id: null,
              requirement: "required",
              resolved: "approved",
              visual_anchor_id: "a1",
              approved_revision_id: "rev1",
            },
            {
              visual_facet_id: "f2",
              facet_key: "cut",
              target_kind: "feature",
              entity_id: null,
              feature_id: "feat",
              requirement: "not_applicable",
              resolved: "not_applicable",
              visual_anchor_id: null,
              approved_revision_id: null,
            },
          ],
        })}
      />,
    );
    expect(container.textContent).toContain("approved");
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

  it("renders visual blockers with per-facet missing detail", () => {
    const { container } = render(
      <VisualContinuityPanel
        state={state({
          visual_continuity_ready: false,
          visual_continuity_issues: [
            { error_code: "VISUAL_REALIZATION_REQUIRED" },
          ],
          facet_statuses: [
            {
              visual_facet_id: "f1",
              facet_key: "signage",
              target_kind: "entity",
              entity_id: "lobby",
              feature_id: null,
              requirement: "required",
              resolved: "missing",
              visual_anchor_id: null,
              approved_revision_id: null,
            },
          ],
        })}
      />,
    );
    expect(container.textContent).toContain("NOT ready");
    expect(container.textContent).toContain("signage");
    expect(container.textContent).toContain("missing realization");
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
