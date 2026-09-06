// M11 Production Library surface (frozen R3 §15): the smallest filmmaker-
// facing page that proves the reusable-production authority.

import Link from "next/link";

import ProductionLibrary from "@/components/ProductionLibrary";
import { serverGetProject } from "@/lib/api.server";

export const dynamic = "force-dynamic";

export default async function ProductionLibraryPage({
  params,
}: {
  params: { id: string };
}) {
  const project = await serverGetProject(params.id);
  return (
    <main>
      <p>
        <Link href={`/projects/${project.id}`}>← {project.name}</Link>
      </p>
      <ProductionLibrary projectId={project.id} />
    </main>
  );
}
