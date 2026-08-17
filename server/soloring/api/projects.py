"""Project HTTP routes (plan §45)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from soloring.api.deps import get_session
from soloring.api.schemas.projects import ProjectCreate, ProjectPatch, ProjectRead
from soloring.domain import projects

router = APIRouter(prefix="/projects", tags=["projects"])


@router.post("", response_model=ProjectRead, status_code=status.HTTP_201_CREATED)
async def create_project(
    payload: ProjectCreate, session: AsyncSession = Depends(get_session)
) -> ProjectRead:
    return await projects.create_project(session, payload)


@router.get("", response_model=list[ProjectRead])
async def list_projects(
    session: AsyncSession = Depends(get_session),
) -> list[ProjectRead]:
    return await projects.list_projects(session)


@router.get("/{project_id}", response_model=ProjectRead)
async def get_project(
    project_id: str, session: AsyncSession = Depends(get_session)
) -> ProjectRead:
    return await projects.get_project(session, project_id)


@router.patch("/{project_id}", response_model=ProjectRead)
async def patch_project(
    project_id: str,
    payload: ProjectPatch,
    session: AsyncSession = Depends(get_session),
) -> ProjectRead:
    return await projects.patch_project(session, project_id, payload)


@router.delete("/{project_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_project(
    project_id: str, session: AsyncSession = Depends(get_session)
) -> None:
    await projects.delete_project(session, project_id)
