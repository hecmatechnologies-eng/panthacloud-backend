import uuid
from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import (
    get_current_project,
    get_current_user,
    get_or_create_assistant,
    require_permission,
)
from app.core.database import get_db
from app.core.permissions import Permission
from app.models.assistant import Assistant
from app.models.membership import Membership
from app.models.organization import Organization
from app.models.project import Project
from app.models.user import User
from app.schemas.assistant import AssistantPreview, AssistantRead, AssistantUpdate
from app.services.assistant.configuration import (
    build_assistant_preview_payload,
    reset_assistant_configuration,
    update_assistant_configuration,
)

router = APIRouter(
    prefix="/organizations/{org_id}/projects/{project_id}/assistant",
    tags=["Assistant"],
)


@router.get(
    "",
    response_model=AssistantRead,
    summary="Get project assistant configuration (auto-initializes if missing)",
)
async def get_assistant(
    org_id: uuid.UUID,
    project_id: uuid.UUID,
    tenant: Annotated[
        tuple[Organization, Membership],
        Depends(require_permission(Permission.ASSISTANT_VIEW)),
    ],
    assistant: Annotated[Assistant, Depends(get_or_create_assistant)],
) -> AssistantRead:
    """
    Retrieve the assistant configuration for the specified project.
    If no configuration exists, it will be automatically initialized with defaults.
    """
    return AssistantRead.model_validate(assistant)


@router.put(
    "",
    response_model=AssistantRead,
    summary="Update assistant configuration",
)
async def put_assistant(
    org_id: uuid.UUID,
    project_id: uuid.UUID,
    update_data: AssistantUpdate,
    tenant: Annotated[
        tuple[Organization, Membership],
        Depends(require_permission(Permission.ASSISTANT_UPDATE)),
    ],
    assistant: Annotated[Assistant, Depends(get_or_create_assistant)],
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> AssistantRead:
    """
    Update the assistant configuration for the project.
    Validates branding colors, avatar URL, and text length limits.
    """
    updated = await update_assistant_configuration(
        assistant=assistant,
        update_data=update_data,
        org_id=org_id,
        project_id=project_id,
        user_id=current_user.id,
        db=db,
    )
    return AssistantRead.model_validate(updated)


@router.patch(
    "",
    response_model=AssistantRead,
    summary="Partially update assistant configuration",
)
async def patch_assistant(
    org_id: uuid.UUID,
    project_id: uuid.UUID,
    update_data: AssistantUpdate,
    tenant: Annotated[
        tuple[Organization, Membership],
        Depends(require_permission(Permission.ASSISTANT_UPDATE)),
    ],
    assistant: Annotated[Assistant, Depends(get_or_create_assistant)],
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> AssistantRead:
    """
    Partially update the assistant configuration for the project.
    """
    updated = await update_assistant_configuration(
        assistant=assistant,
        update_data=update_data,
        org_id=org_id,
        project_id=project_id,
        user_id=current_user.id,
        db=db,
    )
    return AssistantRead.model_validate(updated)


@router.delete(
    "",
    response_model=AssistantRead,
    summary="Reset assistant configuration to defaults",
)
async def delete_or_reset_assistant(
    org_id: uuid.UUID,
    project_id: uuid.UUID,
    tenant: Annotated[
        tuple[Organization, Membership],
        Depends(require_permission(Permission.ASSISTANT_DELETE)),
    ],
    project: Annotated[Project, Depends(get_current_project)],
    assistant: Annotated[Assistant, Depends(get_or_create_assistant)],
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> AssistantRead:
    """
    Reset assistant configuration to canonical Fussion defaults.
    """
    reset_assistant = await reset_assistant_configuration(
        assistant=assistant,
        project_name=project.name,
        org_id=org_id,
        project_id=project_id,
        user_id=current_user.id,
        db=db,
    )
    return AssistantRead.model_validate(reset_assistant)


@router.post(
    "/reset",
    response_model=AssistantRead,
    summary="Explicitly reset assistant configuration to defaults",
)
async def post_reset_assistant(
    org_id: uuid.UUID,
    project_id: uuid.UUID,
    tenant: Annotated[
        tuple[Organization, Membership],
        Depends(require_permission(Permission.ASSISTANT_DELETE)),
    ],
    project: Annotated[Project, Depends(get_current_project)],
    assistant: Annotated[Assistant, Depends(get_or_create_assistant)],
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> AssistantRead:
    """
    Reset assistant configuration to canonical Fussion defaults.
    """
    reset_assistant = await reset_assistant_configuration(
        assistant=assistant,
        project_name=project.name,
        org_id=org_id,
        project_id=project_id,
        user_id=current_user.id,
        db=db,
    )
    return AssistantRead.model_validate(reset_assistant)


@router.get(
    "/preview",
    response_model=AssistantPreview,
    summary="Get preview widget configuration payload",
)
async def get_assistant_preview(
    org_id: uuid.UUID,
    project_id: uuid.UUID,
    tenant: Annotated[
        tuple[Organization, Membership],
        Depends(require_permission(Permission.ASSISTANT_VIEW)),
    ],
    project: Annotated[Project, Depends(get_current_project)],
    assistant: Annotated[Assistant, Depends(get_or_create_assistant)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> AssistantPreview:
    """
    Build preview widget configuration communicating assistant styling,
    grounding availability from Knowledge Base, and mock preview responses.
    Zero external AI/LLM calls.
    """
    return await build_assistant_preview_payload(
        assistant=assistant,
        project=project,
        db=db,
    )
