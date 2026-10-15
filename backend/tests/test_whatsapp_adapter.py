"""The WhatsApp adapter: signature, envelope, and the refusals.

Three things here are tested because they are the ones a provider can break silently.

**The signature** is the security boundary, and the failure mode of getting it wrong is an
open endpoint rather than an error. Tested against real HMACs rather than a mock, because a mock
cannot tell a correct implementation from one that compares the right-looking things.

**The envelope is iterated.** A batch carrying several entries and several changes is the normal
case, and an implementation written to the documented ``entry[0].changes[0]`` example drops every
message after the first with no error. ``test_a_batch_keeps_every_message`` is the test that would
have caught that, and it is the reason this file exists.

**Groups are refused**, because a ``@g.us`` id keyed like a person merges every member's messages
into one conversation.
"""

from __future__ import annotations

import hashlib
import hmac
import json

import pytest

from app.channels.whatsapp import (
    SIGNATURE_HEADER,
    WebhookSignatureError,
    parse_webhook,
    verify_signature,
)

APP_SECRET = "test-app-secret"
BUSINESS_ID = "1234567890"
BUSINESS_NUMBER = "+256772123456"
GUEST_ID = "256700111222"


def _signed_body(payload: dict) -> tuple[bytes, str]:
    """The exact bytes a caller would send, and the matching signature over those bytes."""
    raw = json.dumps(payload).encode("utf-8")
    digest = hmac.new(APP_SECRET.encode(), raw, hashlib.sha256).hexdigest()
    return raw, f"sha256={digest}"


def _message(wa_id: str = GUEST_ID, body: str = "Do you have a room?", mid: str = "wamid.1") -> dict:
    return {"from": wa_id, "id": mid, "timestamp": "1735689600", "type": "text", "text": {"body": body}}


def _payload(messages: list[dict], *, business_id: str = BUSINESS_ID, contacts: list | None = None) -> dict:
    return {
        "object": "whatsapp_business_account",
        "entry": [
            {
                "id": "WABA_ID",
                "changes": [
                    {
                        "field": "messages",
                        "value": {
                            "messaging_product": "whatsapp",
                            "metadata": {
                                "display_phone_number": BUSINESS_NUMBER,
                                "phone_number_id": business_id,
                            },
                            "contacts": contacts
                            if contacts is not None
                            else [{"profile": {"name": "Amina"}, "wa_id": GUEST_ID}],
                            "messages": messages,
                        },
                    }
                ],
            }
        ],
    }


class TestSignature:
    def test_a_correct_signature_passes(self) -> None:
        raw, signature = _signed_body(_payload([_message()]))
        verify_signature(raw_body=raw, signature=signature, app_secret=APP_SECRET)  # must not raise

    def test_a_tampered_body_is_refused(self) -> None:
        """The body is what is signed, so changing one byte must invalidate it."""
        raw, signature = _signed_body(_payload([_message()]))
        tampered = raw.replace(b"Do you have a room?", b"Do you have a suite?")
        with pytest.raises(WebhookSignatureError, match="does not match"):
            verify_signature(raw_body=tampered, signature=signature, app_secret=APP_SECRET)

    def test_the_wrong_secret_is_refused(self) -> None:
        raw, signature = _signed_body(_payload([_message()]))
        with pytest.raises(WebhookSignatureError):
            verify_signature(raw_body=raw, signature=signature, app_secret="a-different-secret")

    def test_a_missing_header_is_refused(self) -> None:
        raw, _ = _signed_body(_payload([_message()]))
        with pytest.raises(WebhookSignatureError, match="missing"):
            verify_signature(raw_body=raw, signature=None, app_secret=APP_SECRET)

    def test_the_deprecated_sha1_header_is_not_accepted(self) -> None:
        """`X-Hub-Signature` (sha1) must not be honoured as a fallback.

        Accepting it would mean an attacker could downgrade the check to sha1, which is not what
        protects this endpoint.
        """
        raw = json.dumps(_payload([_message()])).encode()
        sha1 = hmac.new(APP_SECRET.encode(), raw, hashlib.sha1).hexdigest()
        with pytest.raises(WebhookSignatureError, match="not sha256"):
            verify_signature(raw_body=raw, signature=sha1, app_secret=APP_SECRET)

    def test_no_configured_secret_refuses_rather_than_accepting(self) -> None:
        """Fail closed.

        With no app secret there is nothing to compare against, so an implementation that treated
        "cannot verify" as "allow" would accept every request on the internet.
        """
        raw, signature = _signed_body(_payload([_message()]))
        with pytest.raises(WebhookSignatureError, match="no WhatsApp app secret"):
            verify_signature(raw_body=raw, signature=signature, app_secret=None)

    def test_the_signature_covers_the_raw_bytes_not_a_reparse(self) -> None:
        """Re-serialising the parsed body must not reproduce the signature.

        This is the silent failure: if signing were done over `json.dumps(json.loads(raw))`, a
        payload with different whitespace would stop matching and every delivery would be refused
        with no explanation.
        """
        payload = _payload([_message()])
        _raw, signature = _signed_body(payload)
        reserialised = json.dumps(payload, separators=(",", ":")).encode()
        with pytest.raises(WebhookSignatureError):
            verify_signature(raw_body=reserialised, signature=signature, app_secret=APP_SECRET)


