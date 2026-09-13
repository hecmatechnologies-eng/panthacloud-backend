import uuid
from collections.abc import Callable
from typing import Annotated

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.database import get_db, get_session_factory
from app.core.permissions import Permission, has_permission
from app.core.security import decode_access_token
from app.models.assistant import Assistant, AssistantPosition
from app.models.discovery import DiscoveryRun
from app.models.integration import Integration
from app.models.knowledge import KnowledgeBase, KnowledgeDocument
from app.models.membership import Membership
from app.models.organization import Organization
from app.models.project import Project
from app.models.repository import Repository
from app.models.repository_snapshot import RepositorySnapshot
from app.models.user import User
from app.models.website_integration import WebsiteIntegration
from app.services.knowledge.embeddings import build_default_embedding_provider

bearer_scheme = HTTPBearer(auto_error=False)


async def get_current_user(
    token_auth: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> User:
    """Validate bearer JWT token and return active authenticated user."""
    if not token_auth or not token_auth.credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication credentials were not provided.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    try:
        payload = decode_access_token(token_auth.credentials)
        user_id_str: str | None = payload.get("sub")
        if not user_id_str:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token payload missing subject identifier.",
                headers={"WWW-Authenticate": "Bearer"},
            )
        user_id = uuid.UUID(user_id_str)
    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication token has expired.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    except (jwt.PyJWTError, ValueError):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate authentication credentials.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    stmt = select(User).where(User.id == user_id)
    result = await db.execute(stmt)
    user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Inactive user account.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return user


async def get_current_organization(
    org_id: uuid.UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> tuple[Organization, Membership]:
    """
    Tenant Resolution Dependency:
    Resolves target organization and active membership for the current user.
    Returns 404 on missing organization or membership to prevent cross-tenant enumeration.
    """
    stmt = (
        select(Organization, Membership)
        .join(Membership, Membership.organization_id == Organization.id)
        .where(
            Organization.id == org_id,
            Membership.user_id == current_user.id,
        )
    )
    result = await db.execute(stmt)
    row = result.first()

    if not row:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Organization not found or access denied.",
        )

    org, membership = row
    return org, membership


def require_permission(
    permission: Permission,
) -> Callable[..., tuple[Organization, Membership]]:
    """Factory dependency enforcing explicit RBAC permission in the resolved tenant."""

    async def _dependency(
        tenant: Annotated[tuple[Organization, Membership], Depends(get_current_organization)],
    ) -> tuple[Organization, Membership]:
        _org, membership = tenant
        if not has_permission(membership.role, permission):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Action not permitted. Role '{membership.role.value}' lacks '{permission.value}'.",
            )
        return tenant

    return _dependency


async def get_current_project(
    project_id: uuid.UUID,
    tenant: Annotated[
        tuple[Organization, Membership],
        Depends(require_permission(Permission.PROJECT_VIEW)),
    ],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> Project:
    """
    Project Resolution Dependency:
    Resolves project strictly scoped within the authenticated organization.
    """
    org, _ = tenant
    stmt = select(Project).where(
        Project.id == project_id,
        Project.organization_id == org.id,
    )
    result = await db.execute(stmt)
    project = result.scalar_one_or_none()

    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Project not found in organization.",
        )

    return project


async def authorize_project_stream(
    org_id: uuid.UUID,
    project_id: uuid.UUID,
    token_auth: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)],
) -> uuid.UUID:
    """Authorize a streaming connection, then release the session before the stream begins.

    A server-sent-events connection outlives a request, and FastAPI closes a `yield` dependency
    only after the response completes — so a route that depends on `get_db` holds a pooled
    connection for the connection's life and exhausts the pool (CLAUDE.md §3.6). This resolves the
    user, tenant, permission and project in its own short-lived session and returns only the
    trusted project id; the session is closed when this returns, before any event is streamed.

    It composes the existing resolution functions directly rather than re-implementing the checks,
    so the authorization is identical to a normal request.
    """
    async with get_session_factory()() as db:
        user = await get_current_user(token_auth=token_auth, db=db)
        tenant = await get_current_organization(org_id=org_id, current_user=user, db=db)
        await require_permission(Permission.PROJECT_VIEW)(tenant=tenant)
        project = await get_current_project(project_id=project_id, tenant=tenant, db=db)
        return project.id


async def get_current_integration(
    integration_id: uuid.UUID,
    project: Annotated[Project, Depends(get_current_project)],
    tenant: Annotated[
        tuple[Organization, Membership],
        Depends(require_permission(Permission.INTEGRATION_VIEW)),
    ],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> Integration:
    """
    Integration Resolution Dependency:
    Resolves integration strictly scoped within the authenticated project and organization.
    """
    stmt = select(Integration).where(
        Integration.id == integration_id,
        Integration.project_id == project.id,
    )
    result = await db.execute(stmt)
    integration = result.scalar_one_or_none()

    if not integration:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Integration not found in project.",
        )

    return integration


async def get_current_repository(
    repository_id: uuid.UUID,
    project: Annotated[Project, Depends(get_current_project)],
    tenant: Annotated[
        tuple[Organization, Membership],
        Depends(require_permission(Permission.REPOSITORY_VIEW)),
    ],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> Repository:
    """
    Repository Resolution Dependency:
    Resolves repository strictly scoped within the authenticated project and organization.
    """
    stmt = select(Repository).where(
        Repository.id == repository_id,
        Repository.project_id == project.id,
    )
    result = await db.execute(stmt)
    repo = result.scalar_one_or_none()

    if not repo:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Repository not found in project.",
        )

    return repo


