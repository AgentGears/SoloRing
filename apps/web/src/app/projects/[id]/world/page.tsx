// M12 World/Set workspace page (frozen R3 §15).

import Link from "next/link";

import WorldSetWorkspace from "@/components/WorldSetWorkspace";
import { serverGetProject } from "@/lib/api.server";

export const dynamic = "force-dynamic";

export default async function WorldSetPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  const project = await serverGetProject(id);
  return (
    <main>
      <p>
        <Link href={`/projects/${project.id}`}>← {project.name}</Link>
      </p>
      <WorldSetWorkspace projectId={project.id} />
    </main>
  );
}
