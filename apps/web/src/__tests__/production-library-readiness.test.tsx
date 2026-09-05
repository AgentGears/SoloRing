/** M11-UI:02 — unresolved blocker disables Publish; blocker is visible. */
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { Asset, ProductionObject } from "@/lib/types";

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
    blob_hash: "b".repeat(64),
    detected_media_type: null,
    upload_mime_type: null,
    original_filename: "cross.png",
    width: null,
    height: null,
    duration_ms: null,
    fps: null,
    created_at: "2026-01-01T00:00:00Z",
    blob_url: "/api/blobs/" + "b".repeat(64),
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

afterEach(cleanup);

describe("ProductionLibrary readiness honesty", () => {
  beforeEach(() => {
    vi.mocked(client.listProductionRevisions).mockResolvedValue([]);
    vi.mocked(client.getPublicationReadiness).mockResolvedValue({
      production_object_id: "obj-1",
      source_asset_id: "asset-1",
      ready: false,
      issues: [
        {
          code: "SOURCE_PROJECT_MISMATCH",
          message: "candidate Asset belongs to another Project",
          details: {},
        },
      ],
      proposed_snapshot_hash: null,
      closure: null,
    });
  });

  it("unresolved blocker disables publish", async () => {
    render(<ProductionLibrary projectId="p1" />);
    await waitFor(() => expect(screen.getByTestId("object-id-obj-1")).toBeTruthy());
    await userEvent.click(screen.getByRole("button", { name: /^Desk$/ }));
    await waitFor(() =>
      expect(screen.getByText(/Production Object: Desk/)).toBeTruthy(),
    );
    await userEvent.selectOptions(screen.getByLabelText("Candidate Asset"), "asset-1");
    await userEvent.click(screen.getByRole("button", { name: "Preview Readiness" }));

    await waitFor(() =>
      expect(screen.getByTestId("readiness-blockers")).toBeTruthy(),
    );
    expect(screen.getByTestId("readiness-blockers").textContent).toContain(
      "SOURCE_PROJECT_MISMATCH",
    );
    expect(
      (screen.getByTestId("publish-button") as HTMLButtonElement).disabled,
    ).toBe(true);
    // The UI never fabricates a ready state: no ready panel is rendered.
    expect(screen.queryByTestId("readiness-ready")).toBeNull();
  });
});
