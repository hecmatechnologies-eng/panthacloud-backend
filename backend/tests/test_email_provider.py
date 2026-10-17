"""The provider's two pieces of real logic: webhook signatures and quoted-replies.

**The signature tests sign like Svix does rather than mocking a verifier.** A test that asserts a
hand-written comparison works proves only that the test's own comparison works. These build the
signed content the same way the real thing does and check that a genuine delivery passes and that
each way of being wrong fails:

- the body altered after signing
- the wrong secret
- a timestamp outside tolerance, which is a valid signature and a replay
- a missing header

**Replay is tested separately from forgery** on purpose. A captured, genuinely-signed delivery
passes every check except freshness, so a verifier with no timestamp check is not "nearly secure" -
it is fully replayable, and nothing else in the function would catch it.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import time

import pytest

from app.channels.email.provider import (
    WebhookSignatureError,
    split_address,
    verify_webhook,
)
from app.channels.email.threading import looks_like_reply, strip_quoted_reply

# A key of the shape Svix issues. Any 32 random bytes work; the format is what matters.
SECRET = "whsec_" + base64.b64encode(bytes(range(32))).decode()
OTHER_SECRET = "whsec_" + base64.b64encode(bytes(range(32, 64))).decode()

BODY = b'{"type":"email.received","data":{"email_id":"abc-123"}}'


def sign(
    *,
    body: bytes = BODY,
    msg_id: str = "msg_1",
    timestamp: str | None = None,
    secret: str = SECRET,
) -> dict[str, str]:
    """Build headers the way Svix does, so the tests exercise the real scheme."""
    ts = timestamp if timestamp is not None else str(int(time.time()))
    key = base64.urlsafe_b64decode((secret.removeprefix("whsec_")) + "==")
    signed = f"{msg_id}.{ts}.".encode() + body
    sig = base64.b64encode(hmac.new(key, signed, hashlib.sha256).digest()).decode()
    return {
        "svix-id": msg_id,
        "svix-timestamp": ts,
        "svix-signature": f"v1,{sig}",
    }


class TestWebhookSignature:
    def test_a_genuine_delivery_passes(self) -> None:
        verify_webhook(raw_body=BODY, headers=sign(), secret=SECRET)  # must not raise

    def test_header_case_does_not_matter(self) -> None:
        """HTTP header names are case-insensitive and a framework may not preserve case."""
        headers = {k.upper(): v for k, v in sign().items()}
        verify_webhook(raw_body=BODY, headers=headers, secret=SECRET)

    def test_a_body_changed_after_signing_is_refused(self) -> None:
        """The signature covers the body, so this is the forgery case."""
        headers = sign()
        with pytest.raises(WebhookSignatureError, match="no signature"):
            verify_webhook(raw_body=BODY + b'{"tampered":1}', headers=headers, secret=SECRET)

    def test_re_serialised_json_does_not_match(self) -> None:
        """The failure this guards is silent.

        Parsing the body and re-encoding it changes whitespace or key order, the signature stops
        matching, and every webhook is refused with no indication of why.
        """
        headers = sign(body=B'{"a":1,"b":2}')
        with pytest.raises(WebhookSignatureError):
            verify_webhook(raw_body=b'{"b":2,"a":1}', headers=headers, secret=SECRET)

    def test_the_wrong_secret_is_refused(self) -> None:
        with pytest.raises(WebhookSignatureError, match="no signature"):
            verify_webhook(raw_body=BODY, headers=sign(), secret=OTHER_SECRET)

    def test_a_replayed_but_genuinely_signed_delivery_is_refused(self) -> None:
        """Valid signature, stale timestamp. The only thing that stops it is freshness.

        Without the timestamp check every other test here still passes and the endpoint is fully
        replayable, which is why this is asserted separately.
        """
        stale = str(int(time.time()) - 3600)
        with pytest.raises(WebhookSignatureError, match="tolerance"):
            verify_webhook(raw_body=BODY, headers=sign(timestamp=stale), secret=SECRET)

    def test_a_timestamp_inside_the_window_passes(self) -> None:
        verify_webhook(
            raw_body=BODY,
            headers=sign(timestamp=str(int(time.time()) - 60)),
            secret=SECRET,
        )

    def test_a_timestamp_from_the_future_is_also_refused(self) -> None:
        """Tolerance is two-sided; otherwise a forged future timestamp never ages out."""
        with pytest.raises(WebhookSignatureError, match="tolerance"):
            verify_webhook(
                raw_body=BODY,
                headers=sign(timestamp=str(int(time.time()) + 3600)),
                secret=SECRET,
            )

    @pytest.mark.parametrize(
        "missing", ["svix-id", "svix-timestamp", "svix-signature"]
    )
    def test_a_missing_header_is_refused(self, missing: str) -> None:
        headers = {k: v for k, v in sign().items() if k != missing}
        with pytest.raises(WebhookSignatureError, match="missing"):
            verify_webhook(raw_body=BODY, headers=headers, secret=SECRET)

    def test_no_configured_secret_refuses_rather_than_accepting(self) -> None:
        """Fail closed.

        With no secret there is nothing to compare against, and treating "cannot verify" as "allow"
        would leave the endpoint open to anyone who found its URL.
        """
        with pytest.raises(WebhookSignatureError, match="no webhook signing secret"):
            verify_webhook(raw_body=BODY, headers=sign(), secret=None)

    def test_a_rotated_key_still_accepts_the_delivery_in_flight(self) -> None:
        """Resend sends several signatures during rotation; any one matching must be accepted.

        Refusing would drop every email that was mid-delivery when the key changed.
        """
        headers = sign()
        old = headers["svix-signature"]
        new = sign(secret=OTHER_SECRET)["svix-signature"]
        headers["svix-signature"] = f"{new} {old}"

        verify_webhook(raw_body=BODY, headers=headers, secret=SECRET)

    def test_an_unknown_signature_version_is_refused(self) -> None:
        headers = sign()
        headers["svix-signature"] = "v2,not-a-signature"
        with pytest.raises(WebhookSignatureError, match="no signature"):
            verify_webhook(raw_body=BODY, headers=headers, secret=SECRET)


class TestSplitAddress:
    @pytest.mark.parametrize(
        ("raw", "address", "name"),
        [
            ('"Amina Okello" <amina@example.com>', "amina@example.com", "Amina Okello"),
            ("amina@example.com", "amina@example.com", None),
            ("Amina <amina@example.com>", "amina@example.com", "Amina"),
            ("<amina@example.com>", "amina@example.com", None),
            ("not an address", "", None),
            (None, "", None),
        ],
    )
    def test_it_splits_display_names_from_addresses(
        self, raw: str | None, address: str, name: str | None
    ) -> None:
        """The guest's name arrives free with an email, unlike any other channel.

        Worth parsing properly: a mangled address becomes a session that no later reply can match.
        """
        assert split_address(raw) == (address, name)


class TestStripQuotedReply:
    def test_a_plain_message_is_untouched(self) -> None:
        assert strip_quoted_reply("Do you have a room for Friday?") == (
            "Do you have a room for Friday?"
        )

    @pytest.mark.parametrize(
        "quoted",
        [
            # Gmail / Apple Mail
            (
                "\n\nOn 3 Nov 2026 at 10:22, K Hotels Entebbe <desk@example.com> wrote:\n"
                "> Your suite is available on Friday.\n"
            ),
            # Outlook's underscore divider
            (
                "\n\n________________________________\nFrom: K Hotels <desk@example.com>\n"
                "Your suite is available."
            ),
            # Mailing-list separator
            "\n\n-----Original Message-----\nFrom: desk@example.com\nYour suite is available.",
            # The oldest convention, and still the most common
            "\n\n> Your suite is available on Friday.\n> Rate is 400,000 UGX.",
        ],
        ids=["attribution", "outlook-divider", "original-message", "angle-brackets"],
    )
    def test_every_common_quote_convention_is_removed(self, quoted: str) -> None:
        """Each client formats its own way and there is no standard.

        Left in, the quoted half is our own output read back as the guest speaking - so the assistant
        answers the hotel's sentence rather than the guest's question.
        """
        assert strip_quoted_reply("What is the rate?" + quoted) == "What is the rate?"

    def test_an_unfamiliar_format_is_left_alone_rather_than_lost(self) -> None:
        """A message with its history attached beats no message.

        Returning "" here would silently drop a guest's enquiry because their mail client used a
        format nobody anticipated.
        """
        raw = "What is the rate?\n\n[Quoted text follows in an unfamiliar shape]"
        assert strip_quoted_reply(raw) == raw.strip()

    def test_the_new_text_survives_when_it_contains_an_angle_bracket(self) -> None:
        """A `>` after the halfway mark is the guest writing, not a quote.

        Otherwise "> that was my question" truncates the message at that point.
        """
        raw = "Here is a long first paragraph about the booking.\n\n> and one more thing\n"
        assert "> and one more thing" in strip_quoted_reply(raw)

    def test_an_empty_message_returns_empty(self) -> None:
        assert strip_quoted_reply("") == ""

    def test_windows_line_endings_are_handled(self) -> None:
        raw = "What is the rate?\r\n\r\nOn 3 Nov 2026, desk@example.com wrote:\r\n> Hello.\r\n"
        assert strip_quoted_reply(raw) == "What is the rate?"

    def test_looks_like_reply_distinguishes_a_real_reply(self) -> None:
        """A guest who presses Reply and sends nothing has asked nothing.

        Answering "how can I help?" to an empty reply is noise, and this is how it is avoided.
        """
        assert looks_like_reply("Yes\n\nOn 3 Nov, desk@example.com wrote:\n> Hello") is True
        assert looks_like_reply("Do you have a room for Friday?") is False

class TestOutboundHeaders:
    """Headers on a reply we send.

    Asserted on the built payload rather than on a live message's raw source, because a missing
    opt-out header is not an error - it is simply a lower score, and would otherwise be found only
    in a delivery statistic weeks later.
    """

    def _payload(self, **overrides):
        from app.channels.email.provider import build_payload

        kwargs = {
            "from_address": "reservations@ai-mwalimu.com",
            "to_address": "guest@example.com",
            "subject": "Re: Rooms",
            "text": "Here are our room rates.",
        }
        kwargs.update(overrides)
        return build_payload(**kwargs)

    def test_a_reply_offers_a_one_click_opt_out(self) -> None:
        """The header Gmail now requires from senders of automated mail."""
        payload = self._payload(unsubscribe_url="https://api.example.com/u/token123")
        headers = payload["headers"]
        assert headers["List-Unsubscribe"] == "<https://api.example.com/u/token123>"
        assert headers["List-Unsubscribe-Post"] == "List-Unsubscribe=One-Click"

    def test_one_click_is_never_announced_without_a_url(self) -> None:
        """Announcing one-click with no one-click URL makes clients try and fail."""
        payload = self._payload()
        assert "headers" not in payload

    def test_threading_headers_are_both_present(self) -> None:
        """In-Reply-To names the parent, References the chain; clients read different ones."""
        payload = self._payload(reply_to_message_id="<abc@mail.example.com>")
        headers = payload["headers"]
        assert headers["In-Reply-To"] == "<abc@mail.example.com>"
        assert headers["References"] == "<abc@mail.example.com>"

    def test_threading_and_opt_out_coexist(self) -> None:
        """The common real case: a threaded reply that also carries the opt-out."""
        payload = self._payload(
            reply_to_message_id="<abc@mail.example.com>",
            unsubscribe_url="https://api.example.com/u/token123",
        )
        assert set(payload["headers"]) == {
            "In-Reply-To",
            "References",
            "List-Unsubscribe",
            "List-Unsubscribe-Post",
        }

    def test_the_recipient_is_a_list(self) -> None:
        """Resend rejects a bare string here, and the failure would only show on the first send."""
        assert self._payload()["to"] == ["guest@example.com"]
