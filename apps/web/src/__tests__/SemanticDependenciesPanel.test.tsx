/**
 * M6C — semantic dependency panel interactions.
 *
 * Attach/remove must send the COMPLETE dependency set (full-set contract),
 * and only entities WITH an approved revision are offered for attachment.
 */
import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { Entity, SemanticDependency } from "@/lib/types";

const putSemanticDependencies = vi.fn();

vi.mock("@/lib/api.client", () => ({
  putSemanticDependencies: (
    ...args: unknown[]
  ) => putSemanticDependencies(...args),
}));

vi.mock("next/navigation", () => ({
  useRouter: () => ({ refresh: vi.fn() }),
}));

import { SemanticDependenciesPanel } from "@/components/SemanticDependenciesPanel";

const ENTITY_APPROVED: Entity = {
  id: "entity-eva",
  project_id: "p1",
  kind: "character",
  name: "Eva",
  description: null,
  created_at: "2026-01-01T00:00:00Z",
  updated_at: "2026-01-01T00:00:00Z",
  approved_revision_id: "rev-1",
};
const ENTITY_UNAPPROVED: Entity = {
  ...ENTITY_APPROVED,
  id: "entity-raw",
  name: "Unapproved",
  approved_revision_id: null,
};

const DEP_EVA: SemanticDependency = {
  entity_id: "entity-eva",
  entity_kind: "character",
  entity_name: "Eva",
  role: "subject",
  position: 0,
  resolved_revision_id: "rev-1",
  resolved_revision_number: 12,
  resolved_revision_hash: "a".repeat(64),
};

describe("SemanticDependenciesPanel (M6C full-set payloads)", () => {
  beforeEach(() => {
    putSemanticDependencies.mockReset().mockResolvedValue(undefined);
  });
  afterEach(cleanup);

  it("remove sends the remaining full set", async () => {
    render(
      <SemanticDependenciesPanel
        shotId="shot-1"
        initialDependencies={[DEP_EVA]}
        entities={[ENTITY_APPROVED]}
      />,
    );
    await userEvent.click(screen.getByLabelText(/Remove Eva/));
    expect(putSemanticDependencies).toHaveBeenCalledWith("shot-1", []);
  });

  it("attach appends to the full set", async () => {
    render(
      <SemanticDependenciesPanel
        shotId="shot-1"
        initialDependencies={[DEP_EVA]}
        entities={[ENTITY_APPROVED, ENTITY_UNAPPROVED]}
      />,
    );
    const select = screen.getByLabelText("Entity");
    // Only approved entities are offered.
    const options = Array.from(select.querySelectorAll("option")).map(
      (o) => o.value,
    );
    expect(options).toContain("entity-eva");
    expect(options).not.toContain("entity-raw");
    await userEvent.selectOptions(select, "entity-eva");
    await userEvent.type(
      screen.getByPlaceholderText(/role \(e\.g\. subject\)/i),
      "reflection_subject",
    );
    await userEvent.click(screen.getByRole("button", { name: /attach/i }));
    expect(putSemanticDependencies).toHaveBeenCalledWith("shot-1", [
      { entity_id: "entity-eva", role: "subject" },
      { entity_id: "entity-eva", role: "reflection_subject" },
    ]);
  });
});
