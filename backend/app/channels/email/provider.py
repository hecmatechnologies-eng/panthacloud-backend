"""The Resend provider: the only file that knows this company exists (ADR-004).

Everything email-specific to Resend lives here so that changing provider is a change to this file
and nothing else. The rest of the codebase sees :class:`InboundEmail` and :func:`send_reply`, which
are ours.

**Two credentials, doing different jobs, and the distinction is the whole security model.**

- ``RESEND_API_KEY`` authenticates *our* calls to Resend - fetching a message, sending a reply.
- ``RESEND_WEBHOOK_SECRET`` authenticates *their* calls to us. It is a Svix signing secret and has
  nothing to do with the API key.

Using the API key to verify webhooks would be the obvious mistake and it is a real one: the API key
is a bearer token that appears in outbound requests, the signing secret never does. A webhook signed
with the wrong key is not "a bit less secure", it is an endpoint anyone who has ever seen an
outbound header can post to.

**Signature verification, and why it is not optional.** Resend signs every webhook with Svix:

===============================  ==========================================
``svix-id``                      the message id
``svix-timestamp``               when it was signed, as a unix string
``svix-signature``               ``v1,<base64>``, space separated on rotation
===============================  ==========================================

The signed content is ``{svix_id}.{svix_timestamp}.{raw_body}``, keyed on the signing secret. Three
properties this function has to get right, each of which fails *silently* when wrong:

- **The raw body.** Re-serialising the parsed JSON changes whitespace or key order and stops the
  signature matching, so every webhook is refused and nothing says why.
- **The signature is compared with ``compare_digest``**, not ``==`` - it does not short-circuit, so
  the time taken does not depend on how many leading characters matched.
- **The timestamp is checked.** A signature without a freshness check is replayable: capture one
  valid delivery and resend it forever. Resend documents this as a distinct attack from forgery.

The signature may carry several space-separated values because keys rotate; **any** one matching is
accepted, which is what makes rotation possible without dropping deliveries in flight.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import logging
import time
from dataclasses import dataclass
from email.utils import parseaddr
from typing import Any

import httpx

from app.core.config import settings

logger = logging.getLogger("fussion.channels.email")

RESEND_API_BASE = "https://api.resend.com"

#: How far a webhook timestamp may drift before it is treated as a replay. Svix's own default is
#: five minutes; anything longer widens the replay window for no benefit, since a legitimate
#: delivery is not delayed by that much in practice.
TIMESTAMP_TOLERANCE_SECONDS = 5 * 60


class EmailProviderError(Exception):
    """Something went wrong talking to, or hearing from, the email provider."""


class WebhookSignatureError(EmailProviderError):
    """The webhook signature was absent, malformed, or did not match.

    Kept distinct from a *payload* problem so the endpoint can answer 401 for one and 200 for the
    other. An unauthenticated caller must not be able to tell "your signature is wrong" from "that
    payload made no sense", because that difference is a free oracle.
    """


@dataclass(frozen=True, slots=True)
class InboundEmail:
    """One received email, flattened out of the provider's two-step shape.

    The provider announces an email with metadata only; the body arrives from a second call. Both
    are resolved before an :class:`InboundEmail` exists, so nothing downstream has to know that a
    message arrives in two pieces.
    """

    #: The provider's id, used to fetch the body and to make delivery idempotent.
    email_id: str
    #: Which address it was sent *to*. This is what identifies the tenant - the same job a business
    #: phone number does for WhatsApp - and it is stable across replies, because a reply still goes
    #: to us. The sender never plays that part.
    to_address: str
    #: The guest's address, as written by their mail client. Case is preserved here and normalised
    #: when the session is keyed, because the local part is case-sensitive by the letter of RFC 5321
    #: and folded by every provider in practice.
    from_address: str
    from_name: str | None
    subject: str
    #: Only the guest's *new* words, with any quoted earlier conversation removed. See
    #: :mod:`app.channels.email.threading`.
    text: str
    #: The raw body, kept so a failure to strip quotes degrades to "a longer message" rather than
    #: "no message".
    raw_text: str
    #: RFC 5322 ``Message-ID``, for matching a reply to the message it answers.
    message_id: str | None
    in_reply_to: str | None
    references: str | None
    received_at: str | None


def _b64url(raw: bytes) -> bytes:
    """Base64 without padding, which is how Svix encodes both the key and the signature."""
    return base64.urlsafe_b64decode(raw + b"=" * (-len(raw) % 4))


def verify_webhook(
    *,
    raw_body: bytes,
    headers: dict[str, str],
    secret: str | None,
    tolerance: int = TIMESTAMP_TOLERANCE_SECONDS,
    now: float | None = None,
) -> None:
    """Raise :class:`WebhookSignatureError` unless the request is a genuine, fresh delivery.

    ``headers`` keys are matched case-insensitively, because HTTP header names are and a framework
    may hand them through in any case.
    """
    if not secret:
        # A deployment fault rather than a bad signature, and reported as one: accepting unsigned
        # webhooks because none are configured is how this endpoint ends up public.
        raise WebhookSignatureError("no webhook signing secret is configured")

    lowered = {k.lower(): v for k, v in headers.items()}

    msg_id = lowered.get("svix-id")
    timestamp = lowered.get("svix-timestamp")
    signature = lowered.get("svix-signature")

    if not msg_id or not timestamp or not signature:
        raise WebhookSignatureError("missing svix-id, svix-timestamp or svix-signature")

    try:
        signed_at = int(timestamp)
    except ValueError as exc:
        raise WebhookSignatureError("svix-timestamp is not an integer") from exc

    current = time.time() if now is None else now
    if abs(current - signed_at) > tolerance:
        # The signature is mathematically valid; it is just old. A captured delivery would pass every
        # other check here, and this is the only thing that stops it being replayed.
        raise WebhookSignatureError("svix-timestamp is outside the tolerance window")

    # The key is the base64 after the `whsec_` prefix, not the whole string.
    key = secret.removeprefix("whsec_")
    try:
        key_bytes = _b64url(key.encode("utf-8"))
    except (ValueError, base64.binascii.Error) as exc:
        raise WebhookSignatureError("signing secret is not valid base64") from exc

    signed_content = f"{msg_id}.{timestamp}.".encode() + raw_body
    expected = hmac.new(key_bytes, signed_content, hashlib.sha256).digest()
    expected_b64 = base64.b64encode(expected).decode("ascii")

    # Several values may be present so a key can be rotated; any one matching is accepted, which is
    # what stops a rotation from dropping deliveries already in flight.
    for part in signature.split(" "):
        candidate = part.strip()
        if not candidate.startswith("v1,"):
            continue
        if hmac.compare_digest(candidate[3:], expected_b64):
            return

    raise WebhookSignatureError("no signature in the header matched the request body")


def _headers() -> dict[str, str]:
    if not settings.RESEND_API_KEY:
        raise EmailProviderError("RESEND_API_KEY is not configured")
    return {"Authorization": f"Bearer {settings.RESEND_API_KEY}"}


def _looks_like_address(value: str) -> bool:
    """A cheap sanity check that this is an address and not a stray word.

    ``parseaddr("not an address")`` returns ``('not',)`` as the *address* - it takes the last token
    it can and hands it back. Accepting that would store "not" as a guest's email address, create a
    session for it, and fail in the least obvious place later.

    Deliberately not full RFC 5322 validation, which nobody implements correctly and which rejects
    addresses that work. This only has to reject the obviously-not-one cases.
    """
    if value.count("@") != 1:
        return False
    local, _, domain = value.partition("@")
    return bool(local.strip()) and "." in domain and not domain.startswith(".") and " " not in value


def split_address(raw: str | None) -> tuple[str, str | None]:
    """Split ``"Amina Okello" <amina@example.com>`` into ``("amina@example.com", "Amina Okello")``.

    ``parseaddr`` rather than a regex because this string comes straight from a mail header and is
    genuinely gnarly - comments, nested quoting, unusual display names. The regex people write for
    this gets a surprising fraction of real addresses wrong, and the failure is silent: a mangled
    address becomes a session nobody can match a reply to.

    Note the order: ``parseaddr`` returns ``(name, address)``, not the other way round. Reading them
    the wrong way round is silent too - the result still *looks* like a tuple of two strings.

    Returns ``("", None)`` for anything unparseable, so the caller refuses rather than storing half
    an address.
    """
    if not raw:
        return "", None
    name, address = parseaddr(raw)
    address = address.strip()
    if not _looks_like_address(address):
        return "", None
    return address, (name.strip() or None)


async def fetch_email(email_id: str) -> InboundEmail | None:
    """Fetch one received email, including the body the webhook did not carry.

    The two-step shape is the provider's, not ours: the webhook has metadata only. Resolving it
    here means the rest of the codebase never learns that a message arrives in two pieces.

    Returns ``None`` when the provider has no such email, which is a real possibility rather than
    an error - the stored copy is retained for a limited period, and a replayed webhook can arrive
    after it has gone.
    """
    async with httpx.AsyncClient(timeout=15.0) as client:
        response = await client.get(
            f"{RESEND_API_BASE}/emails/receiving/{email_id}",
            headers=_headers(),
        )

    if response.status_code == 404:
        return None
    if response.status_code >= 400:
        raise EmailProviderError(f"could not fetch email {email_id}: HTTP {response.status_code}")

    body: dict[str, Any] = response.json()

    from_address, from_name = split_address(body.get("from"))

    # `received_for` names the addresses *on our domain* this was delivered for, and is the right
    # thing to route on: `to` also contains anyone the guest copied, and a guest who writes
    # `reservations@...` and CCs a friend must still reach the hotel rather than the friend. Falls
    # back to `to` for older payloads that do not carry it.
    received_for = body.get("received_for") or body.get("to") or []
    to_address, _ = split_address(received_for[0] if received_for else None)

    # The receiving API returns `text` and `html` - NOT `text_body` / `html_body`, which are the
    # names used by some other providers and which appear in Resend's own *blog* example because
    # that shows the webhook payload rather than this one. Reading the wrong pair yields an empty
    # body for every email ever sent, and the only symptom is that every message is quietly refused.
    # Both spellings are accepted so a rename cannot silently empty every transcript.
    #
    # Plain text preferred over HTML: the model reads prose, and HTML arrives full of markup and
    # tracking pixels that would otherwise be quoted at the model as though it were guest text.
    raw_text = body.get("text") or body.get("text_body") or ""
    if not raw_text.strip():
        html_body = body.get("html") or body.get("html_body")
        if html_body:
            raw_text = _html_to_text(html_body)

    # Imported here rather than at module scope: threading.py imports from this module for the
    # dataclass, and a module-level import in both directions is a cycle.
    from app.channels.email.threading import strip_quoted_reply

    return InboundEmail(
        email_id=email_id,
        to_address=to_address,
        from_address=from_address,
        from_name=from_name,
        subject=body.get("subject") or "",
        text=strip_quoted_reply(raw_text) or raw_text.strip(),
        raw_text=raw_text,
        message_id=body.get("message_id"),
        in_reply_to=body.get("in_reply_to"),
        references=body.get("references"),
        received_at=body.get("last_event") or body.get("created_at"),
    )


def _html_to_text(html: str) -> str:
    """A deliberately crude HTML-to-text, used only when an email has no plain part.

    Not a parser. Its job is to stop markup reaching the model as though the guest had typed it,
    and a tag-stripping pass does that well enough for a hotel enquiry. A real parser is a
    dependency and a security surface for input we did not write, which is a poor trade here.
    """
    import re

    text = re.sub(r"(?is)<(script|style)\b.*?</\1>", " ", html)
    text = re.sub(r"(?i)<br\s*/?>", "\n", text)
    text = re.sub(r"(?i)</p\s*>", "\n", text)
    text = re.sub(r"<[^>]+>", " ", text)
    text = (
        text.replace("&nbsp;", " ")
        .replace("&amp;", "&")
        .replace("&lt;", "<")
        .replace("&gt;", ">")
        .replace("&quot;", '"')
        .replace("&#39;", "'")
    )
    return re.sub(r"[ \t]{2,}", " ", text)


def build_payload(
    *,
    from_address: str,
    to_address: str,
    subject: str,
    text: str,
    html: str | None = None,
    reply_to_message_id: str | None = None,
    unsubscribe_url: str | None = None,
) -> dict[str, Any]:
    """The JSON body for one reply, separated from the HTTP call so the headers are testable.

    The opt-out headers are the reason this is a function. They are the only thing standing between
    an automated guest assistant and being indistinguishable from spam, and the only way they fail
    is silently - a missing header is not an error, it is just a lower score. Building them here
    means they can be asserted directly instead of by reading a live email's raw source.

    HTTPS only, no ``mailto:`` fallback. RFC 2369 allows either, but a mailto only works if a human
    reads that mailbox, and nothing reads ``unsubscribe@`` on a single-tenant platform. Offering a
    route that goes nowhere is worse than offering the one that works.

    ``html`` is an addition and never a replacement: ``text`` is always present. A client with images
    blocked, a screen reader, or a decade-old phone reads the text version, and some filters score
    plain text more favourably. ``html`` is omitted entirely when empty, so an unbranded project
    sends no empty HTML part.
    """
    payload: dict[str, Any] = {
        "from": from_address,
        "to": [to_address],
        "subject": subject,
        "text": text,
    }
    if html:
        payload["html"] = html
    headers: dict[str, str] = {}
    if reply_to_message_id:
        # Both are required for threading, not one or the other: In-Reply-To names the parent,
        # References the whole chain. Clients differ in which they read.
        headers["In-Reply-To"] = reply_to_message_id
        headers["References"] = reply_to_message_id
    if unsubscribe_url:
        headers["List-Unsubscribe"] = f"<{unsubscribe_url}>"
        # Only meaningful alongside an HTTPS URL, which is why it is not set independently: announcing
        # one-click with nothing to click invites clients to try and fail.
        headers["List-Unsubscribe-Post"] = "List-Unsubscribe=One-Click"
    if headers:
        payload["headers"] = headers
    return payload


async def send_reply(
    *,
    from_address: str,
    to_address: str,
    subject: str,
    text: str,
    html: str | None = None,
    reply_to_message_id: str | None = None,
    unsubscribe_url: str | None = None,
) -> str | None:
    """Send one reply. Returns the provider's message id.

    ``reply_to_message_id`` is what keeps the exchange in one thread, which is what a guest expects
    when they press Reply - and it is also what lets us recognise their next reply as a continuation
    rather than a fresh conversation.

    ``unsubscribe_url`` produces the RFC 2369/8058 opt-out headers. These are not a filter trick:
    they are the only honest way to offer a guest who does not want this mail a way to stop it, and
    Gmail now requires one from senders of automated mail.
    """
    payload = build_payload(
        from_address=from_address,
        to_address=to_address,
        subject=subject,
        text=text,
        html=html,
        reply_to_message_id=reply_to_message_id,
        unsubscribe_url=unsubscribe_url,
    )

    async with httpx.AsyncClient(timeout=15.0) as client:
        response = await client.post(f"{RESEND_API_BASE}/emails", headers=_headers(), json=payload)

    if response.status_code >= 400:
        # Provider bodies can echo guest content back; the status is enough and the detail is
        # logged rather than returned, so a failure cannot surface a guest's words in an error.
        logger.warning(
            "email: send rejected with %s", response.status_code, extra={"body": response.text[:300]}
        )
        raise EmailProviderError(f"send failed: HTTP {response.status_code}")

    try:
        return response.json().get("id")
    except ValueError:
        return None


__all__ = [
    "TIMESTAMP_TOLERANCE_SECONDS",
    "EmailProviderError",
    "InboundEmail",
    "WebhookSignatureError",
    "fetch_email",
    "send_reply",
    "split_address",
    "verify_webhook",
]