import asyncio
import json
from collections.abc import AsyncGenerator
from typing import Annotated

from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_project, require_permission
from app.core.database import get_db
from app.core.permissions import Permission
from app.models.audit_event import AuditEvent
from app.models.membership import Membership
from app.models.organization import Organization
from app.models.project import Project

router = APIRouter(prefix="/organizations/{org_id}/projects", tags=["Studio Events"])


def _serialize_event(event: AuditEvent) -> dict[str, object]:
    return {
        "id": str(event.id),
        "event_type": event.event_type,
        "payload": event.payload,
        "created_at": event.created_at.isoformat(),
    }


@router.get("/{project_id}/events/stream", summary="Stream project studio activity")
async def stream_project_events(
    request: Request,
    project: Annotated[Project, Depends(get_current_project)],
    tenant: Annotated[
        tuple[Organization, Membership], Depends(require_permission(Permission.PROJECT_VIEW))
    ],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> StreamingResponse:
    del tenant

    async def event_generator() -> AsyncGenerator[str]:
        initial_stmt = (
            select(AuditEvent)
            .where(AuditEvent.project_id == project.id)
            .order_by(AuditEvent.created_at.desc())
            .limit(25)
        )
        initial_events = list(reversed((await db.execute(initial_stmt)).scalars().all()))
        last_created_at = None

        for event in initial_events:
            last_created_at = event.created_at
            yield f"id: {event.id}\nevent: studio.activity\ndata: {json.dumps(_serialize_event(event))}\n\n"

        while not await request.is_disconnected():
            stmt = select(AuditEvent).where(AuditEvent.project_id == project.id)
            if last_created_at is not None:
                stmt = stmt.where(AuditEvent.created_at > last_created_at)
            stmt = stmt.order_by(AuditEvent.created_at.asc())
            new_events = (await db.execute(stmt)).scalars().all()

            for event in new_events:
                last_created_at = event.created_at
                yield f"id: {event.id}\nevent: studio.activity\ndata: {json.dumps(_serialize_event(event))}\n\n"

            yield ": keepalive\n\n"
            await asyncio.sleep(1)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive", "X-Accel-Buffering": "no"},
    )
