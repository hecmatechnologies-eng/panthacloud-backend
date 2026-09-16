"""Per-organization model selection (FR-072, FR-075).

The model an organization's assistants run on is an economic setting: it decides what every
conversation costs and how well it answers. Two consequences shape this module:

- **Reading is open to any member** (`ORG_VIEW`) — knowing which model answers your customers is
  not privileged.
- **Writing is not** (`ORG_UPDATE`, held by OWNER and ADMIN). A member may run an integration, but
  changing the model changes the bill for everyone in the organization.
"""

import logging
import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, require_permission
from app.core.config import settings
from app.core.database import get_db
from app.core.permissions import Permission
from app.models.membership import Membership
from app.models.organization import Organization
from app.models.organization_model_settings import OrganizationModelSettings
from app.models.user import User
from app.schemas.model_settings import OrgModelSettingsRead, OrgModelSettingsUpdate
from app.services.audit import record_audit
from app.services.model_settings import chosen_model_id

logger = logging.getLogger("fussion.model_settings")

router = APIRouter(
    prefix="/organizations/{org_id}/model-settings",
    tags=["Model Settings"],
)

_Tenant = Annotated[
    tuple[Organization, Membership],
    Depends(require_permission(Permission.ORG_VIEW)),
]
_TenantWrite = Annotated[
    tuple[Organization, Membership],
    Depends(require_permission(Permission.ORG_UPDATE)),
]


def _read(chosen: str | None) -> OrgModelSettingsRead:
    return OrgModelSettingsRead(
        model_id=chosen or settings.MODEL_ID,
        is_override=chosen is not None,
        default_model_id=settings.MODEL_ID,
        allowed_model_ids=list(settings.MODEL_ALLOWED_IDS),
    )


@router.get("", response_model=OrgModelSettingsRead, summary="The model this organization runs on")
async def get_model_settings(
    org_id: uuid.UUID,
    tenant: _Tenant,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> OrgModelSettingsRead:
    del org_id
    organization, _ = tenant
    return _read(await chosen_model_id(db, organization.id))


@router.put(
    "",
    response_model=OrgModelSettingsRead,
    summary="Choose the model this organization runs on, or clear the choice",
)
async def put_model_settings(
    org_id: uuid.UUID,
    payload: OrgModelSettingsUpdate,
    tenant: _TenantWrite,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> OrgModelSettingsRead:
    """Set the model, or return to the deployment default with ``model_id = null``.

    The allow-list is checked here as well as in the gateway. Here it is a *write* refusal with the
    permitted values in the message — the gateway's check is the one no caller can bypass, but a
    caller who mistypes a model deserves to be told at the point of the mistake, not on the next
    visitor's question.
    """
    del org_id
    organization, _ = tenant

    chosen = (payload.model_id or "").strip() or None
    if chosen is not None and chosen not in settings.MODEL_ALLOWED_IDS:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=(
                f"{chosen!r} is not a model this deployment allows. Allowed: "
                f"{', '.join(settings.MODEL_ALLOWED_IDS)}."
            ),
        )

    existing = (
        await db.execute(
            select(OrganizationModelSettings).where(
                OrganizationModelSettings.organization_id == organization.id
            )
        )
    ).scalar_one_or_none()

    if chosen is None:
        if existing is not None:
            await db.delete(existing)
    elif existing is not None:
        existing.model_id = chosen
    else:
        db.add(
            OrganizationModelSettings(organization_id=organization.id, model_id=chosen)
        )

    # The change and its record commit together: an audited configuration change that could be
    # recorded without happening (or happen without being recorded) is not audited at all.
    # `project_id` is None because this is an organization-level decision with no project.
    await record_audit(
        db,
        organization.id,
        None,
        user.id,
        "organization.model.changed",
        organization.id,
        {"model_id": chosen or settings.MODEL_ID, "is_override": chosen is not None},
        resource_type="organization",
    )

    logger.info(
        "Organization %s set its model to %s (by user %s)",
        organization.id,
        chosen or settings.MODEL_ID,
        user.id,
    )

    return _read(chosen)
