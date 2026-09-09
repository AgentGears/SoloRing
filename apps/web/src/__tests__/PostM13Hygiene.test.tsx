import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

/**
 * HYG-FE:01–04 — reachable-surface DOM hygiene: the World/Set workspace
 * renders occurrences with valid list nesting (no <li> in <li>), and a
 * targeted console guard makes SoloRing-attributable validateDOMNesting
 * output fatal.
 */

const fetchMock = vi.fn();
globalThis.fetch = fetchMock as unknown as typeof fetch;

function jsonResponse(body: unknown, status = 200) {
  return {
    ok: status >= 200 && status < 300, status,
    json: () => Promise.resolve(body),
  } as Response;
}

function captureConsole(errors: string[]) {
  const orig = console.error;
  console.error = (...a: unknown[]) => { errors.push(a.map(String).join(" ")); };
  return () => { console.error = orig; };
}

afterEach(cleanup);

beforeEach(() => {
  fetchMock.mockReset();
});

describe("Post-M13 hygiene: reachable DOM surface", () => {
  it("World/Set workspace renders occurrences with valid nesting and no "
     + "SoloRing validateDOMNesting output (HYG-FE:01/02/04)", async () => {
    fetchMock.mockImplementation(async (url: unknown) => jsonResponse(
      String(url).includes("publication-readiness") ? null : []));
    vi.doMock("@/lib/api.client", () => ({
      getJson: vi.fn(async (url: string) =>
        String(url).includes("publication-readiness") ? null : []),
      getAuthoritySubject: vi.fn(async () => ({
        composition_id: "c1", occurrence_id: "occ-1",
        subject_kind: "composition_local", subject_id: null,
        creative_entity_id: null, created_at: null })),
      listCompositionRevisionsPublic: vi.fn(async () => []),
      listCompositions: vi.fn(async () => [{
        id: "c1", project_id: "p1", name: "Lobby", description: null,
        metadata_version: 0, working_version: 1,
        created_at: "t", updated_at: "t" }]),
      listOccurrences: vi.fn(async () => [
        {
          occurrence_id: "occ-1", display_name: "Chair 7",
          source_kind: "production_revision", production_revision_id: "pr",
          visible: 1, x_mm: 0, y_mm: 0, z_mm: 0, yaw_udeg: 0,
          pitch_udeg: 0, roll_udeg: 0 },
        {
          occurrence_id: "occ-2", display_name: "Nested",
          source_kind: "composition_revision",
          nested_composition_revision_id: "nr",
          visible: 1, x_mm: 0, y_mm: 0, z_mm: 0, yaw_odeg: 0,
          pitch_udeg: 0, roll_udeg: 0 },
      ]),
    }));
    const { default: WorldSetWorkspace } = await import(
      "@/components/WorldSetWorkspace");
    const errors: string[] = [];
    const restore = captureConsole(errors);
    try {
      render(<WorldSetWorkspace projectId="p1" />);
      fireEvent.click(await screen.findByText("Lobby"));
      await screen.findByTestId("occurrence-list");
      await new Promise((r) => setTimeout(r, 250));
    } finally {
      restore();
    }
    const nesting = errors.filter((e) => e.includes("validateDOMNesting"));
    expect(nesting, nesting.join("\n")).toEqual([]);
    // the occurrence list rendered with both children (HYG-FE:03:
    // interaction/display preserved — subject rows still render inside
    // the occurrence items)
    expect(screen.getByTestId("occ-occ-1")).toBeTruthy();
    expect(screen.getByText(/Chair 7/)).toBeTruthy();
    expect(screen.getByText(/unsupported\/deferred/)).toBeTruthy();
  });

  it("the console guard itself is live: a synthesized "
     + "validateDOMNesting error fails the assertion (guard self-test)",
     async () => {
    const errors: string[] = [];
    const restore = captureConsole(errors);
    try {
      console.error("Warning: validateDOMNesting(...): <li> cannot appear"
        + " as a descendant of <li>.");
    } finally {
      restore();
    }
    expect(errors.filter((e) => e.includes("validateDOMNesting")))
      .toHaveLength(1);
  });
});
