from datetime import timedelta

import pytest
from httpx import AsyncClient

from app.core.security import create_access_token, hash_password, verify_password


@pytest.mark.asyncio
async def test_password_hashing():
    pwd = "supersecretpassword123"
    hashed = hash_password(pwd)
    assert hashed != pwd
    assert verify_password(pwd, hashed) is True
    assert verify_password("wrongpassword", hashed) is False


@pytest.mark.asyncio
async def test_registration_success(client: AsyncClient):
    resp = await client.post(
        "/api/v1/auth/register",
        json={
            "email": "alice@example.com",
            "password": "Password123!",
            "full_name": "Alice Wonderland",
            "org_name": "Alice Corp",
        },
    )
    assert resp.status_code == 201
    data = resp.json()
    assert "access_token" in data
    assert data["token_type"] == "bearer"
    assert data["user"]["email"] == "alice@example.com"
    assert data["user"]["full_name"] == "Alice Wonderland"
    assert "hashed_password" not in data["user"]


@pytest.mark.asyncio
async def test_registration_duplicate_email(client: AsyncClient):
    payload = {
        "email": "duplicate@example.com",
        "password": "Password123!",
        "full_name": "Duplicate User",
    }
    resp1 = await client.post("/api/v1/auth/register", json=payload)
    assert resp1.status_code == 201

    # Second attempt with same email
    resp2 = await client.post("/api/v1/auth/register", json=payload)
    assert resp2.status_code == 400
    assert "already exists" in resp2.json()["detail"]


@pytest.mark.asyncio
async def test_login_success(client: AsyncClient):
    # Register first
    await client.post(
        "/api/v1/auth/register",
        json={
            "email": "bob@example.com",
            "password": "ValidPassword123!",
            "full_name": "Bob Builder",
        },
    )

    # Login
    resp = await client.post(
        "/api/v1/auth/login",
        json={
            "email": "bob@example.com",
            "password": "ValidPassword123!",
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "access_token" in data
    assert data["user"]["email"] == "bob@example.com"


@pytest.mark.asyncio
async def test_login_failure_wrong_password(client: AsyncClient):
    await client.post(
        "/api/v1/auth/register",
        json={
            "email": "charlie@example.com",
            "password": "ValidPassword123!",
        },
    )

    resp = await client.post(
        "/api/v1/auth/login",
        json={
            "email": "charlie@example.com",
            "password": "WrongPassword999!",
        },
    )
    assert resp.status_code == 401
    assert "Invalid email or password" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_login_failure_unknown_email(client: AsyncClient):
    resp = await client.post(
        "/api/v1/auth/login",
        json={
            "email": "nonexistent@example.com",
            "password": "SomePassword123!",
        },
    )
    assert resp.status_code == 401
    assert "Invalid email or password" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_get_me_success(client: AsyncClient):
    reg_resp = await client.post(
        "/api/v1/auth/register",
        json={
            "email": "me@example.com",
            "password": "ValidPassword123!",
            "full_name": "Me Myself",
        },
    )
    token = reg_resp.json()["access_token"]

    resp = await client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["email"] == "me@example.com"
    assert data["full_name"] == "Me Myself"
    assert "hashed_password" not in data


@pytest.mark.asyncio
async def test_auth_invalid_token(client: AsyncClient):
    resp = await client.get(
        "/api/v1/auth/me",
        headers={"Authorization": "Bearer invalid.jwt.token"},
    )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_auth_expired_token(client: AsyncClient):
    reg_resp = await client.post(
        "/api/v1/auth/register",
        json={
            "email": "expired@example.com",
            "password": "ValidPassword123!",
        },
    )
    user_id = reg_resp.json()["user"]["id"]

    # Issue an already-expired token
    expired_token = create_access_token(
        subject=user_id,
        expires_delta=timedelta(seconds=-10),
    )

    resp = await client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {expired_token}"},
    )
    assert resp.status_code == 401
    assert "expired" in resp.json()["detail"].lower()
