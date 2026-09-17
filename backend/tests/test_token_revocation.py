"""Tests for JWT token revocation (single-token and user-wide logout)."""

import uuid

import pytest
from httpx import AsyncClient

from app.core.redis import (
    blacklist_token,
    is_token_blacklisted,
    is_user_revoked,
    reset_token_blacklist,
    set_user_revoked_before,
)


@pytest.fixture(autouse=True)
def _clean_blacklist():
    reset_token_blacklist()
    yield
    reset_token_blacklist()


@pytest.mark.asyncio
async def test_blacklist_utilities():
    jti = str(uuid.uuid4())
    assert await is_token_blacklisted(jti) is False

    await blacklist_token(jti, ttl_seconds=60)
    assert await is_token_blacklisted(jti) is True


@pytest.mark.asyncio
async def test_user_revoked_utilities():
    user_id = uuid.uuid4()
    now = 1000

    assert await is_user_revoked(user_id, issued_at=now) is False

    await set_user_revoked_before(user_id, timestamp=now + 50)
    assert await is_user_revoked(user_id, issued_at=now) is True
    assert await is_user_revoked(user_id, issued_at=now + 100) is False


@pytest.mark.asyncio
async def test_single_token_logout(client: AsyncClient):
    # 1. Register a new user and receive access token
    reg_res = await client.post(
        "/api/v1/auth/register",
        json={
            "email": "revoke_test@example.com",
            "password": "Password123!",
            "full_name": "Revoke User",
            "org_name": "Revoke Corp",
        },
    )
    assert reg_res.status_code == 201
    token = reg_res.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    # 2. Token works initially
    me_res = await client.get("/api/v1/auth/me", headers=headers)
    assert me_res.status_code == 200
    assert me_res.json()["email"] == "revoke_test@example.com"

    # 3. Call logout
    logout_res = await client.post("/api/v1/auth/logout", headers=headers)
    assert logout_res.status_code == 200
    assert logout_res.json()["status"] == "ok"

    # 4. Token is now revoked
    me_after_logout = await client.get("/api/v1/auth/me", headers=headers)
    assert me_after_logout.status_code == 401
    assert "revoked" in me_after_logout.json()["detail"].lower()


@pytest.mark.asyncio
async def test_logout_all_devices(client: AsyncClient):
    # 1. Register user
    reg_res = await client.post(
        "/api/v1/auth/register",
        json={
            "email": "logout_all@example.com",
            "password": "Password123!",
            "full_name": "Logout All User",
        },
    )
    assert reg_res.status_code == 201
    token_device_1 = reg_res.json()["access_token"]
    headers_1 = {"Authorization": f"Bearer {token_device_1}"}

    # 2. Simulate second device login
    login_res = await client.post(
        "/api/v1/auth/login",
        json={"email": "logout_all@example.com", "password": "Password123!"},
    )
    assert login_res.status_code == 200
    token_device_2 = login_res.json()["access_token"]
    headers_2 = {"Authorization": f"Bearer {token_device_2}"}

    # Both tokens work
    assert (await client.get("/api/v1/auth/me", headers=headers_1)).status_code == 200
    assert (await client.get("/api/v1/auth/me", headers=headers_2)).status_code == 200

    # 3. Trigger logout-all from device 1
    logout_all_res = await client.post("/api/v1/auth/logout-all", headers=headers_1)
    assert logout_all_res.status_code == 200

    # 4. Both prior tokens are now revoked
    assert (await client.get("/api/v1/auth/me", headers=headers_1)).status_code == 401
    assert (await client.get("/api/v1/auth/me", headers=headers_2)).status_code == 401

    # 5. Fresh login receives new token_version and works
    fresh_login = await client.post(
        "/api/v1/auth/login",
        json={"email": "logout_all@example.com", "password": "Password123!"},
    )
    assert fresh_login.status_code == 200
    fresh_token = fresh_login.json()["access_token"]
    headers_3 = {"Authorization": f"Bearer {fresh_token}"}
    assert (await client.get("/api/v1/auth/me", headers=headers_3)).status_code == 200
