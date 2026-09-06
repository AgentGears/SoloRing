/**
 * Client-contract serialization proof: examines the ACTUAL fetch body the
 * browser client sends — never mocking away the client layer.
 *
 * Verifies previewIdentityOperation wraps {scope, request} exactly as the
 * corrected backend's PreviewRequest demands.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const fetchMock = vi.fn();
globalThis.fetch = fetchMock as unknown as typeof fetch;

import { previewIdentityOperation } from "@/lib/api.client";

beforeEach(() => {
  vi.clearAllMocks();
  fetchMock.mockResolvedValue({
    ok: true,
    json: async () => ({
      allowed: true, working_version: 1, normalized_request: {},
      request_fingerprint: "f".repeat(64),
      impact_fingerprint: "e".repeat(64),
      source_occurrence_summaries: [],
      historical_reference_counts: {},
      live_blocking_references: [],
    }),
  });
});

afterEach(() => {
  vi.restoreAllMocks();
});

describe("previewIdentityOperation serialization", () => {
  it("sends the scope-wrapped PreviewRequest body the backend requires", async () => {
    const request = {
      kind: "replace_as_new",
      source_occurrence_ids: ["occ-1"],
      target_working_specs: [{
        display_name: "Chair 8",
        source: { kind: "production_revision", revision_id: "pr-3" },
        visible: true,
        transform: { translation_mm: [0, 0, 0], rotation_udeg: [0, 0, 0] },
      }],
    };
    await previewIdentityOperation("comp-1", {
      scope: "composition_working_state",
      request,
    });

    expect(fetchMock).toHaveBeenCalledTimes(1);
    const [url, init] = fetchMock.mock.calls[0];
    expect(String(url)).toBe(
      "/api/compositions/comp-1/identity-operations/preview");
    const body = JSON.parse(String(init.body));
    // exact backend PreviewRequest shape
    expect(Object.keys(body).sort()).toEqual(["request", "scope"]);
    expect(body.scope).toBe("composition_working_state");
    expect(body.request).toEqual(request);
    // a raw unwrapped body (the F7 residual shape) would miss `scope`
    expect(body.request.kind).toBe("replace_as_new");
  });
});
