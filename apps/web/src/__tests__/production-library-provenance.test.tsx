/** M11-UI:03 — closure and source provenance rendered as distinct concepts. */
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { Asset, ProductionObject, ProductionRevisionDetail } from "@/lib/types";

vi.mock("@/lib/api.client", () => ({
  listAssets: vi.fn(async () => ASSETS),
  listProductionObjects: vi.fn(async () => [OBJ]),
  createProductionObject: vi.fn(),
  getPublicationReadiness: vi.fn(),
  publishProductionRevision: vi.fn(),
  listProductionRevisions: vi.fn(),
  getProductionRevision: vi.fn(),
}));

const client = await import("@/lib/api.client");
import ProductionLibrary from "@/components/ProductionLibrary";

const ASSETS: Asset[] = [
  {
    id: "asset-1",
    project_id: "p1",
    take_id: null,
    kind: "reference",
    blob_hash: "c".repeat(64),
    detected_media_type: "image/png",
    upload_mime_type: "image/png",
    original_filename: "desk.png",
    width: 64,
    height: 64,
    duration_ms: null,
    fps: null,
    created_at: "2026-01-01T00:00:00Z",
    blob_url: "/api/blobs/" + "c".repeat(64),
  },
];

const OBJ: ProductionObject = {
  id: "obj-1",
  project_id: "p1",
  name: "Desk",
  description: null,
  created_at: "2026-01-01T00:00:00Z",
  updated_at: "2026-01-01T00:00:00Z",
};

const BLOB = "c".repeat(64);

afterEach(cleanup);

describe("ProductionLibrary provenance separation", () => {
  beforeEach(() => {
    vi.mocked(client.getPublicationReadiness).mockResolvedValue({
      production_object_id: "obj-1",
      source_asset_id: "asset-1",
      ready: true,
      issues: [],
      proposed_snapshot_hash: "h".repeat(64),
      closure: {
        contract_key: "retained_blob",
        contract_version: 1,
        blob_hash: BLOB,
        size_bytes: 4,
        media_type: "image/png",
      },
    });
    vi.mocked(client.publishProductionRevision).mockResolvedValue(DETAIL());
    vi.mocked(client.listProductionRevisions).mockResolvedValue([
      {
        revision_id: "rev-1",
        revision_number: 1,
        snapshot_hash: "h".repeat(64),
        created_at: "2026-01-01T00:00:00Z",
      },
    ]);
    vi.mocked(client.getProductionRevision).mockResolvedValue(DETAIL());
  });

  it("closure and source provenance remain distinct", async () => {
    render(<ProductionLibrary projectId="p1" />);
    await waitFor(() => expect(screen.getByTestId("object-id-obj-1")).toBeTruthy());
    await userEvent.click(screen.getByRole("button", { name: /^Desk$/ }));
    await waitFor(() =>
      expect(screen.getByText(/Production Object: Desk/)).toBeTruthy(),
    );
    await userEvent.selectOptions(screen.getByLabelText("Candidate Asset"), "asset-1");
    await userEvent.click(screen.getByRole("button", { name: "Preview Readiness" }));
    await waitFor(() =>
      expect(screen.getByTestId("readiness-ready")).toBeTruthy(),
    );
    await userEvent.click(screen.getByTestId("publish-button"));

    await waitFor(() => expect(screen.getByTestId("revision-detail")).toBeTruthy());

    const closure = screen.getByTestId("consumption-closure");
    const provenance = screen.getByTestId("source-provenance");
    // Two separately-labelled sections: the retained consumption closure and
    // the append-only source provenance are never merged into one list.
    expect(closure.textContent).toContain("retained_blob");
    expect(closure.textContent).toContain(BLOB);
    expect(provenance.textContent).toContain("source Asset asset-1");
    expect(provenance.textContent).not.toContain("retained_blob");
    expect(closure.textContent).not.toContain("source Asset");
  });
});

function DETAIL(): ProductionRevisionDetail {
  return {
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
      size_bytes: 4,
      media_type: "image/png",
    },
    blob_url: "/api/blobs/cd/" + BLOB.slice(2, 4) + "/" + BLOB,
    sources: [{ asset_id: "asset-1", created_at: "2026-01-01T00:00:00Z" }],
    physical_integrity: "not_full_hash_verified_in_this_view",
  };
}
