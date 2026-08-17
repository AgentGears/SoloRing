/**
 * Audit remediation F4 — reference identity is (asset_id, role).
 *
 * The backend legally allows the same Asset under multiple roles. Every
 * mutation callback must therefore carry the COMPLETE occurrence identity;
 * these tests pin remove / role-change / move against one asset held under
 * two roles so the wrong occurrence can never be mutated or dropped.
 */
import { cleanup, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { Asset, ReferenceItem } from "@/lib/types";

const replaceReferences = vi.fn();

vi.mock("@/lib/api.client", () => ({
  replaceReferences: (...args: unknown[]) => replaceReferences(...args),
  uploadAsset: vi.fn(),
  toBlobUrl: (url: string) => url,
}));

vi.mock("next/navigation", () => ({
  useRouter: () => ({ refresh: vi.fn() }),
}));

import ReferencePanel from "@/components/ReferencePanel";

const ASSET_A: Asset = {
  id: "asset-aaaa",
  project_id: "p1",
  take_id: null,
  kind: "reference",
  blob_hash: "a".repeat(64),
  detected_media_type: "image/png",
  upload_mime_type: "image/png",
  original_filename: "shared.png",
  width: 64,
  height: 64,
  duration_ms: null,
  fps: null,
  created_at: "2026-01-01T00:00:00Z",
  blob_url: "/api/blobs/" + "a".repeat(64),
};
const ASSET_B: Asset = {
  ...ASSET_A,
  id: "asset-bbbb",
  blob_hash: "b".repeat(64),
  blob_url: "/api/blobs/" + "b".repeat(64),
  original_filename: "other.png",
};
const ASSET_C: Asset = {
  ...ASSET_A,
  id: "asset-cccc",
  blob_hash: "c".repeat(64),
  blob_url: "/api/blobs/" + "c".repeat(64),
  original_filename: "third.png",
};

function ref(asset: Asset, role: string, position: number): ReferenceItem {
  return {
    asset_id: asset.id,
    role,
    position,
    created_at: "2026-01-01T00:00:00Z",
  };
}

/** The canonical echo the server would return for a desired set. */
function normalize(
  desired: { asset_id: string; role: string }[],
): ReferenceItem[] {
  const counts = new Map<string, number>();
  return [...desired]
    .sort((x, y) =>
      x.role === y.role
        ? x.role.localeCompare(y.role) === 0
          ? 0
          : x.role.localeCompare(y.role)
        : x.role.localeCompare(y.role),
    )
    .map((d) => {
      const n = counts.get(d.role) ?? 0;
      counts.set(d.role, n + 1);
      return { ...d, position: n, created_at: "2026-01-01T00:00:00Z" };
    });
}

function renderPanel(
  references: ReferenceItem[],
  assets: Asset[] = [ASSET_A, ASSET_B, ASSET_C],
) {
  render(
    <ReferencePanel
      shotId="shot-1"
      projectId="p1"
      initialReferences={references}
      initialAssets={assets}
    />,
  );
}

function groupFor(role: string): HTMLElement {
  const groups = screen.getAllByText(role, { selector: "code" });
  const heading = groups.find((el) => el.closest(".role-group") !== null);
  expect(heading, `role group ${role} rendered`).toBeTruthy();
  return heading!.closest(".role-group") as HTMLElement;
}

async function clickIn(
  group: HTMLElement,
  label: string | RegExp,
  name: string,
) {
  const row = within(group).getAllByText(name, { selector: ".name" })[
    0
  ].closest(".ref-row") as HTMLElement;
  await userEvent.click(within(row).getByRole("button", { name: label }));
  await waitFor(() => expect(replaceReferences).toHaveBeenCalled());
}

function lastDesired(): { asset_id: string; role: string }[] {
  return replaceReferences.mock.calls.at(-1)![1];
}

beforeEach(() => {
  replaceReferences.mockReset();
  replaceReferences.mockImplementation(async (_sid: string, desired: []) =>
    normalize(desired),
  );
});
afterEach(cleanup);

describe("reference occurrence identity is (asset_id, role)", () => {
  it("removes only the targeted occurrence of a dual-role asset", async () => {
    renderPanel([
      ref(ASSET_A, "character", 0),
      ref(ASSET_B, "character", 1),
      ref(ASSET_A, "style", 0),
    ]);

    await clickIn(groupFor("character"), "Remove", "shared.png");

    expect(lastDesired()).toEqual([
      { asset_id: ASSET_B.id, role: "character" },
      { asset_id: ASSET_A.id, role: "style" },
    ]);
  });

  it("changes the role of only the targeted occurrence", async () => {
    renderPanel([
      ref(ASSET_A, "character", 0),
      ref(ASSET_A, "style", 0),
    ]);

    const group = groupFor("style");
    const row = within(group)
      .getAllByText("shared.png", { selector: ".name" })[0]
      .closest(".ref-row") as HTMLElement;
    const input = within(row).getByLabelText("Role");
    await userEvent.clear(input);
    await userEvent.type(input, "mood");
    await userEvent.click(within(row).getByRole("button", { name: "Move role" }));
    await waitFor(() => expect(replaceReferences).toHaveBeenCalled());

    expect(lastDesired()).toEqual([
      { asset_id: ASSET_A.id, role: "character" },
      { asset_id: ASSET_A.id, role: "mood" },
    ]);
  });

  it("moves the occurrence inside its own role group, not a same-asset sibling", async () => {
    // A is the SECOND item of "zeta" and the only item of "alpha". The old
    // asset_id-only lookup found the alpha occurrence (no-op) instead of
    // moving the zeta one.
    renderPanel([
      ref(ASSET_A, "alpha", 0),
      ref(ASSET_C, "zeta", 0),
      ref(ASSET_A, "zeta", 1),
    ]);

    await clickIn(groupFor("zeta"), "Move up within role", "shared.png");

    const desired = lastDesired();
    const zeta = desired.filter((d) => d.role === "zeta");
    expect(zeta).toEqual([
      { asset_id: ASSET_A.id, role: "zeta" },
      { asset_id: ASSET_C.id, role: "zeta" },
    ]);
    expect(desired).toContainEqual({ asset_id: ASSET_A.id, role: "alpha" });
  });

  it("attach still rejects an exact (asset_id, role) duplicate only", async () => {
    renderPanel([ref(ASSET_A, "character", 0)]);

    await userEvent.selectOptions(
      screen.getByLabelText("Asset"),
      ASSET_A.id,
    );
    const roleInput = screen.getAllByLabelText("Role").find((el) => el.closest(".form-row"))!;
    await userEvent.clear(roleInput);
    await userEvent.type(roleInput, "style"); // different role: legal
    await userEvent.click(screen.getByRole("button", { name: "Attach" }));
    await waitFor(() => expect(replaceReferences).toHaveBeenCalled());

    expect(lastDesired()).toEqual([
      { asset_id: ASSET_A.id, role: "character" },
      { asset_id: ASSET_A.id, role: "style" },
    ]);
  });
});
