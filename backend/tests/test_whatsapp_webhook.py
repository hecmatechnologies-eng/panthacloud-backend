"""The WhatsApp webhook endpoint: authentication and acknowledgement.

The adapter tests cover translation; these cover the two things the endpoint decides that the
adapter cannot.

**Authentication is the whole point.** An unsigned POST must never reach the runtime, and must not
be able to tell a caller *why* it was refused - "your signature is wrong" and "that number is not
registered" are the same answer from outside, or the endpoint becomes an oracle for finding which
numbers a tenant has claimed.

**Acknowledgement is subtle.** Meta retries anything that is not a 2xx, so an authenticated
delivery carrying nothing answerable - a delivery receipt, an image, a verification ping - must be
acknowledged. Answering 400 there makes Meta redeliver the same payload indefinitely. Refusing to
acknowledge is reserved for authentication, where a 200 would mean *we did not check who you are*.
"""

from __future__ import annotations

import hashlib
import hmac
import json

import pytest
from httpx import AsyncClient

from app.core.config import settings

VERIFY_TOKEN = "verify-me"
APP_SECRET = "whatsapp-app-secret"
BASE = "/api/v1/webhooks/whatsapp"


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture(autouse=True)
def _whatsapp_config(monkeypatch: pytest.MonkeyPatch) -> None:
    """Signed and configured by default, so a test states only what it is actually testing.

    Set on ``settings`` rather than via the environment because these tests must not depend on a
    developer's local ``.env`` - a signature test that passes or fails on ambient configuration is
    not a test.
    """
    monkeypatch.setattr(settings, "WHATSAPP_VERIFY_TOKEN", VERIFY_TOKEN, raising=False)
    monkeypatch.setattr(settings, "WHATSAPP_APP_SECRET", APP_SECRET, raising=False)


def _sign(raw: bytes) -> dict[str, str]:
    digest = hmac.new(APP_SECRET.encode(), raw, hashlib.sha256).hexdigest()
    return {"X-Hub-Signature-256": f"sha256={digest}"}


def _payload(messages: list[dict]) -> dict:
    return {
        "object": "whatsapp_business_account",
        "entry": [
            {
                "id": "WABA",
                "changes": [
                    {
                        "field": "messages",
                        "value": {
                            "messaging_product": "whatsapp",
                            "metadata": {
                                "display_phone_number": "+256772123456",
                                "phone_number_id": "1234567890",
                            },
                            "contacts": [{"profile": {"name": "Amina"}, "wa_id": "256700111222"}],
                            "messages": messages,
                        },
                    }
                ],
            }
        ],
    }


def _message(**over: object) -> dict:
    base = {
        "from": "256700111222",
        "id": "wamid.1",
        "timestamp": "1735689600",
        "type": "text",
        "text": {"body": "Do you have a room?"},
    }
    base.update(over)
    return base


class TestVerificationHandshake:
    async def test_the_challenge_is_echoed_for_the_right_token(
        self, client: AsyncClient
    ) -> None:
        response = await client.get(
            f"{BASE}?hub.mode=subscribe&hub.verify_token={VERIFY_TOKEN}&hub.challenge=1158201444"
        )

        assert response.status_code == 200
        assert response.text == "1158201444"

    async def test_a_wrong_token_is_refused(self, client: AsyncClient) -> None:
        response = await client.get(
            f"{BASE}?hub.mode=subscribe&hub.verify_token=wrong&hub.challenge=1158201444"
        )

        assert response.status_code == 403

    async def test_a_non_subscribe_request_is_refused(self, client: AsyncClient) -> None:
        """Echoing the challenge outside a subscription would make this an open relay."""
        response = await client.get(f"{BASE}?hub.mode=unsubscribe&hub.challenge=1")

        assert response.status_code == 400

    async def test_an_unconfigured_token_refuses_rather_than_passing(
        self, client: AsyncClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A comparison against an empty value passes whenever the caller sends an empty token.

        That would make the webhook publicly completable, so absent configuration is a 503.
        """
        monkeypatch.setattr(settings, "WHATSAPP_VERIFY_TOKEN", None, raising=False)

        response = await client.get(f"{BASE}?hub.mode=subscribe&hub.verify_token=&hub.challenge=1")

        assert response.status_code == 503


class TestSignatureIsRequired:
    async def test_an_unsigned_delivery_is_refused(self, client: AsyncClient) -> None:
        raw = json.dumps(_payload([_message()])).encode()

        response = await client.post(BASE, content=raw)

        assert response.status_code == 401

    async def test_a_tampered_delivery_is_refused(self, client: AsyncClient) -> None:
        raw = json.dumps(_payload([_message()])).encode()
        headers = _sign(raw)
        tampered = raw.replace(b"Do you have a room?", b"Give me the presidential suite")

        response = await client.post(BASE, content=tampered, headers=headers)

        assert response.status_code == 401

    async def test_no_configured_app_secret_refuses_everything(
        self, client: AsyncClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Fail closed.

        The alternative - treating an unverifiable request as acceptable - is an endpoint anyone on
        the internet can make the assistant answer on, and spend a tenant's quota with.
        """
        monkeypatch.setattr(settings, "WHATSAPP_APP_SECRET", None, raising=False)
        raw = json.dumps(_payload([_message()])).encode()

        response = await client.post(BASE, content=raw, headers=_sign(raw))

        assert response.status_code == 401


class TestAcknowledgement:
    async def test_a_signed_delivery_is_acknowledged(self, client: AsyncClient) -> None:
        """200 even though the number is not registered.

        The signature was valid, so the delivery is genuinely ours; refusing to acknowledge would
        make Meta redeliver it forever. The refusal that matters happened per-message.
        """
        raw = json.dumps(_payload([_message()])).encode()

        response = await client.post(BASE, content=raw, headers=_sign(raw))

        assert response.status_code == 200

    async def test_a_delivery_receipt_is_acknowledged_not_answered(self, client: AsyncClient) -> None:
        """A status update has nothing to answer.

        Answering it with anything but 2xx causes an unbounded retry loop against Meta.
        """
        payload = {
            "entry": [
                {
                    "id": "WABA",
                    "changes": [
                        {
                            "field": "messages",
                            "value": {
                                "metadata": {"phone_number_id": "1234567890"},
                                "statuses": [
                                    {"id": "wamid.1", "status": "delivered", "timestamp": "1735689600"}
                                ],
                            },
                        }
                    ],
                }
            ]
        }
        raw = json.dumps(payload).encode()

        response = await client.post(BASE, content=raw, headers=_sign(raw))

        assert response.status_code == 200

    async def test_an_unparseable_body_is_acknowledged(self, client: AsyncClient) -> None:
        """Authenticated but unreadable.

        Retrying a body that will never parse cannot succeed, so this must not become a loop.
        """
        raw = b"{not json at all"

        response = await client.post(BASE, content=raw, headers=_sign(raw))

        assert response.status_code == 200