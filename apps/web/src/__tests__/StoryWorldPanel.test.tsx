/**
 * M6A — Story World approval CAS interaction.
 *
 * The ApproveRevisionButton must carry the entity's CURRENT approved id as
 * the CAS expectation (null for first approval), and a 409
 * ENTITY_APPROVAL_CONFLICT must surface as a visible error banner, never a
 * silent overwrite of story-world canon.
 */
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { Entity, EntityRevisionSummary } from "@/lib/types";

const approveEntityRevision = vi.fn();
const createEntityRevision = vi.fn();

vi.mock("@/lib/api.client", () => ({
  approveEntityRevision: (...args: unknown[]) => approveEntityRevision(...args),
  createEntityRevision: (...args: unknown[]) => createEntityRevision(...args),
  createEntity: vi.fn(),
  patchEntity: vi.fn(),
}));

vi.mock("next/navigation", () => ({
  useRouter: () => ({ refresh: vi.fn() }),
}));

import {
  ApproveRevisionButton,
  RevisionCreateForm,
} from "@/components/StoryWorldPanel";
import { ApiError } from "@/lib/api.shared";

const ENTITY: Entity = {
  id: "entity-aaaa",
  project_id: "p1",
  kind: "character",
  name: "Eva",
  description: null,
  created_at: "2026-01-01T00:00:00Z",
  updated_at: "2026-01-01T00:00:00Z",
  approved_revision_id: null,
};

const REV_1: EntityRevisionSummary = {
  id: "rev-1111",
  entity_id: ENTITY.id,
  revision_number: 1,
  schema_version: 1,
  spec_hash: "1".repeat(64),
  created_at: "2026-01-01T00:00:00Z",
};

const REV_2: EntityRevisionSummary = {
  ...REV_1,
  id: "rev-2222",
  revision_number: 2,
};

describe("ApproveRevisionButton (M6A CAS)", () => {
  beforeEach(() => {
    approveEntityRevision.mockReset();
  });
  afterEach(cleanup);

  it("sends the current approved id as the CAS expectation", async () => {
    approveEntityRevision.mockResolvedValue(undefined);
    render(
      <ApproveRevisionButton
        entity={{ ...ENTITY, approved_revision_id: REV_1.id }}
        revision={REV_2}
      />,
    );
    await userEvent.click(screen.getByRole("button", { name: /approve/i }));
    await waitFor(() => expect(approveEntityRevision).toHaveBeenCalledOnce());
    expect(approveEntityRevision).toHaveBeenCalledWith(
      ENTITY.id,
      REV_2.id,
      REV_1.id,
    );
  });

  it("sends null as the expectation for a first approval", async () => {
    approveEntityRevision.mockResolvedValue(undefined);
    render(<ApproveRevisionButton entity={ENTITY} revision={REV_1} />);
    await userEvent.click(screen.getByRole("button", { name: /approve/i }));
    await waitFor(() => expect(approveEntityRevision).toHaveBeenCalledOnce());
    expect(approveEntityRevision).toHaveBeenCalledWith(
      ENTITY.id,
      REV_1.id,
      null,
    );
  });

  it("renders APPROVED (no button) for the already-approved revision", () => {
    render(
      <ApproveRevisionButton
        entity={{ ...ENTITY, approved_revision_id: REV_1.id }}
        revision={REV_1}
      />,
    );
    expect(screen.getByText("APPROVED")).toBeTruthy();
    expect(
      screen.queryByRole("button", { name: /approve/i }),
    ).toBeNull();
  });

  it("surfaces ENTITY_APPROVAL_CONFLICT as a visible banner", async () => {
    approveEntityRevision.mockRejectedValue(
      new ApiError(
        "ENTITY_APPROVAL_CONFLICT",
        "Approved revision for entity changed.",
        409,
      ),
    );
    render(<ApproveRevisionButton entity={ENTITY} revision={REV_1} />);
    await userEvent.click(screen.getByRole("button", { name: /approve/i }));
    const banner = await screen.findByRole("alert");
    expect(banner.textContent).toContain("ENTITY_APPROVAL_CONFLICT");
  });
});

describe("RevisionCreateForm (M6A)", () => {
  beforeEach(() => {
    createEntityRevision.mockReset();
  });
  afterEach(cleanup);

  it("posts a v1 spec payload through the kind-agnostic form", async () => {
    createEntityRevision.mockResolvedValue(REV_1);
    render(<RevisionCreateForm entityId={ENTITY.id} />);
    await userEvent.type(
      screen.getByPlaceholderText(/design description/i),
      "Rain-soaked courier",
    );
    await userEvent.click(
      screen.getByRole("button", { name: /create design revision/i }),
    );
    await waitFor(() => expect(createEntityRevision).toHaveBeenCalledOnce());
    expect(createEntityRevision).toHaveBeenCalledWith(ENTITY.id, {
      schema_version: 1,
      description: "Rain-soaked courier",
      notes: null,
    });
  });
});
