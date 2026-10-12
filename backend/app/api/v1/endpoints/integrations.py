from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_integration, get_current_project, require_permission
from app.api.v1.endpoints._location import CREATED_RESPONSE, created
from app.core.database import get_db
from app.core.permissions import Permission
from app.core.secrets import secret_store
from app.models.integration import Integration, IntegrationStatus
from app.models.membership import Membership
from app.models.organization import Organization
from app.models.project import Project
from app.schemas.integration import (
    IntegrationCreate,
    IntegrationRead,
    IntegrationUpdate,
)

router = APIRouter(
    prefix="/organizations/{org_id}/projects/{project_id}/integrations",
    tags=["Integrations"],
)

# Explicit valid user-triggered lifecycle transitions
VALID_TRANSITIONS: dict[IntegrationStatus, set[IntegrationStatus]] = {
    IntegrationStatus.PENDING: {
        IntegrationStatus.PENDING,
        IntegrationStatus.ACTIVE,
        IntegrationStatus.DISABLED,
    },
    IntegrationStatus.ACTIVE: {
        IntegrationStatus.ACTIVE,
        IntegrationStatus.DISCONNECTED,
        IntegrationStatus.DISABLED,
    },
    IntegrationStatus.DISCONNECTED: {
        IntegrationStatus.DISCONNECTED,
        IntegrationStatus.ACTIVE,
        IntegrationStatus.DISABLED,
    },
    IntegrationStatus.ERROR: {
        IntegrationStatus.ERROR,
        IntegrationStatus.PENDING,
        IntegrationStatus.ACTIVE,
        IntegrationStatus.DISABLED,
    },
    IntegrationStatus.DISABLED: {
        IntegrationStatus.DISABLED,
        IntegrationStatus.ACTIVE,
        IntegrationStatus.PENDING,
    },
}


def to_integration_read(integration: Integration) -> IntegrationRead:
    return IntegrationRead(
        id=integration.id,
        project_id=integration.project_id,
        provider=integration.provider,
        name=integration.name,
        status=integration.status,
        configuration=integration.configuration,
        has_credentials=bool(integration.encrypted_secrets),
        created_at=integration.created_at,
        updated_at=integration.updated_at,
    )


@router.post(
    "",
    response_model=IntegrationRead,
    status_code=status.HTTP_201_CREATED,
    responses=CREATED_RESPONSE,
    summary="Create a new integration for the project",
)
async def create_integration(
    payload: IntegrationCreate,
    project: Annotated[Project, Depends(get_current_project)],
    tenant: Annotated[
        tuple[Organization, Membership],
        Depends(require_permission(Permission.INTEGRATION_CREATE)),
    ],
    db: Annotated[AsyncSession, Depends(get_db)],
    response: Response,
) -> IntegrationRead:
    # Invariant: Integration name must be unique inside the project
    stmt = select(Integration).where(
        Integration.project_id == project.id,
        Integration.name == payload.name,
    )
    result = await db.execute(stmt)
    if result.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"An integration named '{payload.name}' already exists in this project.",
        )

    # Separate configuration from encrypted credentials
    encrypted_blob: str | None = None
    initial_status = payload.status
    if payload.secrets:
        encrypted_blob = secret_store.encrypt(payload.secrets)
        if initial_status == IntegrationStatus.PENDING:
            initial_status = IntegrationStatus.ACTIVE

    integration = Integration(
        project_id=project.id,
        provider=payload.provider,
        name=payload.name,
        status=initial_status,
        configuration=payload.configuration,
        encrypted_secrets=encrypted_blob,
    )
    db.add(integration)
    await db.commit()
    await db.refresh(integration)

    created(
        response,
        "organizations",
        str(project.organization_id),
        "projects",
        str(project.id),
        "integrations",
        str(integration.id),
    )
    return to_integration_read(integration)


@router.get(
    "",
    response_model=list[IntegrationRead],
    summary="List all integrations for the project",
)
async def list_integrations(
    project: Annotated[Project, Depends(get_current_project)],
    tenant: Annotated[
        tuple[Organization, Membership],
        Depends(require_permission(Permission.INTEGRATION_VIEW)),
    ],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> list[IntegrationRead]:
    stmt = (
        select(Integration)
        .where(Integration.project_id == project.id)
        .order_by(Integration.created_at.desc())
    )
    result = await db.execute(stmt)
    integrations = result.scalars().all()
    return [to_integration_read(item) for item in integrations]


@router.get(
    "/{integration_id}",
    response_model=IntegrationRead,
    summary="Retrieve integration details within project scope",
)
async def get_integration(
    integration: Annotated[Integration, Depends(get_current_integration)],
) -> IntegrationRead:
    return to_integration_read(integration)


@router.patch(
    "/{integration_id}",
    response_model=IntegrationRead,
    summary="Update integration configuration or status",
)
async def update_integration(
    payload: IntegrationUpdate,
    integration: Annotated[Integration, Depends(get_current_integration)],
    tenant: Annotated[
        tuple[Organization, Membership],
        Depends(require_permission(Permission.INTEGRATION_MODIFY)),
    ],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> IntegrationRead:
    if payload.name is not None and payload.name != integration.name:
        # Check name collision in same project
        stmt = select(Integration).where(
            Integration.project_id == integration.project_id,
            Integration.name == payload.name,
        )
        result = await db.execute(stmt)
        if result.scalar_one_or_none():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"An integration named '{payload.name}' already exists in this project.",
            )
        integration.name = payload.name

    if payload.configuration is not None:
        updated_config = dict(integration.configuration)
        updated_config.update(payload.configuration)
        integration.configuration = updated_config

    if payload.secrets is not None:
        integration.encrypted_secrets = secret_store.encrypt(payload.secrets)

    if payload.status is not None:
        allowed = VALID_TRANSITIONS.get(integration.status, set())
        if payload.status not in allowed:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid state transition from '{integration.status.value}' to '{payload.status.value}'.",
            )
        integration.status = payload.status

    await db.commit()
    await db.refresh(integration)
    return to_integration_read(integration)


@router.delete(
    "/{integration_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete an integration from the project",
)
async def delete_integration(
    integration: Annotated[Integration, Depends(get_current_integration)],
    tenant: Annotated[
        tuple[Organization, Membership],
        Depends(require_permission(Permission.INTEGRATION_DELETE)),
    ],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> None:
    await db.delete(integration)
    await db.commit()