async def get_current_snapshot(
    snapshot_id: uuid.UUID,
    repository: Annotated[Repository, Depends(get_current_repository)],
    tenant: Annotated[
        tuple[Organization, Membership],
        Depends(require_permission(Permission.REPOSITORY_SNAPSHOT_VIEW)),
    ],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> RepositorySnapshot:
    """
    Snapshot Resolution Dependency:
    Resolves snapshot strictly scoped within the authenticated repository, project, and organization.
    """
    stmt = select(RepositorySnapshot).where(
        RepositorySnapshot.id == snapshot_id,
        RepositorySnapshot.repository_id == repository.id,
    )
    result = await db.execute(stmt)
    snapshot = result.scalar_one_or_none()

    if not snapshot:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Snapshot not found in repository.",
        )

    return snapshot


async def get_current_discovery(
    discovery_id: uuid.UUID,
    snapshot: Annotated[RepositorySnapshot, Depends(get_current_snapshot)],
    tenant: Annotated[
        tuple[Organization, Membership],
        Depends(require_permission(Permission.REPOSITORY_DISCOVERY_VIEW)),
    ],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> DiscoveryRun:
    """
    Discovery Run Resolution Dependency:
    Resolves discovery run strictly scoped within the authenticated snapshot, repository, project, and organization.
    """
    stmt = select(DiscoveryRun).where(
        DiscoveryRun.id == discovery_id,
        DiscoveryRun.snapshot_id == snapshot.id,
    )
    result = await db.execute(stmt)
    discovery = result.scalar_one_or_none()

    if not discovery:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Discovery run not found in snapshot.",
        )

    return discovery


async def get_or_create_knowledge_base(
    project: Annotated[Project, Depends(get_current_project)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> KnowledgeBase:
    """
    Knowledge Base Resolution Dependency:
    Resolves or creates the 1-to-1 KnowledgeBase for the authenticated project.
    Strictly tenant- and project-scoped.
    """
    stmt = select(KnowledgeBase).where(KnowledgeBase.project_id == project.id)
    result = await db.execute(stmt)
    kb = result.scalar_one_or_none()

    if not kb:
        # New bases take the configured embedding provider; the stored model/dimension decide how
        # every future query embeds (app/services/knowledge/embeddings.py).
        provider = build_default_embedding_provider()
        kb = KnowledgeBase(
            project_id=project.id,
            name=f"{project.name} Knowledge Base",
            description=f"Business knowledge base for {project.name}",
            embedding_model=provider.model_id,
            embedding_dimension=provider.dimension,
        )
        db.add(kb)
        await db.commit()
        await db.refresh(kb)

    return kb


async def get_current_knowledge_document(
    document_id: uuid.UUID,
    kb: Annotated[KnowledgeBase, Depends(get_or_create_knowledge_base)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> KnowledgeDocument:
    """
    Knowledge Document Resolution Dependency:
    Resolves document strictly scoped within the authenticated project's KnowledgeBase.
    Returns 404 on missing document or cross-tenant/cross-project attempts.
    """
    stmt = (
        select(KnowledgeDocument)
        .where(
            KnowledgeDocument.id == document_id,
            KnowledgeDocument.knowledge_base_id == kb.id,
        )
        .options(selectinload(KnowledgeDocument.chunks))
    )
    result = await db.execute(stmt)
    doc = result.scalar_one_or_none()

    if not doc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Knowledge document not found in project.",
        )

    return doc


async def get_or_create_assistant(
    project: Annotated[Project, Depends(get_current_project)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> Assistant:
    """
    Assistant Resolution Dependency:
    Resolves or creates the 1-to-1 Assistant configuration for the authenticated project.
    Strictly tenant- and project-scoped.
    """
    stmt = select(Assistant).where(Assistant.project_id == project.id)
    result = await db.execute(stmt)
    assistant = result.scalar_one_or_none()

    if not assistant:
        assistant = Assistant(
            project_id=project.id,
            name="Fussion Assistant",
            description=f"AI Assistant for {project.name}",
            welcome_message="Hi! How can I help you today?",
            system_instructions=None,
            brand_color="#6366F1",
            text_color="#FFFFFF",
            position=AssistantPosition.BOTTOM_RIGHT,
            avatar_url=None,
            starter_prompt="What can you tell me about your products?",
            is_enabled=True,
        )
        db.add(assistant)
        await db.commit()
        await db.refresh(assistant)

    return assistant


async def get_current_assistant(
    project: Annotated[Project, Depends(get_current_project)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> Assistant:
    """
    Assistant Lookup Dependency:
    Resolves the existing Assistant for the authenticated project.
    Returns 404 if not found or cross-tenant/cross-project.
    """
    stmt = select(Assistant).where(Assistant.project_id == project.id)
    result = await db.execute(stmt)
    assistant = result.scalar_one_or_none()

    if not assistant:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Assistant not found for project.",
        )

    return assistant


async def get_current_website_integration(
    project: Annotated[Project, Depends(get_current_project)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> WebsiteIntegration:
    """
    Website Integration Lookup Dependency:
    Resolves the existing WebsiteIntegration for the authenticated project.
    Returns 404 if not found or cross-tenant/cross-project.
    """
    stmt = select(WebsiteIntegration).where(WebsiteIntegration.project_id == project.id)
    result = await db.execute(stmt)
    integration = result.scalar_one_or_none()

    if not integration:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Website integration not found for project.",
        )

    return integration



