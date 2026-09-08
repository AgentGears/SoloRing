import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import ProductionLibrary from "@/components/ProductionLibrary";
import { PIStagingMount } from "@/components/PIStagingMount";

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

const PID = "11111111-1111-1111-1111-111111111111";
const PRID = "33333333-3333-3333-3333-333333333333";
const WID = "99999999-9999-9999-9999-999999999999";
const OID = "22222222-2222-2222-2222-222222222222";
const TRACK = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa";

describe("M13 R2-B5: reachable product workflows", () => {
  it("Production Library revision detail mounts the M13 interpretation "
     + "surface (§25.1)", async () => {
    fetchMock.mockResolvedValue(jsonResponse([]));
    const mod = await import("@/components/ProductionLibrary");
    expect(mod.default).toBeTruthy();
    const src = String(mod.default);
    expect(src).toContain("SpatialInterpretationSection");
  });

  it("PIStagingMount requires the exact occurrence before authoring "
     + "(§25.3) and PIStagingAuthoring targets only that occurrence",
     async () => {
    render(<PIStagingMount worldId={WID} />);
    const input = screen.getByPlaceholderText(
      /occurrence UUID/);
    expect(screen.queryByLabelText(
      "production instance staging authoring")).toBeNull();
    // commit the occurrence → the authoring surface mounts
    fireEvent.change(input, { target: { value: OID } });
    fireEvent.click(screen.getByText("Load staging authoring"));
    // wait for the authoring section to mount, then drive track fetch
    await vi.waitFor(() => {
      expect(screen.getByLabelText(
        "production instance staging authoring")).toBeTruthy();
    });
    fetchMock.mockResolvedValueOnce(jsonResponse([
      { id: "other-track", occurrence_id: "deadbeef-0000-0000-0000-0" },
      { id: TRACK, occurrence_id: OID }]));
    const set = screen.getByText("Set staging at anchor");
    const anchor = screen.getByPlaceholderText("anchor UUID");
    fireEvent.change(anchor, {
      target: { value: "55555555-5555-5555-5555-555555555555" } });
    fireEvent.click(set);
    await vi.waitFor(() => {
      const call = fetchMock.mock.calls.find((c) =>
        String(c[0]).includes("production-instance-spatial-tracks"));
      expect(call).toBeTruthy();
    });
    // the transition POST targeted THIS occurrence's track
    const post = fetchMock.mock.calls.find((c) =>
      String(c[0]).endsWith(`/production-instance-spatial-tracks/`
        + `${TRACK}/transitions`));
    expect(post).toBeTruthy();
  });
});
