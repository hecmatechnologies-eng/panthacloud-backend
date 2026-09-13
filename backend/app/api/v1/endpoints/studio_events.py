import asyncio
import json
import uuid
from collections.abc import AsyncGenerator
from typing import Annotated

from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse
from sqlalchemy import select

from app.api.deps import authorize_project_stream
from app.core.database import get_session_factory
from app.models.audit_event import AuditEvent

router = APIRouter(prefix="/organizations/{org_id}/projects", tags=["Studio Events"])


def _frame(event: AuditEvent) -> str:
    payload = {
        "id": str(event.id),
        "event_type": event.event_type,
        "payload": event.payload,
        "created_at": event.created_at.isoformat(),
    }
    return f"id: {event.id}\nevent: studio.activity\ndata: {json.dumps(payload)}\n\n"


@router.get("/{project_id}/events/stream", summary="Stream project studio activity")
async def stream_project_events(
    request: Request,
    authorized_project_id: Annotated[uuid.UUID, Depends(authorize_project_stream)],
) -> StreamingResponse:
    """Stream a project's audit events.

    Authorization happens in `authorize_project_stream`, which closes its session before this
    returns. The generator then opens a short-lived session per poll and closes it before yielding,
    so an idle connection holds no pooled connection at all (CLAUDE.md §3.6).
    """

    async def event_generator() -> AsyncGenerator[str]:
        session_factory = get_session_factory()

        async with session_factory() as db:
            initial_stmt = (
                select(AuditEvent)
                .where(AuditEvent.project_id == authorized_project_id)
                .order_by(AuditEvent.created_at.desc())
                .limit(25)
            )
            initial_events = list(reversed((await db.execute(initial_stmt)).scalars().all()))
            # Serialise inside the session: the frames are plain strings, so nothing is read from a
            # detached instance after the session closes.
            initial_frames = [_frame(event) for event in initial_events]
            last_created_at = initial_events[-1].created_at if initial_events else None

        for frame in initial_frames:
            yield frame

        while not await request.is_disconnected():
            async with session_factory() as db:
                stmt = select(AuditEvent).where(AuditEvent.project_id == authorized_project_id)
                if last_created_at is not None:
                    stmt = stmt.where(AuditEvent.created_at > last_created_at)
                stmt = stmt.order_by(AuditEvent.created_at.asc())
                new_events = (await db.execute(stmt)).scalars().all()
                new_frames = [_frame(event) for event in new_events]
                if new_events:
                    last_created_at = new_events[-1].created_at

            for frame in new_frames:
                yield frame
            yield ": keepalive\n\n"
            await asyncio.sleep(1)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive", "X-Accel-Buffering": "no"},
    )