class TestEnvelope:
    def test_a_text_message_is_flattened_out_of_the_envelope(self) -> None:
        (message,) = parse_webhook(_payload([_message()]))

        assert message.text == "Do you have a room?"
        assert message.wa_id == GUEST_ID
        assert message.message_id == "wamid.1"
        assert message.phone_number_id == BUSINESS_ID
        assert message.display_phone_number == BUSINESS_NUMBER
        assert message.display_name == "Amina"
        assert message.timestamp is not None

    def test_a_batch_keeps_every_message(self) -> None:
        """The load-bearing test.

        Written to the documented ``entry[0].changes[0]`` this would return one message and drop the
        other three, with no error - a hotel quietly stops answering guests whenever Meta batches.
        """
        payload = {
            "entry": [
                {
                    "id": "WABA",
                    "changes": [
                        {"field": "messages", "value": {
                            "metadata": {"phone_number_id": BUSINESS_ID,
                                         "display_phone_number": BUSINESS_NUMBER},
                            "contacts": [{"profile": {"name": "A"}, "wa_id": "256700000001"}],
                            "messages": [_message("256700000001", "first", "wamid.1"),
                                         _message("256700000001", "second", "wamid.2")],
                        }},
                        {"field": "messages", "value": {
                            "metadata": {"phone_number_id": BUSINESS_ID,
                                         "display_phone_number": BUSINESS_NUMBER},
                            "contacts": [{"profile": {"name": "B"}, "wa_id": "256700000002"}],
                            "messages": [_message("256700000002", "third", "wamid.3")],
                        }},
                    ],
                },
                {
                    "id": "WABA",
                    "changes": [
                        {"field": "messages", "value": {
                            "metadata": {"phone_number_id": BUSINESS_ID,
                                         "display_phone_number": BUSINESS_NUMBER},
                            "contacts": [{"profile": {"name": "C"}, "wa_id": "256700000003"}],
                            "messages": [_message("256700000003", "fourth", "wamid.4")],
                        }},
                    ],
                },
            ]
        }

        parsed = parse_webhook(payload)

        assert [m.text for m in parsed] == ["first", "second", "third", "fourth"]

    def test_contact_names_match_on_wa_id_not_position(self) -> None:
        """`contacts[0]` corresponds to `messages[0]` only in the simple case.

        Two guests in one batch is normal, and positional matching would attach the wrong name to
        the wrong person.
        """
        payload = _payload(
            [_message("256700000001", "from A", "wamid.1"), _message("256700000002", "from B", "wamid.2")],
            contacts=[
                {"profile": {"name": "Amina"}, "wa_id": "256700000001"},
                {"profile": {"name": "Brian"}, "wa_id": "256700000002"},
            ],
        )

        parsed = parse_webhook(payload)

        assert [m.display_name for m in parsed] == ["Amina", "Brian"]

    def test_a_group_message_is_flagged_not_addressed_to_us(self) -> None:
        """A group id is not a person; keying a session on it merges every member's messages."""
        group = "1234567890-1234567890@g.us"
        (message,) = parse_webhook(_payload([_message(group, "room service?", "wamid.g")]))

        assert message.is_group is True
        assert message.addressed_to_business is False

    def test_a_change_without_metadata_is_skipped(self) -> None:
        """Without `metadata.phone_number_id` there is nothing to route on."""
        payload = {"entry": [{"id": "WABA", "changes": [{"field": "messages", "value": {
            "messages": [_message()]}}]}]}

        assert parse_webhook(payload) == []

    def test_a_status_update_yields_nothing_to_answer(self) -> None:
        """Receipts are acknowledged, not answered - returning 200 is what stops a retry loop."""
        payload = {"entry": [{"id": "WABA", "changes": [{"field": "messages", "value": {
            "metadata": {"phone_number_id": BUSINESS_ID},
            "statuses": [{"id": "wamid.1", "status": "delivered", "timestamp": "1735689600"}],
        }}]}]}

        assert parse_webhook(payload) == []

    def test_non_text_messages_are_skipped(self) -> None:
        """A caption is not a photo. Answering 'thanks, got it' to a passport is worse than silence."""
        image = {"from": GUEST_ID, "id": "wamid.i", "timestamp": "1735689600",
                 "type": "image", "image": {"caption": "my passport"}}

        assert parse_webhook(_payload([image])) == []

    @pytest.mark.parametrize(
        "payload",
        [
            pytest.param({}, id="empty object"),
            pytest.param({"entry": None}, id="null entry"),
            pytest.param({"entry": []}, id="no entries"),
            pytest.param({"entry": "not-a-list"}, id="entry is a string"),
            pytest.param({"entry": [{"changes": [{"value": {"metadata": {}}}]}]}, id="no phone id"),
        ],
    )
    def test_a_malformed_payload_yields_nothing_rather_than_raising(self, payload: dict) -> None:
        """Provider-controlled input must degrade to "nothing usable", not to a 500.

        A 500 here would make Meta redeliver the same bad payload forever.
        """
        assert parse_webhook(payload) == []


class TestToIncomingMessage:
    def test_it_becomes_the_channel_neutral_shape(self) -> None:
        (parsed,) = parse_webhook(_payload([_message()]))
        incoming = parsed.to_incoming_message()

        assert incoming.identity.channel.value == "whatsapp"
        assert incoming.identity.external_id == GUEST_ID
        assert incoming.message_id == "wamid.1"
        assert incoming.metadata["phone_number_id"] == BUSINESS_ID

    def test_the_plus_is_stripped_so_the_guest_keys_consistently(self) -> None:
        """Registration and session lookup must agree on the address form."""
        (parsed,) = parse_webhook(_payload([_message(wa_id="+256700111222")]))
        assert parsed.to_incoming_message().identity.external_id == "256700111222"

    def test_the_signature_header_name_is_the_v2_one(self) -> None:
        assert SIGNATURE_HEADER == "X-Hub-Signature-256"