import { describe, expect, it, vi } from "vitest";

/**
 * M13 round-4 regression: the /api browser boundary is mechanical.
 * Every M13 browser-side call must go through api.client.ts helpers
 * (BASE="/api"); the M13 product components must contain no
 * NEXT_PUBLIC_API_ORIGIN or absolute-origin URL construction.
 */
describe("M13 UI /api boundary", () => {
  it("M13 product components never construct raw-origin URLs", async () => {
    const fs = await import("node:fs");
    const path = await import("node:path");
    const files = [
      "src/components/ProductionWorldPanel.tsx",
      "src/components/PIStagingMount.tsx",
      "src/components/ProductionLibrary.tsx",
      "src/components/WorldSetWorkspace.tsx",
    ];
    for (const rel of files) {
      const src = fs.readFileSync(
        path.resolve(process.cwd(), rel), "utf-8");
      expect(src, `${rel} must not use NEXT_PUBLIC_API_ORIGIN`)
        .not.toContain("NEXT_PUBLIC_API_ORIGIN");
    }
  });

  it("the M13 api.client helpers fetch canonical /api URLs", async () => {
    const fetchMock = vi.fn(
      async (..._a: unknown[]) => ({
        ok: true, status: 200, json: async () => ([]),
      } as Response));
    globalThis.fetch = fetchMock as unknown as typeof fetch;
    const client = await import("@/lib/api.client");
    await client.listProductionInstanceTracks("w1");
    await client.getCapturedProductionWorld("r1");
    await client.listCompositionRevisionsPublic("c1");
    await client.createProductionInstanceTrack("w1", "o1", "optional");
    await client.createProductionInstanceSpatialTransition("t1", {
      anchor_type: "sequence", anchor_id: "a", boundary: "start",
      operation: "set",
      transform: { translation_mm: [0, 0, 0], rotation_udeg: [0, 0, 0] } });
    const urls = fetchMock.mock.calls.map(
      (c: unknown[]) => String(c[0]));
    expect(urls.every((u) => u.startsWith("/api/"))).toBe(true);
    expect(urls).toContain("/api/spatial-worlds/w1/production-instance-tracks");
    expect(urls).toContain("/api/shot-revisions/r1/production-world");
    expect(urls).toContain("/api/compositions/c1/revisions");
    expect(urls).toContain(
      "/api/production-instance-spatial-tracks/t1/transitions");
  });
});
