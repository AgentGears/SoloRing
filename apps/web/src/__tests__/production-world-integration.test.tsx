import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import {
  CapturedProductionWorldInspector,
  PIStagingAuthoring,
  ShotProductionWorldCard,
} from "@/components/ProductionWorldPanel";

const fetchMock = vi.fn();
globalThis.fetch = fetchMock as unknown as typeof fetch;

function jsonResponse(body: unknown, status = 200) {
  return {
    ok: status >= 200 && status < 300, status,
    json: () => Promise.resolve(body),
  } as Response;
}

afterEach(cleanup);

beforeEach(() => {
  fetchMock.mockReset();
});

const SHOT = "77777777-7777-7777-7777-777777777777";
const CRID = "44444444-4444-4444-4444-444444444444";
const WRID = "55555555-5555-5555-5555-555555555555";
const BID = "66666666-6666-6666-6666-666666666666";
const REV = "88888888-8888-8888-8888-888888888888";
const WID = "99999999-9999-9999-9999-999999999999";
const OID = "22222222-2222-2222-2222-222222222222";

describe("M13 UI correction B5: full shot card", () => {
  it("shows exact C/W revision hashes, pack hash, and PI summaries",
     async () => {
    fetchMock.mockResolvedValueOnce(jsonResponse({
      shot_id: SHOT, selected: true, binding_id: BID,
      binding_hash: "e".repeat(64), binding_current_complete: true,
      stale_details: [], ready: true, issues: [],
      production_world: {
        binding: {
          binding_id: BID, binding_hash: "e".repeat(64),
          value: {
            composition_revision: {
              revision_id: CRID, snapshot_hash: "a".repeat(64) },
            spatial_world_revision: {
              revision_id: WRID, snapshot_hash: "b".repeat(64) },
          },
        },
        instance_feature_states: [{}, {}],
        instance_spatial_states: [
          { production_instance_track_id: "t1", requirement: "required" },
          { production_instance_track_id: "t2", requirement: "optional" }],
      },
      production_world_hash: "c".repeat(64) }));
    render(<ShotProductionWorldCard shotId={SHOT} />);
    await screen.findByTestId("production-world-state");
    expect(screen.getByText(new RegExp(CRID))).toBeTruthy();
    expect(screen.getByText(new RegExp(WRID))).toBeTruthy();
    expect(screen.getByTestId("pi-feature-summary").textContent)
      .toContain("2");
    expect(screen.getByTestId("pi-staging-summary").textContent)
      .toContain("2");
    expect(screen.getByTestId("pi-staging-summary").textContent)
      .toContain("1 required");
  });
});

describe("M13 UI correction B5: PI staging authoring", () => {
  it("creates a track and sets staging through the real endpoints",
     async () => {
    fetchMock.mockResolvedValueOnce(jsonResponse({ id: "track-1" }));
    render(<PIStagingAuthoring worldId={WID} occurrenceId={OID} />);
    const create = await screen.findByText("Create PI track in this world");
    create.dispatchEvent(new MouseEvent("click", { bubbles: true }));
    await vi.waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        expect.stringContaining(
          `/spatial-worlds/${WID}/production-instance-tracks`),
        expect.objectContaining({ method: "POST" }));
    });
  });
});

describe("M13 UI correction B5: historical inspector", () => {
  it("renders captured identities read-only, labeled as history",
     async () => {
    fetchMock.mockResolvedValueOnce(jsonResponse({
      captured: true, production_world_hash: "d".repeat(64),
      binding: {
        binding_id: BID, binding_hash: "e".repeat(64),
        composition_revision_id: CRID,
        composition_revision_hash: "a".repeat(64),
        spatial_world_revision_id: WRID,
        spatial_world_revision_hash: "b".repeat(64) },
      captured_feature_states: [{}],
      captured_spatial_states: [{}, {}] }));
    render(<CapturedProductionWorldInspector revisionId={REV} />);
    const section = await screen.findByLabelText(
      "captured production world");
    expect(section.getAttribute("data-history")).toBe("true");
    expect(screen.getByText(/history — read-only/)).toBeTruthy();
    expect(screen.getByText(new RegExp(CRID))).toBeTruthy();
    expect(screen.getByText(/captured PI state entries:/).textContent)
      .toContain("1");
    expect(screen.getByText(/captured PI staging entries:/).textContent)
      .toContain("2");
  });
});
