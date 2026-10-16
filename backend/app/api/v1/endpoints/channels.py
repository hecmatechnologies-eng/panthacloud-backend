"""Connected channel accounts, and a project's choice of one (ADR-004).

Two levels, matching the two things the Settings page has to show:

- **Organisation** - the accounts this tenant has *connected*. Many per organisation; this is where
  a group adds its second property's number.
- **Project** - which of those the project's assistant *answers on*. Exactly one per channel.

The split exists because the alternative is not expressible. With one column on ``Project`` a
tenant could connect only as many numbers as it had projects, and "connect it now, decide later"
would be impossible.

**Routing refuses a connected-but-unselected number.** ``resolve_channel_tenant`` joins through
``ProjectChannel``, so the row a tenant just created answers nobody until a project is pointed at
it. The read endpoints therefore report ``selected_by_project_id`` on every account: without it the
Settings page would show "Connected" for a number that is silently answering nobody, which is the
most likely way to lose an afternoon during setup.

**Never returns a token.** ``ChannelAccountRead`` has no field for it; ``has_access_token`` is a
boolean instead. The endpoint is readable by ``channel:view``, which a MEMBER holds.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from fastapi.responses import JSONResponse
from sqlalchemy import select, tuple_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db, require_permission
from app.api.v1.endpoints._pagination import (
    InvalidCursor,
    apply_page,
    cursor_http_error,
    decode_cursor,
    encode_cursor,
    parse_timestamp,
)
from app.channels.base import Channel
from app.core.permissions import Permission
from app.core.secrets import secret_store
from app.models.channel_registration import ChannelRegistration
from app.models.membership import Membership
from app.models.organization import Organization
from app.models.project import Project
from app.models.project_channel import ProjectChannel
from app.schemas.channel import (
    ChannelAccountCreate,
    ChannelAccountRead,
    ChannelAccountUpdate,
    ProjectChannelRead,
    ProjectChannelSet,
)

router = APIRouter(prefix="/organizations/{org_id}", tags=["Channels"])


# ============================================================
# Helpers
# ============================================================


async def _require_project(db: AsyncSession, org_id: uuid.UUID, project_id: uuid.UUID) -> Project:
    project = (
        await db.execute(
            select(Project).where(Project.id == project_id, Project.organization_id == org_id)
        )
    ).scalar_one_or_none()
    if project is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
    return project


def _read(
    row: ChannelRegistration,
    *,
    selected: ProjectChannel | None,
    project_name: str | None,
) -> ChannelAccountRead:
    """Map to the read shape, keeping the token out of it."""
    return ChannelAccountRead(
        id=row.id,
        channel=row.channel,
        external_identifier=row.external_identifier,
        display_name=row.display_name,
        phone_number_id=row.phone_number_id,
        is_active=row.is_active,
        verified_at=row.verified_at,
        has_access_token=bool(row.encrypted_access_token),
        selected_by_project_id=selected.project_id if selected else None,
        selected_by_project_name=project_name,
    )


# ============================================================
# Organisation: connected accounts
# ============================================================


@router.get(
    "/channels",
    response_model=list[ChannelAccountRead],
    summary="List the channel accounts this organization has connected",
)
async def list_channels(
    request: Request,
    response: Response,
    org_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    tenant: Annotated[
        tuple[Organization, Membership],
        Depends(require_permission(Permission.CHANNEL_VIEW)),
    ],
    limit: Annotated[int, Query(ge=1, le=100)] = 25,
    cursor: Annotated[str | None, Query(max_length=512)] = None,
) -> list[ChannelAccountRead]:

    # Keyset on (channel, created_at, id) rather than offset: a tenant retires an account rather
    # than deleting it, so the list only ever grows, and an offset would let a row shift between
    # pages as a new account is connected mid-scroll - serving one twice and skipping another.
    # `id` is the tiebreaker because created_at is not unique.
    after = None
    if cursor:
        try:
            after = decode_cursor(cursor)
        except InvalidCursor:
            raise cursor_http_error() from None

    stmt = select(ChannelRegistration).where(ChannelRegistration.organization_id == org_id)
    if after:
        stmt = stmt.where(
            tuple_(
                ChannelRegistration.channel,
                ChannelRegistration.created_at,
                ChannelRegistration.id,
            )
            # uuid.UUID(...) rather than the raw string from the cursor: the comparison is a
            # row-value compare against a UUID column, and handing it a str makes the predicate
            # compare text to uuid - which does not advance, so the page silently repeats the last
            # row of the previous page.
            > tuple_(after["c"], parse_timestamp(after["t"]), uuid.UUID(after["i"]))
        )
    stmt = stmt.order_by(
        ChannelRegistration.channel, ChannelRegistration.created_at, ChannelRegistration.id
    ).limit(limit + 1)

    rows = list((await db.execute(stmt)).scalars().all())

    # One query for the selections rather than N, so the page does not scale its queries with the
    # number of numbers a tenant has connected.
    selections = {
        s.channel_registration_id: s
        for s in (
            await db.execute(
                select(ProjectChannel).where(
                    ProjectChannel.project_id.in_(
                        select(Project.id).where(Project.organization_id == org_id)
                    )
                )
            )
        ).scalars().all()
    }
    projects = {
        p.id: p.name
        for p in (await db.execute(select(Project).where(Project.organization_id == org_id))).scalars().all()
    }

    # apply_page does the limit+1 trim and the Link header together; hand-rolling that is how the
    # two drift apart and a page silently serves the wrong number of rows.
    link = apply_page(
        rows,
        limit,
        last_cursor=(
            encode_cursor(
                {
                    "c": rows[limit - 1].channel.value,
                    "t": rows[limit - 1].created_at,
                    "i": str(rows[limit - 1].id),
                }
            )
            if len(rows) > limit
            else ""
        ),
        path=request.url.path,
        params=dict(request.query_params),
    )
    if link:
        response.headers["Link"] = link
    page = rows[:limit]

    return [
        _read(
            row,
            selected=selections.get(row.id),
            project_name=(
                projects.get(selections[row.id].project_id) if row.id in selections else None
            ),
        )
        for row in page
    ]


@router.post(
    "/channels",
    response_model=ChannelAccountRead,
    status_code=status.HTTP_201_CREATED,
    summary="Connect a channel account",
    # Declared so a created resource is addressable; the 201 points at it. Without this the
    # Location header would name a path that 404s, which is worse than omitting it.
    responses={201: {"headers": {"Location": {"schema": {"type": "string"}}}}},
)
async def connect_channel(
    request: Request,
    org_id: uuid.UUID,
    payload: ChannelAccountCreate,
    db: Annotated[AsyncSession, Depends(get_db)],
    tenant: Annotated[
        tuple[Organization, Membership],
        Depends(require_permission(Permission.CHANNEL_MANAGE)),
    ],
) -> ChannelAccountRead:
    _organization, membership = tenant
    """Connect a number. It answers nobody until a project selects it."""

    row = ChannelRegistration(
        organization_id=org_id,
        # Null: the account belongs to the organisation. Which project uses it is ProjectChannel.
        project_id=None,
        channel=payload.channel,
        external_identifier=payload.external_identifier,
        display_name=payload.display_name,
        phone_number_id=payload.phone_number_id,
        is_active=True,
        encrypted_access_token=(
            secret_store.encrypt_text(payload.access_token) if payload.access_token else None
        ),
        created_by_user_id=membership.user_id,
    )
    db.add(row)
    try:
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        # The address is unique organisation-wide, so this is either "you already connected this
        # number" or "another tenant holds it". Both are a 409, and both deliberately read the
        # same: saying which would leak whether a number is registered somewhere else.
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="That address is already connected.",
        ) from exc
    await db.refresh(row)

    # RFC 9110 15.3.2: a 201 on a resource creation carries the new resource's URI. This one is a
    # representation of the created resource, so the usual "not addressable" exception does not
    # apply.
    return JSONResponse(
        content=_read(row, selected=None, project_name=None).model_dump(mode="json"),
        status_code=status.HTTP_201_CREATED,
        headers={"Location": f"/api/v1/organizations/{org_id}/channels/{row.id}"},
    )


@router.get(
    "/channels/{registration_id}",
    response_model=ChannelAccountRead,
    summary="Read one connected channel account",
)
async def get_channel(
    org_id: uuid.UUID,
    registration_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    tenant: Annotated[
        tuple[Organization, Membership],
        Depends(require_permission(Permission.CHANNEL_VIEW)),
    ],
) -> ChannelAccountRead:
    """One account by id.

    Exists so the 201's ``Location`` resolves. A header naming a path that 404s is worse than no
    header, because a client that follows it reports a failure for a request that succeeded.
    """
    row = (
        await db.execute(
            select(ChannelRegistration).where(
                ChannelRegistration.id == registration_id,
                ChannelRegistration.organization_id == org_id,
            )
        )
    ).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Channel not found")

    selected = (
        await db.execute(
            select(ProjectChannel).where(ProjectChannel.channel_registration_id == row.id)
        )
    ).scalar_one_or_none()
    project_name = None
    if selected is not None:
        project_name = (
            await db.execute(select(Project.name).where(Project.id == selected.project_id))
        ).scalar_one_or_none()

    return _read(row, selected=selected, project_name=project_name)


@router.patch(
    "/channels/{registration_id}",
    response_model=ChannelAccountRead,
    summary="Retire or restore a channel account",
)
async def update_channel(
    org_id: uuid.UUID,
    registration_id: uuid.UUID,
    payload: ChannelAccountUpdate,
    db: Annotated[AsyncSession, Depends(get_db)],
    tenant: Annotated[
        tuple[Organization, Membership],
        Depends(require_permission(Permission.CHANNEL_MANAGE)),
    ],
) -> ChannelAccountRead:
    _organization, _membership = tenant  # tenancy already enforced by the dependency

    row = (
        await db.execute(
            select(ChannelRegistration).where(
                ChannelRegistration.id == registration_id,
                ChannelRegistration.organization_id == org_id,
            )
        )
    ).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Channel not found")

    row.is_active = payload.is_active
    await db.commit()
    await db.refresh(row)

    selected = (
        await db.execute(
            select(ProjectChannel).where(
                ProjectChannel.channel_registration_id == row.id
            )
        )
    ).scalar_one_or_none()

    return _read(row, selected=selected, project_name=None)


# ============================================================
# Project: which account the assistant uses
# ============================================================


@router.get(
    "/projects/{project_id}/channels",
    response_model=list[ProjectChannelRead],
    summary="List the accounts this project answers on",
)
async def list_project_channels(
    org_id: uuid.UUID,
    project_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    tenant: Annotated[
        tuple[Organization, Membership],
        Depends(require_permission(Permission.CHANNEL_VIEW)),
    ],
    limit: Annotated[int, Query(ge=1, le=100)] = 25,
    cursor: Annotated[str | None, Query(max_length=512)] = None,
) -> list[ProjectChannelRead]:
    await _require_project(db, org_id, project_id)

    # `channel` is unique per project (uq_project_channel_project), so the page is stable without
    # a tiebreaker; the cursor still exists so this stays a normal collection contract rather than
    # an endpoint that silently breaks the first time a project gets two accounts on a channel.
    after = None
    if cursor:
        try:
            after = decode_cursor(cursor)
        except InvalidCursor:
            raise cursor_http_error() from None

    stmt = (
        select(ProjectChannel, ChannelRegistration)
        .join(
            ChannelRegistration,
            ChannelRegistration.id == ProjectChannel.channel_registration_id,
        )
        .where(ProjectChannel.project_id == project_id)
    )
    if after:
        stmt = stmt.where(ProjectChannel.channel > Channel(after["c"]))
    stmt = stmt.order_by(ProjectChannel.channel).limit(limit + 1)

    rows = list((await db.execute(stmt)).all())[:limit]

    return [
        ProjectChannelRead(
            channel=pc.channel,
            channel_registration_id=reg.id,
            external_identifier=reg.external_identifier,
            display_name=reg.display_name,
            is_active=reg.is_active,
            has_access_token=bool(reg.encrypted_access_token),
            selected_at=pc.selected_at,
        )
        for pc, reg in rows
    ]


@router.put(
    "/projects/{project_id}/channels/{channel}",
    response_model=ProjectChannelRead,
    summary="Point a project at a connected account",
)
async def set_project_channel(
    org_id: uuid.UUID,
    project_id: uuid.UUID,
    channel: Channel,
    payload: ProjectChannelSet,
    db: Annotated[AsyncSession, Depends(get_db)],
    tenant: Annotated[
        tuple[Organization, Membership],
        Depends(require_permission(Permission.PROJECT_CHANNEL_MODIFY)),
    ],
) -> ProjectChannelRead:
    """Choose which connected account this project's assistant answers on.

    A PUT, replacing any previous choice rather than adding a second: two live accounts would leave
    "where do replies go?" unanswerable, which is the rule ``uq_project_channel_project`` also
    enforces in the database. Here it is a friendly error rather than an IntegrityError.
    """
    await _require_project(db, org_id, project_id)

    registration = (
        await db.execute(
            select(ChannelRegistration).where(
                ChannelRegistration.id == payload.channel_registration_id,
                ChannelRegistration.organization_id == org_id,
                ChannelRegistration.channel == channel,
            )
        )
    ).scalar_one_or_none()
    if registration is None:
        # Same 404 whether the id is unknown, belongs to another org, or is the wrong channel - the
        # differences are not this endpoint's to disclose.
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Channel account not found"
        )

    if not registration.is_active:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="That account is retired. Restore it before selecting it.",
        )

    # An account serves at most one project - enforced by ``uq_project_channel_registration``
    # because inbound routing names the number and nothing else. Moving one to this project is a
    # legitimate operation, so the previous holder's row is released here rather than surfacing as
    # an IntegrityError: the caller asked for this project to take it, and the alternative (a 409)
    # would leave them with no way to express "move it" at all.
    previous_holder = (
        await db.execute(
            select(ProjectChannel).where(
                ProjectChannel.channel_registration_id == registration.id,
                ProjectChannel.channel == channel,
            )
        )
    ).scalar_one_or_none()
    if previous_holder is not None and previous_holder.project_id != project_id:
        await db.delete(previous_holder)
        await db.flush()

    existing = (
        await db.execute(
            select(ProjectChannel).where(
                ProjectChannel.project_id == project_id, ProjectChannel.channel == channel
            )
        )
    ).scalar_one_or_none()

    if existing is not None and existing.channel_registration_id == registration.id:
        return ProjectChannelRead(
            channel=channel,
            channel_registration_id=registration.id,
            external_identifier=registration.external_identifier,
            display_name=registration.display_name,
            is_active=registration.is_active,
            has_access_token=bool(registration.encrypted_access_token),
            selected_at=existing.selected_at,
        )

    if existing is not None:
        existing.channel_registration_id = registration.id
        existing.selected_at = datetime.now(UTC)
        await db.commit()
        await db.refresh(existing)
        pc = existing
    else:
        pc = ProjectChannel(
            project_id=project_id,
            channel=channel,
            channel_registration_id=registration.id,
            selected_at=datetime.now(UTC),
        )
        db.add(pc)
        await db.commit()
        await db.refresh(pc)

    return ProjectChannelRead(
        channel=pc.channel,
        channel_registration_id=registration.id,
        external_identifier=registration.external_identifier,
        display_name=registration.display_name,
        is_active=registration.is_active,
        has_access_token=bool(registration.encrypted_access_token),
        selected_at=pc.selected_at,
    )


__all__ = ["router"]