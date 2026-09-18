"""Tests for GitHub webhook ingestion and origin auto-verification."""

import hashlib
import hmac
import json
import uuid

import pytest
from sqlalchemy import select

from app.core.config import settings
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


@pytest.fixture
async def sample_integration(db_session):
    user = User(
        id=uuid.uuid4(),
        email=f"user-{uuid.uuid4().hex[:6]}@example.com",
        full_name="Webhook Tester",
        hashed_password="hash",
    )
    db_session.add(user)
    org = Organization(id=uuid.uuid4(), name="Test Org", slug=f"test-org-{uuid.uuid4().hex[:6]}")
    db_session.add(org)
    project = Project(
        id=uuid.uuid4(),
        name="Test Project",
        slug=f"proj-{uuid.uuid4().hex[:6]}",
        organization_id=org.id,
    )
    db_session.add(project)

    integration = WebsiteIntegration(
        id=uuid.uuid4(),
        project_id=project.id,
        repository_owner="acmecorp",
        repository_name="sweetshop",
        default_branch="main",
        framework_skill_id="nextjs-app-router",
        widget_target_path="app/layout.tsx",
        status=WebsiteIntegrationStatus.PR_CREATED,
    )
    db_session.add(integration)

    run = IntegrationRun(
        id=uuid.uuid4(),
        integration_id=integration.id,
        status=IntegrationRunStatus.PR_CREATED,
        branch_name="fussion/widget-install",
        sandbox_ref="sbx-test",
        pull_request_number=42,
        pull_request_url="https://github.com/acmecorp/sweetshop/pull/42",
    )
    db_session.add(run)

    await db_session.commit()
    await db_session.refresh(integration)
    await db_session.refresh(run)
    return integration, run


def _sign_payload(payload_bytes: bytes, secret: str) -> str:
    return "sha256=" + hmac.new(secret.encode("utf-8"), payload_bytes, hashlib.sha256).hexdigest()


@pytest.mark.asyncio
async def test_webhook_ping(client, monkeypatch):
    secret = "test-webhook-secret"
    monkeypatch.setattr(settings, "GITHUB_APP_WEBHOOK_SECRET", secret)

    payload = json.dumps({"zen": "Keep it simple"}).encode("utf-8")
    signature = _sign_payload(payload, secret)

    resp = await client.post(
        "/api/v1/webhooks/github",
        content=payload,
        headers={
            "content-type": "application/json",
            "x-github-event": "ping",
            "x-hub-signature-256": signature,
        },
    )
    assert resp.status_code == 200
    assert resp.json() == {"status": "pong"}


@pytest.mark.asyncio
async def test_webhook_invalid_signature_rejected(client, monkeypatch):
    monkeypatch.setattr(settings, "GITHUB_APP_WEBHOOK_SECRET", "correct-secret")

    payload = json.dumps({"action": "ping"}).encode("utf-8")
    signature = _sign_payload(payload, "wrong-secret")

    resp = await client.post(
        "/api/v1/webhooks/github",
        content=payload,
        headers={
            "content-type": "application/json",
            "x-github-event": "ping",
            "x-hub-signature-256": signature,
        },
    )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_webhook_pull_request_merged(client, sample_integration, db_session, monkeypatch):
    integration, _run = sample_integration
    secret = "test-webhook-secret"
    monkeypatch.setattr(settings, "GITHUB_APP_WEBHOOK_SECRET", secret)

    payload_dict = {
        "action": "closed",
        "pull_request": {
            "number": 42,
            "merged": True,
        },
        "repository": {
            "owner": {"login": "acmecorp"},
            "name": "sweetshop",
        },
    }
    payload = json.dumps(payload_dict).encode("utf-8")
    signature = _sign_payload(payload, secret)

    resp = await client.post(
        "/api/v1/webhooks/github",
        content=payload,
        headers={
            "content-type": "application/json",
            "x-github-event": "pull_request",
            "x-hub-signature-256": signature,
        },
    )
    assert resp.status_code == 200
    assert resp.json()["event"] == "pull_request.merged"

    await db_session.refresh(integration)
    assert integration.status == WebsiteIntegrationStatus.PR_MERGED


@pytest.mark.asyncio
async def test_webhook_deployment_status_success_auto_registers_origins(
    client, sample_integration, db_session, monkeypatch
):
    integration, _ = sample_integration
    secret = "test-webhook-secret"
    monkeypatch.setattr(settings, "GITHUB_APP_WEBHOOK_SECRET", secret)

    payload_dict = {
        "deployment_status": {
            "state": "success",
            "environment_url": "https://sweets.com",
        },
        "repository": {
            "owner": {"login": "acmecorp"},
            "name": "sweetshop",
        },
    }
    payload = json.dumps(payload_dict).encode("utf-8")
    signature = _sign_payload(payload, secret)

    resp = await client.post(
        "/api/v1/webhooks/github",
        content=payload,
        headers={
            "content-type": "application/json",
            "x-github-event": "deployment_status",
            "x-hub-signature-256": signature,
        },
    )
    assert resp.status_code == 200
    assert resp.json()["event"] == "deployment_status.success"

    await db_session.refresh(integration)
    assert integration.status == WebsiteIntegrationStatus.DEPLOYED

    # Verify that both sweets.com AND www.sweets.com were registered as verified origins!
    origins = (
        await db_session.execute(
            select(AllowedOrigin).where(AllowedOrigin.integration_id == integration.id)
        )
    ).scalars().all()

    origin_urls = {o.origin for o in origins}
    assert "https://sweets.com" in origin_urls
    assert "https://www.sweets.com" in origin_urls
    for o in origins:
        assert o.is_verified is True
        assert o.source == "github_deployment"
