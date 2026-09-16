"""Audit-event recording shared by the website-integration control-plane endpoints.

Other modules still carry their own private copies of this helper; consolidating all of them is
its own change. This exists so no module has to import a private function from another.
"""

import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit_event import AuditEvent

_REDACTED_KEYS = ("token", "github_token", "encrypted_secrets", "secret", "password")


async def record_audit(
    db: AsyncSession,
    org_id: uuid.UUID,
    project_id: uuid.UUID | None,
    user_id: uuid.UUID | None,
    event_type: str,
    resource_id: uuid.UUID,
    payload: dict[str, Any] | None = None,
    resource_type: str = "website_integration",
) -> None:
    """Append an audit event.

    ``project_id`` is ``None`` for an organization-level change — choosing the organization's model,
    for instance — which has no project to attribute it to.
    """
    clean_payload = dict(payload or {})
    for key in _REDACTED_KEYS:
        clean_payload.pop(key, None)

    event = AuditEvent(
        organization_id=org_id,
        project_id=project_id,
        user_id=user_id,
        event_type=event_type,
        resource_type=resource_type,
        resource_id=resource_id,
        payload=clean_payload,
    )
    db.add(event)
    await db.commit()
