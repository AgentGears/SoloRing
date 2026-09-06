/**
 * M11-UI:01 — candidate → readiness → publish → revision inspection.
 * M11-UI:04 — duplicate display names are disambiguated by stable id.
 */
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { Asset, ProductionObject, ProductionRevisionDetail } from "@/lib/types";

const listProductionObjects = vi.fn();
const createProductionObject = vi.fn();
const getPublicationReadiness = vi.fn();
const publishProductionRevision = vi.fn();
const listProductionRevisions = vi.fn();
const getProductionRevision = vi.fn();

vi.mock("@/lib/api.client", () => ({
  listAssets: vi.fn(async () => ASSETS),
  listProductionObjects: (...a: unknown[]) => listProductionObjects(...a),
  createProductionObject: (...a: unknown[]) => createProductionObject(...a),
  getPublicationReadiness: (...a: unknown[]) => getPublicationReadiness(...a),
  publishProductionRevision: (...a: unknown[]) => publishProductionRevision(...a),
  listProductionRevisions: (...a: unknown[]) => listProductionRevisions(...a),
  getProductionRevision: (...a: unknown[]) => getProductionRevision(...a),
}));

import ProductionLibrary from "@/components/ProductionLibrary";

const BLOB = "a".repeat(64);

const ASSETS: Asset[] = [
  {
    id: "asset-1",
    project_id: "p1",
    take_id: null,
    kind: "reference",
    blob_hash: BLOB,
    detected_media_type: "image/png",
    upload_mime_type: "image/png",
    original_filename: "desk.png",
    width: 64,
    height: 64,
    duration_ms: null,
    fps: null,
    created_at: "2026-01-01T00:00:00Z",
    blob_url: "/api/blobs/" + BLOB,
  },
];

const OBJ: ProductionObject = {
  id: "obj-1",
  project_id: "p1",
  name: "Reception Desk",
  description: null,
  created_at: "2026-01-01T00:00:00Z",
  updated_at: "2026-01-01T00:00:00Z",
};

const DETAIL: ProductionRevisionDetail = {
  revision_id: "rev-1",
  production_object_id: "obj-1",
  project_id: "p1",
  revision_number: 1,
  snapshot_json: "{}",
  snapshot_hash: "h".repeat(64),
  created_at: "2026-01-01T00:00:00Z",
  closure: {
    contract_key: "retained_blob",
    contract_version: 1,
    blob_hash: BLOB,
    size_bytes: 3,
    media_type: "image/png",
  },
  blob_url: "/api/blobs/" + BLOB.slice(0, 2) + "/" + BLOB.slice(2, 4) + "/" + BLOB,
  sources: [{ asset_id: "asset-1", created_at: "2026-01-01T00:00:00Z" }],
  physical_integrity: "not_full_hash_verified_in_this_view",
};

beforeEach(() => {
  vi.clearAllMocks();
  listProductionObjects.mockResolvedValue([]);
});

afterEach(cleanup);

describe("ProductionLibrary", () => {
  it("candidate readiness publish revision inspection", async () => {
    createProductionObject.mockResolvedValue(OBJ);
    listProductionObjects
      .mockResolvedValueOnce([])
      .mockResolvedValue([OBJ]);
    getPublicationReadiness.mockResolvedValue({
      production_object_id: "obj-1",
      source_asset_id: "asset-1",
      ready: true,
      issues: [],
      proposed_snapshot_hash: "h".repeat(64),
      closure: DETAIL.closure,
    });
    publishProductionRevision.mockResolvedValue(DETAIL);
    listProductionRevisions.mockResolvedValue([
      {
        revision_id: "rev-1",
        revision_number: 1,
        snapshot_hash: "h".repeat(64),
        created_at: "2026-01-01T00:00:00Z",
      },
    ]);
    getProductionRevision.mockResolvedValue(DETAIL);

    render(<ProductionLibrary projectId="p1" />);

    const name = screen.getByLabelText("New Production Object name");
    await userEvent.type(name, "Reception Desk");
    await userEvent.click(screen.getByRole("button", { name: "Create Production Object" }));

    await waitFor(() =>
      expect(screen.getByText(/Production Object: Reception Desk/)).toBeTruthy(),
    );

    await userEvent.selectOptions(screen.getByLabelText("Candidate Asset"), "asset-1");
    await userEvent.click(screen.getByRole("button", { name: "Preview Readiness" }));

    await waitFor(() =>
      expect(screen.getByTestId("readiness-ready")).toBeTruthy(),
    );
    expect(screen.getByTestId("proposed-snapshot-hash").textContent).toContain(
      "h".repeat(64),
    );

    await userEvent.click(screen.getByTestId("publish-button"));

    await waitFor(() => expect(screen.getByTestId("revision-detail")).toBeTruthy());
    expect(publishProductionRevision).toHaveBeenCalledWith("obj-1", "asset-1");
    const detail = screen.getByTestId("revision-detail");
    expect(detail.textContent).toContain("Revision 1");
    expect(detail.textContent).toContain("retained_blob");
  });

  it("duplicate object names are disambiguated by stable id", async () => {
    const twin = { ...OBJ, id: "obj-2" };
    listProductionObjects.mockResolvedValue([OBJ, twin]);
    render(<ProductionLibrary projectId="p1" />);
    await waitFor(() =>
      expect(screen.getByTestId("object-id-obj-1")).toBeTruthy(),
    );
    expect(screen.getByTestId("object-id-obj-2").textContent).toBe("obj-2");
    // Two buttons share the display name; the stable ids distinguish them.
    const named = screen.getAllByRole("button", { name: /Reception Desk/ });
    expect(named.length).toBe(2);
  });
});
