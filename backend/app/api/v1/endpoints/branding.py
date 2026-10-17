"""A project's branding: how its mail looks to a guest.

Sits beside the channel endpoints rather than inside them. Connecting a number and describing the
business are different acts with different consequences: a channel is a technical claim on an
address, and branding is a statement about who the sender is. Splitting them means a tenant can
change how they look without touching credentials, and can connect a channel before they have
decided on a brand - which is the common case, since the address has to exist first.

Absence is a legitimate state, not an error. A project with no branding still sends and still
receives replies; they are simply unstyled. That is why `GET` answers with an empty object rather
than 404, and why `PUT` is an upsert rather than a create.
"""

from __future__ import annotations

import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Response, status
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db, require_permission
from app.core.permissions import Permission
from app.models.project import Project
from app.models.project_branding import SOCIAL_PLATFORMS, ProjectBranding

router = APIRouter(prefix="/organizations/{org_id}", tags=["Branding"])


class SocialLink(BaseModel):
    platform: str
    url: str


class BrandingUpdate(BaseModel):
    """A whole-row replacement.

    PUT rather than PATCH on purpose. This is a small object edited in one form, and a partial update
    cannot express "the guest removed the phone number" - omitting it would be indistinguishable from
    forgetting it, so the value would stick forever with no way to clear it.
    """

    business_name: str = Field(min_length=1, max_length=160)
    tagline: str | None = Field(default=None, max_length=160)
    logo_url: str | None = Field(default=None, max_length=500)
    accent_colour: str | None = Field(default=None, max_length=7)
    postal_address: str | None = None
    phone: str | None = Field(default=None, max_length=40)
    contact_email: str | None = Field(default=None, max_length=500)
    website: str | None = Field(default=None, max_length=500)
    social_links: dict[str, str] = Field(default_factory=dict)
    footer_note: str | None = None

    @field_validator("social_links")
    @classmethod
    def _known_platforms_only(cls, value: dict[str, str]) -> dict[str, str]:
        """Unknown platforms are refused rather than dropped.

        The renderer has a closed label set, so an unrecognised key would be silently discarded - a
        tenant who typed "Facebok" would save successfully and see nothing appear, with no way to
        find out why.
        """
        unknown = set(value) - set(SOCIAL_PLATFORMS)
        if unknown:
            raise ValueError(
                f"unknown social platform(s): {', '.join(sorted(unknown))}. "
                f"Allowed: {', '.join(SOCIAL_PLATFORMS)}"
            )
        return value

    @field_validator("website", "logo_url", "contact_email")
    @classmethod
    def _http_only(cls, value: str | None) -> str | None:
        """Reject anything that is not http(s).

        These are interpolated into ``href``/``src`` attributes in the rendered mail. Escaping stops
        them breaking out of the attribute; requiring a scheme stops a ``javascript:`` URL from
        being one click away in a guest's mail client.
        """
        if value is None:
            return None
        candidate = value.strip()
        if not candidate:
            return None
        if not candidate.lower().startswith(("http://", "https://")):
            raise ValueError("must be an http:// or https:// URL")
        return candidate


class BrandingRead(BaseModel):
    """What `GET` returns. An unbranded project gets empty strings, not a 404."""

    business_name: str | None = None
    tagline: str | None = None
    logo_url: str | None = None
    accent_colour: str | None = None
    postal_address: str | None = None
    phone: str | None = None
    contact_email: str | None = None
    website: str | None = None
    social_links: dict[str, str] = Field(default_factory=dict)
    footer_note: str | None = None


def _to_read(row: ProjectBranding | None) -> BrandingRead:
    if row is None:
        return BrandingRead()
    return BrandingRead(
        business_name=row.business_name,
        tagline=row.tagline,
        logo_url=row.logo_url,
        accent_colour=row.accent_colour,
        postal_address=row.postal_address,
        phone=row.phone,
        contact_email=row.contact_email,
        website=row.website,
        social_links=row.social_links or {},
        footer_note=row.footer_note,
    )


async def _require_project(db: AsyncSession, org_id: uuid.UUID, project_id: uuid.UUID) -> Project:
    """The project, proven to belong to this organisation.

    Checked here rather than trusted from the path: `org_id` and `project_id` both arrive from the
    caller, and without this a valid project id under another organisation would be readable and
    writable by anyone who could guess it.
    """
    project = (
        await db.execute(
            select(Project).where(
                Project.id == project_id, Project.organization_id == org_id
            )
        )
    ).scalar_one_or_none()
    if project is None:
        # 404, not 403: saying "forbidden" confirms the project exists, which is itself a leak of
        # another tenant's ids.
        from fastapi import HTTPException

        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
    return project


@router.get(
    "/projects/{project_id}/branding",
    summary="A project's branding",
)
async def get_branding(
    org_id: uuid.UUID,
    project_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[Any, Depends(require_permission(Permission.CHANNEL_VIEW))],
) -> BrandingRead:
    await _require_project(db, org_id, project_id)
    row = (
        await db.execute(
            select(ProjectBranding).where(ProjectBranding.project_id == project_id)
        )
    ).scalar_one_or_none()
    return _to_read(row)


@router.put(
    "/projects/{project_id}/branding",
    summary="Set a project's branding",
)
async def put_branding(
    org_id: uuid.UUID,
    project_id: uuid.UUID,
    payload: BrandingUpdate,
    db: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[Any, Depends(require_permission(Permission.CHANNEL_MANAGE))],
) -> BrandingRead:
    """Create or replace. There is no partial update, and no delete.

    Absent branding is a state a tenant can return to by clearing the fields, which is why this is a
    replacement rather than a create-or-404. A separate DELETE would be a second spelling of the same
    PUT with every field omitted.
    """
    await _require_project(db, org_id, project_id)

    row = (
        await db.execute(
            select(ProjectBranding).where(ProjectBranding.project_id == project_id)
        )
    ).scalar_one_or_none()

    values = payload.model_dump()
    if row is None:
        row = ProjectBranding(project_id=project_id, **values)
        db.add(row)
    else:
        for key, value in values.items():
            setattr(row, key, value)

    try:
        await db.commit()
    except SQLAlchemyError:
        # Almost certainly the unique index, from two concurrent first writes. The loser retries and
        # gets the winner's row, which is the outcome they wanted anyway.
        await db.rollback()
        raise
    await db.refresh(row)
    return _to_read(row)


@router.delete(
    "/projects/{project_id}/branding",
    summary="Remove a project's branding",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_branding(
    org_id: uuid.UUID,
    project_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[Any, Depends(require_permission(Permission.CHANNEL_MANAGE))],
) -> Response:
    """Back to unbranded mail.

    Idempotent, so a tenant who clicks twice does not get a confusing error for having succeeded
    once already.
    """
    await _require_project(db, org_id, project_id)
    row = (
        await db.execute(
            select(ProjectBranding).where(ProjectBranding.project_id == project_id)
        )
    ).scalar_one_or_none()
    if row is not None:
        await db.delete(row)
        await db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


__all__ = ["router"]