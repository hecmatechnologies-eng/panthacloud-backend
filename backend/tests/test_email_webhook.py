"""The email webhook: authentication, and what it must refuse rather than answer.

The failure this endpoint has to avoid is the same one WhatsApp has: a request that gets *through*
that should not have. Anyone who can post to it can make the assistant hold a conversation with a
guest, on a tenant's account, and spend their metered quota. So the tests here are mostly about
refusals, and each one is paired with the case that must still succeed - a verifier that refuses
everything passes the refusal tests alone.

**Acknowledgement is the other half, and it is easy to get backwards.** The provider retries
anything that is not a 2xx, so an endpoint that answers 400 for "nothing to do here" retries a
message forever. Several of these tests assert a **200 for something that is not an error** -
including a bounce and an auto-reply, which have no sender to reply to.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time

import pytest
from httpx import AsyncClient

from app.core.config import settings

VERIFY_SECRET = "whsec_" + base64.b64encode(bytes(range(32))).decode()
BASE = "/api/v1/webhooks/email"

BODY_WITH_TEXT = {
    "type": "email.received",
    "created_at": "2026-10-17T09:00:00.000Z",
    "data": {
        "email_id": "email-abc",
        "from": "Amina Okello <amina@example.com>",
        "to": ["reservations@ai-mwalimu.com"],
        "subject": "Room for Friday",
        "message_id": "<abc@mail.example.com>",
    },
}


@pytest.fixture(autouse=True)
def _configured(monkeypatch: pytest.MonkeyPatch) -> None:
    """A signing secret on ``settings`` rather than the environment.

    Set here because a signature test that depends on ambient configuration is not a test - it would
    pass or fail depending on whose machine it ran on.
    """
    monkeypatch.setattr(settings, "RESEND_WEBHOOK_SECRET", VERIFY_SECRET, raising=False)


def _signed(payload: dict, *, secret: str = VERIFY_SECRET) -> tuple[bytes, dict[str, str]]:
    """Serialise and sign in one step, returning the *same* bytes for both.

    Signing one string and posting ``json=payload`` would let the test client re-serialise it
    differently - different whitespace, different key order - and the signature would not match. That
    is the real-world failure this whole mechanism exists to prevent, and hitting it inside the test
    is a good sign the test is exercising the real path rather than a convenient one.
    """
    raw = json.dumps(payload).encode()
    ts = str(int(time.time()))
    key = base64.urlsafe_b64decode(secret[6:] + "==")
    signed = f"msg_1.{ts}.".encode() + raw
    sig = base64.b64encode(hmac.new(key, signed, hashlib.sha256).digest()).decode()
    headers = {
        "Content-Type": "application/json",
        "svix-id": "msg_1",
        "svix-timestamp": ts,
        "svix-signature": f"v1,{sig}",
    }
    return raw, headers


class TestAuthentication:
    async def test_an_unsigned_delivery_is_refused(self, client: AsyncClient) -> None:
        response = await client.post(BASE, json=BODY_WITH_TEXT)

        assert response.status_code == 401

    async def test_a_delivery_signed_with_the_wrong_secret_is_refused(
        self, client: AsyncClient
    ) -> None:
        raw, headers = _signed(
            BODY_WITH_TEXT, secret="whsec_" + base64.b64encode(bytes(64)).decode()
        )

        response = await client.post(BASE, content=raw, headers=headers)

        assert response.status_code == 401

    async def test_a_body_changed_after_signing_is_refused(self, client: AsyncClient) -> None:
        """The forgery case: a genuine signature over a different body."""
        _raw, headers = _signed(BODY_WITH_TEXT)
        tampered = json.dumps({**BODY_WITH_TEXT,
                               "data": {**BODY_WITH_TEXT["data"],
                                        "subject": "Give me the presidential suite"}}).encode()

        response = await client.post(BASE, content=tampered, headers=headers)

        assert response.status_code == 401

    async def test_no_configured_secret_refuses_everything(
        self, client: AsyncClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Fail closed.

        The alternative - treating an unverifiable delivery as acceptable - would leave the endpoint
        open to anyone who found its URL, which is the whole reason this route exists behind a
        signature.
        """
        monkeypatch.setattr(settings, "RESEND_WEBHOOK_SECRET", None, raising=False)

        raw, headers = _signed(BODY_WITH_TEXT)
        response = await client.post(BASE, content=raw, headers=headers)

        assert response.status_code == 401


