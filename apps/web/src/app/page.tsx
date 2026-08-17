// Projects page (M2B): server-rendered authoritative list + client actions.

import Link from "next/link";

import { ProjectCreateForm, ProjectDeleteButton } from "@/components/ProjectActions";
import { asApiError, type ApiError } from "@/lib/api.shared";
import { serverListProjects } from "@/lib/api.server";
import type { Project } from "@/lib/types";

export const dynamic = "force-dynamic";

export default async function ProjectsPage() {
  let projects: Project[] = [];
  let loadError: ApiError | null = null;
  try {
    projects = await serverListProjects();
  } catch (err) {
    loadError = asApiError(err);
  }

  return (
    <main>
      <h1>SoloRing</h1>
      <h2>Projects</h2>
      {loadError ? (
        <div className="empty">
          {loadError.code} — {loadError.message}
        </div>
      ) : projects.length === 0 ? (
        <div className="empty">No projects yet.</div>
      ) : (
        projects.map((p) => (
          <div className="card row" key={p.id}>
            <div>
              <Link href={`/projects/${p.id}`}>
                <strong>{p.name}</strong>
              </Link>
              {p.description ? <div className="meta">{p.description}</div> : null}
              <div className="meta">created {p.created_at}</div>
            </div>
            <ProjectDeleteButton project={p} />
          </div>
        ))
      )}
      <h2>New project</h2>
      <ProjectCreateForm />
    </main>
  );
}
