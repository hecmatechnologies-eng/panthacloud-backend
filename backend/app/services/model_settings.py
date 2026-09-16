"""Per-organization model selection (FR-072, FR-075).

The deployment names a default model; an organization may choose another from the same allow-list.
Resolution is one function so the runtime and the API cannot disagree about which model is in force.
"""

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.organization_model_settings import OrganizationModelSettings


async def chosen_model_id(db: AsyncSession, organization_id: uuid.UUID) -> str | None:
    """The model this organization chose, or ``None`` when it has not chosen one."""
    return (
        await db.execute(
            select(OrganizationModelSettings.model_id).where(
                OrganizationModelSettings.organization_id == organization_id
            )
        )
    ).scalar_one_or_none()


async def effective_model_id(db: AsyncSession, organization_id: uuid.UUID) -> str:
    """The model this organization's assistants run on.

    There is no fallback beyond the deployment default, deliberately. If a stored choice stops being
    allowed — because the deployment narrowed ``MODEL_ALLOWED_IDS`` — the gateway refuses the call
    rather than answering on some other model. A silent fallback would make both the cost and the
    behaviour a lie, and neither is visible from the outside.
    """
    return await chosen_model_id(db, organization_id) or settings.MODEL_ID
