import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import {
  AuthoritySubjectRow,
  BindingPanel,
  M13BindingLauncherScoped,
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

const CID = "11111111-1111-1111-1111-111111111111";
const OID = "22222222-2222-2222-2222-222222222222";
const CRID = "44444444-4444-4444-4444-444444444444";
const WRID = "55555555-5555-5555-5555-555555555555";

describe("M13 UI §25.2 contract (round 3)", () => {
  it("BindingPanel displays the selected exact C/W revision "
     + "identities and hashes", async () => {
    fetchMock.mockResolvedValueOnce(jsonResponse({
      ready: true, issues: [], proposed_binding_hash: "a".repeat(64),
      composition_revision_id: CRID,
      composition_revision_hash: "b".repeat(64),
      spatial_world_revision_id: WRID,
      spatial_world_revision_hash: "c".repeat(64),
      subject_summaries: [], entry_summaries: [] }));
    render(<BindingPanel compositionRevisionId={CRID}
                          worldRevisionId={WRID} />);
    await screen.findByTestId("binding-ready");
    expect(screen.getByText(new RegExp(CRID))).toBeTruthy();
    expect(screen.getByText(new RegExp(WRID))).toBeTruthy();
    expect(screen.getByText(/bbbbbbbbbbbbbbbb/)).toBeTruthy();
    expect(screen.getByText(/cccccccccccccccc/)).toBeTruthy();
  });

  it("nested occurrences show the frozen unsupported/deferred "
     + "presentation with no adoption controls", async () => {
    render(<AuthoritySubjectRow compositionId={CID} occurrenceId={OID}
                                nested={true} />);
    expect(screen.getByText(
      /promotion unsupported/)).toBeTruthy();
    expect(screen.getByText(/Nested Composition Revision sources/))
      .toBeTruthy();
    expect(screen.queryByText(/Adopt Production Instance/)).toBeNull();
    expect(screen.queryByText(/Adopt Creative Entity/)).toBeNull();
    // and it performs NO subject fetch (nested occurrences are outside
    // the schema-1 universe)
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("the binding launcher offers ONLY this composition's published "
     + "revisions", async () => {
    fetchMock.mockResolvedValueOnce(jsonResponse([
      { revision_id: CRID, revision_number: 2 },
      { revision_id: "eeeeeeee-eeee-eeee-eeee-eeeeeeeeeeee",
        revision_number: 1 }]));
    render(<M13BindingLauncherScoped compositionId={CID} />);
    const select = await screen.findByRole("combobox");
    const options = Array.from(
      select.querySelectorAll("option")).map((o) => o.value)
      .filter((v) => v !== "");  // placeholder expected
    expect(options).toContain(CRID);
    expect(options).toHaveLength(2);  // only this set's revisions
    // scoping proof: the fetch targeted THIS composition's revisions
    expect(fetchMock).toHaveBeenCalledWith(
      expect.stringContaining(`/compositions/${CID}/revisions`),
      expect.anything());
    // readiness cannot open until a revision of THIS set + a world are
    // chosen
    expect(screen.queryByLabelText(
      "composition spatial binding")).toBeNull();
    fireEvent.change(select, { target: { value: CRID } });
    fireEvent.change(screen.getByPlaceholderText(
      /SpatialWorldRevision UUID/),
      { target: { value: WRID } });
    fetchMock.mockResolvedValueOnce(jsonResponse({
      ready: true, issues: [], proposed_binding_hash: "a".repeat(64),
      composition_revision_id: CRID,
      composition_revision_hash: "b".repeat(64),
      spatial_world_revision_id: WRID,
      spatial_world_revision_hash: "c".repeat(64),
      subject_summaries: [], entry_summaries: [] }));
    fireEvent.click(screen.getByText("Open binding readiness"));
    expect(await screen.findByTestId("binding-ready")).toBeTruthy();
  });
});
