"""Tests for tenant resolver guardrails, provisional auto-discovery, and self-healing fallback."""

import uuid
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import select

from app.models.allowed_origin import AllowedOrigin
from app.models.organization import Organization
from app.models.project import Project
from app.models.user import User
from app.models.website_integration import (
    IntegrationRun,
    IntegrationRunStatus,
    WebsiteIntegration,
    WebsiteIntegrationStatus,
)
from app.runtime.resolver import TenantResolutionError, resolve_tenant
from app.services.integration.github import set_git_provider


@pytest.fixture
async def setup_tenant_data(db_session):
    user = User(
        id=uuid.uuid4(),
        email=f"user-{uuid.uuid4().hex[:6]}@example.com",
        full_name="Resolver Tester",
        hashed_password="hash",
    )
    db_session.add(user)
    org = Organization(id=uuid.uuid4(), name="Resolver Org", slug=f"res-org-{uuid.uuid4().hex[:6]}")
    db_session.add(org)
    project = Project(
        id=uuid.uuid4(),
        name="Resolver Project",
        slug=f"proj-{uuid.uuid4().hex[:6]}",
        organization_id=org.id,
    )
    db_session.add(project)

    integration = WebsiteIntegration(
        id=uuid.uuid4(),
        project_id=project.id,
        repository_owner="sweetowner",
        repository_name="sweetrepo",
        default_branch="main",
        framework_skill_id="nextjs-app-router",
        widget_target_path="app/layout.tsx",
        status=WebsiteIntegrationStatus.PR_CREATED,
    )
    db_session.add(integration)

    origin = AllowedOrigin(
        id=uuid.uuid4(),
        integration_id=integration.id,
        origin="https://official.sweets.com",
        is_verified=True,
        source="manual",
    )
    db_session.add(origin)

    await db_session.commit()
    await db_session.refresh(integration)
    await db_session.refresh(origin)
    return org, project, integration, origin


@pytest.mark.asyncio
async def test_resolve_verified_origin_success(db_session, setup_tenant_data):
    org, project, integration, origin = setup_tenant_data
    ctx = await resolve_tenant(db_session, integration.public_key, "https://official.sweets.com")

    assert ctx.integration_id == integration.id
    assert ctx.project_id == project.id
    assert ctx.organization_id == org.id
    assert ctx.origin == "https://official.sweets.com"

    # Verify last_seen_at updated
    await db_session.refresh(origin)
    assert origin.last_seen_at is not None


@pytest.mark.asyncio
async def test_resolve_loopback_private_rejected(db_session, setup_tenant_data):
    _, _, integration, _ = setup_tenant_data
    with pytest.raises(TenantResolutionError):
        await resolve_tenant(db_session, integration.public_key, "http://localhost:3000")

    with pytest.raises(TenantResolutionError):
        await resolve_tenant(db_session, integration.public_key, "https://192.168.1.5")


@pytest.mark.asyncio
async def test_resolve_preview_origin_auto_binds_provisional(db_session, setup_tenant_data):
    _org, _project, integration, _ = setup_tenant_data
    preview_url = "https://sweetrepo-pr-12.vercel.app"

    ctx = await resolve_tenant(db_session, integration.public_key, preview_url)
    assert ctx.integration_id == integration.id
    assert ctx.origin == preview_url

    # Check database
    created = (
        await db_session.execute(
            select(AllowedOrigin).where(
                AllowedOrigin.integration_id == integration.id,
                AllowedOrigin.origin == preview_url,
            )
        )
    ).scalar_one_or_none()

    assert created is not None
    assert created.is_verified is False
    assert created.source == "preview_provisional"
    assert created.last_seen_at is not None


@pytest.mark.asyncio
async def test_resolve_fast_deploy_race_self_heals(db_session, setup_tenant_data):
    """When PR_CREATED integration receives traffic on sweets.com before webhook arrives."""
    _org, _project, integration, _ = setup_tenant_data

    # Add a run
    run = IntegrationRun(
        id=uuid.uuid4(),
        integration_id=integration.id,
        status=IntegrationRunStatus.PR_CREATED,
        branch_name="fussion/install",
        sandbox_ref="sbx-test",
        pull_request_number=101,
    )
    db_session.add(run)
    await db_session.commit()

    # Mock git provider to return merged=True
    mock_provider = AsyncMock()
    mock_provider.get_pull_request = AsyncMock(
        return_value={"number": 101, "merged": True, "status": "merged"}
    )
    set_git_provider(mock_provider)

    ctx = await resolve_tenant(db_session, integration.public_key, "https://sweets.com")
    assert ctx.integration_id == integration.id
    assert ctx.origin == "https://sweets.com"

    # Status progressed to PR_MERGED
    await db_session.refresh(integration)
    assert integration.status == WebsiteIntegrationStatus.PR_MERGED

    # Provisional origins registered for both sweets.com and www.sweets.com
    origins = (
        await db_session.execute(
            select(AllowedOrigin).where(AllowedOrigin.integration_id == integration.id)
        )
    ).scalars().all()

    origin_map = {o.origin: o for o in origins}
    assert "https://sweets.com" in origin_map
    assert "https://www.sweets.com" in origin_map
    assert origin_map["https://sweets.com"].is_verified is False
    assert origin_map["https://sweets.com"].source == "auto_provisional"
