import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import {
  AuthoritySubjectRow,
  BindingPanel,
  ShotProductionWorldCard,
  SpatialInterpretationSection,
} from "@/components/ProductionWorldPanel";

const fetchMock = vi.fn();
globalThis.fetch = fetchMock as unknown as typeof fetch;

function jsonResponse(body: unknown, status = 200) {
  return {
    ok: status >= 200 && status < 300, status,
    json: () => Promise.resolve(body),
  } as Response;
}

const CID = "11111111-1111-1111-1111-111111111111";
const OID = "22222222-2222-2222-2222-222222222222";
const PRID = "33333333-3333-3333-3333-333333333333";
const CRID = "44444444-4444-4444-4444-444444444444";
const WRID = "55555555-5555-5555-5555-555555555555";
const BID = "66666666-6666-6666-6666-666666666666";
const SHOT = "77777777-7777-7777-7777-777777777777";

afterEach(cleanup);

beforeEach(() => {
  fetchMock.mockReset();
});

describe("M13 UI: authority subject (§25.2)", () => {
  it("renders composition-local and offers explicit one-way adoption",
     async () => {
    fetchMock.mockResolvedValueOnce(jsonResponse({
      composition_id: CID, occurrence_id: OID,
      subject_kind: "composition_local", subject_id: null,
      creative_entity_id: null, created_at: null }));
    render(<AuthoritySubjectRow compositionId={CID} occurrenceId={OID} />);
    expect(await screen.findByText(/Composition-local/)).toBeTruthy();
    expect(screen.getByText(/cannot be edited or rebound/)).toBeTruthy();
  });

  it("renders a production instance subject without adoption controls",
     async () => {
    fetchMock.mockResolvedValueOnce(jsonResponse({
      composition_id: CID, occurrence_id: OID,
      subject_kind: "production_instance", subject_id: OID,
      creative_entity_id: null, created_at: "t" }));
    render(<AuthoritySubjectRow compositionId={CID} occurrenceId={OID} />);
    expect(await screen.findByText(/Production Instance/)).toBeTruthy();
    expect(screen.queryByText(/Adopt Production Instance/)).toBeNull();
  });
});

describe("M13 UI: binding panel (§25.2)", () => {
  it("shows ready/blocked, subject + A4 counts, hash, publish action",
     async () => {
    fetchMock.mockResolvedValueOnce(jsonResponse({
      ready: true, issues: [], proposed_binding_hash: "a".repeat(64),
      composition_revision_id: CRID, composition_revision_hash: "b".repeat(64),
      spatial_world_revision_id: WRID, spatial_world_revision_hash:
        "c".repeat(64),
      subject_summaries: [{ occurrence_id: OID }, { occurrence_id: OID }],
      entry_summaries: [{ occurrence_id: OID,
                          placement: { kind: "entity_track", id: "x" } }] }));
    render(<BindingPanel compositionRevisionId={CRID}
                          worldRevisionId={WRID} />);
    expect(await screen.findByTestId("binding-ready").then(
      (e) => e.textContent)).toBe("ready");
    expect(screen.getByText("subjects: 2")).toBeTruthy();
    expect(screen.getByText("A4-bound: 1")).toBeTruthy();
    expect(screen.getByText("Publish exact binding")).toBeTruthy();
  });

  it("shows the full ordered issue list when blocked", async () => {
    fetchMock.mockResolvedValueOnce(jsonResponse({
      ready: false,
      issues: [{ code: "BINDING_PROJECT_MISMATCH" },
               { code: "BINDING_SPATIAL_TARGET_CONFLICT" }],
      proposed_binding_hash: "a".repeat(64),
      composition_revision_id: CRID, composition_revision_hash: "b".repeat(64),
      spatial_world_revision_id: WRID, spatial_world_revision_hash:
        "c".repeat(64),
      subject_summaries: [], entry_summaries: [] }));
    render(<BindingPanel compositionRevisionId={CRID}
                          worldRevisionId={WRID} />);
    await screen.findByTestId("binding-ready");
    expect(screen.getByText("BINDING_PROJECT_MISMATCH")).toBeTruthy();
    expect(screen.getByText("BINDING_SPATIAL_TARGET_CONFLICT")).toBeTruthy();
    expect(screen.queryByText("Publish exact binding")).toBeNull();
  });
});

describe("M13 UI: spatial interpretation (§25.1)", () => {
  it("shows availability and the irreversibility warning", async () => {
    fetchMock.mockResolvedValueOnce(jsonResponse({
      production_revision_id: PRID, interpretation_hash: "d".repeat(64) }));
    render(<SpatialInterpretationSection revisionId={PRID} />);
    expect(await screen.findByText(/available — hash/)).toBeTruthy();
    expect(screen.getByText(/millimeters, microdegrees/)).toBeTruthy();
  });

  it("offers creation with the correction warning when absent",
     async () => {
    fetchMock.mockResolvedValueOnce(jsonResponse({ error_code:
      "PRODUCTION_SPATIAL_INTERPRETATION_NOT_FOUND" }, 404));
    render(<SpatialInterpretationSection revisionId={PRID} />);
    expect(await screen.findByText("absent")).toBeTruthy();
    expect(screen.getByText(/cannot be edited\s+or deleted/)).toBeTruthy();
  });
});

describe("M13 UI: shot production-world card (§25.4)", () => {
  it("distinguishes ready / selected-but-stale / absent and shows the "
     + "explicit reselect workflow", async () => {
    // first render: selected but stale
    fetchMock.mockResolvedValueOnce(jsonResponse({
      shot_id: SHOT, selected: true, binding_id: BID,
      binding_hash: "e".repeat(64), binding_current_complete: false,
      stale_details: [{ code: "BINDING_STALE_SUBJECT_SET_CHANGED" }],
      ready: false, issues: [] }));
    render(<ShotProductionWorldCard shotId={SHOT} />);
    expect(await screen.findByTestId("production-world-state").then(
      (e) => e.textContent)).toBe("selected-but-stale");
    expect(screen.getByText(/inspect the current/)).toBeTruthy();
    expect(screen.getByText("BINDING_STALE_SUBJECT_SET_CHANGED"))
      .toBeTruthy();
  });

  it("renders absent with explicit exact-binding selection (no latest)",
     async () => {
    fetchMock.mockResolvedValueOnce(jsonResponse({
      shot_id: SHOT, selected: false, binding_id: null, binding_hash: null,
      binding_current_complete: null, stale_details: [], ready: true,
      issues: [] }));
    render(<ShotProductionWorldCard shotId={SHOT} />);
    expect(await screen.findByTestId("production-world-state").then(
      (e) => e.textContent)).toBe("absent");
    expect(screen.getByPlaceholderText("exact binding id")).toBeTruthy();
    expect(screen.queryByText(/latest/i)).toBeNull();
  });
});
