// M10B §50 — Spatial World workspace route (reachable surface).

import { SpatialWorldPanel } from "@/components/SpatialWorldPanel";

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
    </main>
  );
}