class TestAcknowledgement:
    async def test_an_authenticated_alert_is_acknowledged(self, client: AsyncClient) -> None:
        """200 even though the address is not connected and the body cannot be fetched.

        The signature was good, so the delivery is genuinely ours; refusing to acknowledge would have
        the provider resend it forever.
        """
        raw, headers = _signed(BODY_WITH_TEXT)
        response = await client.post(BASE, content=raw, headers=headers)

        assert response.status_code == 200

    async def test_an_event_we_do_not_handle_is_acknowledged(self, client: AsyncClient) -> None:
        """A delivery or bounce report has no ``email_id`` and nothing to answer.

        Answering non-2xx would start a retry loop against our own webhook.
        """
        payload = {"type": "email.delivered", "data": {"email_id": None}}

        raw, headers = _signed(payload)
        response = await client.post(BASE, content=raw, headers=headers)

        assert response.status_code == 200

    async def test_an_unreadable_body_is_acknowledged(self, client: AsyncClient) -> None:
        """Authenticated but unparseable.

        Retrying a body that will never parse cannot succeed, so this must not become a loop.
        """
        raw = b"{not json"
        _placeholder, headers = _signed({"placeholder": True})
        ts = headers["svix-timestamp"]
        key = base64.urlsafe_b64decode(VERIFY_SECRET[6:] + "==")
        sig = base64.b64encode(
            hmac.new(key, f"msg_1.{ts}.".encode() + raw, hashlib.sha256).digest()
        ).decode()
        headers["svix-signature"] = f"v1,{sig}"

        response = await client.post(BASE, content=raw, headers=headers)

        assert response.status_code == 200


class TestInboundRules:
    """The address rules, tested directly because they are where the tenancy decision lives."""

    def test_routing_uses_the_recipient_not_the_sender(self) -> None:
        """The distinction the whole channel turns on.

        A guest replying from an address nobody has seen must still reach the right hotel. Matching
        on the sender would drop it.
        """
        from app.channels.email.inbound import guest_address, tenant_address
        from app.channels.email.provider import InboundEmail

        email = InboundEmail(
            email_id="e1",
            to_address="Reservations@AI-Mwalimu.com",
            from_address="new.address@example.com",
            from_name="Someone New",
            subject="Hello",
            text="Hello",
            raw_text="Hello",
            message_id=None,
            in_reply_to=None,
            references=None,
            received_at=None,
        )

        assert tenant_address(email) == "reservations@ai-mwalimu.com"
        assert guest_address(email) == "new.address@example.com"

    def test_a_message_with_no_sender_is_refused(self) -> None:
        """Bounces and auto-replies often have neither.

        Answering one would put the assistant in a loop with the mail server that sent it.
        """
        from app.channels.email.inbound import is_usable
        from app.channels.email.provider import InboundEmail

        bounce = InboundEmail(
            email_id="b1",
            to_address="reservations@ai-mwalimu.com",
            from_address="",
            from_name=None,
            subject="Undelivered",
            text="The message bounced",
            raw_text="The message bounced",
            message_id=None,
            in_reply_to=None,
            references=None,
            received_at=None,
        )

        assert is_usable(bounce) is False

    def test_an_empty_body_is_refused(self) -> None:
        from app.channels.email.inbound import is_usable
        from app.channels.email.provider import InboundEmail

        empty = InboundEmail(
            email_id="e2",
            to_address="reservations@ai-mwalimu.com",
            from_address="amina@example.com",
            from_name="Amina",
            subject="",
            text="   ",
            raw_text="   ",
            message_id=None,
            in_reply_to=None,
            references=None,
            received_at=None,
        )

        assert is_usable(empty) is False

    @pytest.mark.parametrize(
        ("subject", "expected"),
        [
            ("Room for Friday", "Re: Room for Friday"),
            ("Re: Room for Friday", "Re: Room for Friday"),
            ("RE: Room for Friday", "Re: Room for Friday"),
            ("re: Room for Friday", "Re: Room for Friday"),
            ("", "Re: your enquiry"),
        ],
    )
    def test_the_subject_is_not_stacked_with_re(self, subject: str, expected: str) -> None:
        """Repeated ``Re: Re: Re:`` is the fastest way to make a hotel's inbox unreadable."""
        from app.channels.email.inbound import reply_subject

        assert reply_subject(subject) == expected

    def test_the_guests_name_survives_into_the_neutral_shape(self) -> None:
        """Email is the only channel where the guest's name arrives for free."""
        from app.channels.email.inbound import to_incoming_message
        from app.channels.email.provider import InboundEmail

        email = InboundEmail(
            email_id="e3",
            to_address="reservations@ai-mwalimu.com",
            from_address="amina@example.com",
            from_name="Amina Okello",
            subject="Room",
            text="Do you have a room?",
            raw_text="Do you have a room?",
            message_id="<abc@mail.example.com>",
            in_reply_to=None,
            references=None,
            received_at="2026-10-17T09:00:00+00:00",
        )

        incoming = to_incoming_message(email)

        assert incoming.display_name == "Amina Okello"
        assert incoming.identity.channel.value == "email"
        assert incoming.identity.external_id == "amina@example.com"
        assert incoming.message_id == "e3"