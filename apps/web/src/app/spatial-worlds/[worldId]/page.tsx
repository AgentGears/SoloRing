// M10B §50 + M10C §10 — Spatial World workspace route (reachable
// surface): world editor + current staging inspector.

import { SpatialWorldPanel } from "@/components/SpatialWorldPanel";
import { StagingInspector } from "@/components/StagingInspector";

export default async function SpatialWorldPage({
  params,
}: {
  params: Promise<{ worldId: string }>;
}) {
  const { worldId } = await params;
  return (
    <main className="container">
      <h1>Spatial World</h1>
      <SpatialWorldPanel worldId={worldId} />
      <StagingInspector worldId={worldId} />
    </main>
  );
}
