"""The WhatsApp Cloud API adapter (ADR-004).

Translation only: Meta's payload in, :class:`~app.channels.base.IncomingMessage` out. No tenant
resolution, no turn execution, no HTTP server - those belong to ``app.runtime`` and the endpoint, so
that a second channel cannot end up with a subtly different pipeline.

**Signature verification is not optional and is checked before anything else.** Meta authenticates
every webhook with ``X-Hub-Signature-256``: an HMAC-SHA256 of the **raw request bytes**, keyed on
the **app secret**, compared with ``compare_digest``. Three properties follow from that being
overlooked, and they are the reason this module exists rather than a five-line handler:

- **Raw bytes, not the parsed body.** Re-serialising the JSON to compute the digest fails on any
  difference in whitespace or key order, and fails *silently* - every request simply stops matching.
  The endpoint must hand this module the body before any JSON library has seen it.
- **The key is the app secret, not the tenant token.** A per-tenant key would make it impossible to
  authenticate a request before knowing which tenant sent it. That ordering constraint is the whole
  reason the app secret is a platform setting.
- **Fail closed.** An absent or unparseable signature is a refusal, never a pass. See
  :func:`verify_signature`.

.. warning::
   The signature scheme, the ``entry``/``changes`` envelope and the ``metadata`` block are
   implemented from the Cloud API reference and cross-checked against the summary at
   ``docs/WHATSAPP-CLOUD-API.md``. The offline brief that prompted this adapter documented the send
   endpoint, the ``hub.*`` handshake and the receive JSON *path* but **omitted signature
   verification, ``value.metadata`` and ``messages[].id`` entirely**. Those three are load-bearing
   here - without the first the endpoint is unauthenticated, without the second nothing can be
   routed, and without the third every provider retry duplicates a turn - so they are the parts to
   re-verify against Meta's live documentation before this handles production traffic.

**The envelope is iterated, never indexed.** The receive path is often written as
``entry[0].changes[0].value.messages[0]``, which is correct only when Meta sends exactly one message
per delivery. It does not: a batch carries many ``entry`` items, each with many ``changes``. Indexing
``[0]`` drops every message after the first with no error and no log, so a hotel silently stops
answering guests under load. :func:`parse_webhook` therefore returns a *list*.

**Groups are not guests.** A WhatsApp group id is ``<digits>-<digits>@g.us`` and a direct chat is
``...@c.us``. Group ids are rejected rather than stored, because an id ending in ``@g.us`` is not a
person: keyed like one it would create a single shared "guest" conversation merging every member's
messages, and the hotel would answer a room. ``IncomingMessage.is_addressed_to_us`` exists for the
same reason and the adapter fills the flag it reads.
"""

from __future__ import annotations

import hashlib
import hmac
import logging
from collections.abc import Iterator, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from app.channels.base import Channel, ChannelIdentity, IncomingMessage, normalize_external_id

logger = logging.getLogger("fussion.channels.whatsapp")

#: The header Meta signs with. Separate from the v1 header (`X-Hub-Signature`, sha1), which is
#: deprecated and must not be accepted as a fallback - sha1 is not what protects this endpoint.
SIGNATURE_HEADER = "X-Hub-Signature-256"
_SIGNATURE_PREFIX = "sha256="

#: WhatsApp suffix for a group conversation, as opposed to a direct one (``@c.us``). Rejected: see
#: the module docstring.
GROUP_SUFFIX = "@g.us"


class WebhookSignatureError(Exception):
    """The webhook signature was absent, malformed, or did not match.

    Distinct from a *parse* failure so the endpoint can answer 401 for one and 400 for the other -
    an unauthenticated caller must not be able to distinguish "your signature is wrong" from "your
    payload is malformed", since that difference is a free oracle for probing.
    """


@dataclass(frozen=True, slots=True)
class WhatsAppInbound:
    """One inbound WhatsApp text message, already flattened out of the envelope."""

    #: Meta's id for the *business* number. This - not the guest's number - is what identifies the
    #: tenant, and it is the value the send endpoint needs as ``{PHONE_NUMBER_ID}``.
    phone_number_id: str
    #: The business number as a human would write it, e.g. ``+256772123456``. Kept because
    #: registrations are claimed by number and this is the field to match on when no
    #: ``phone_number_id`` was recorded.
    display_phone_number: str | None
    #: The guest's ``wa_id`` - the external id the session is keyed by.
    wa_id: str
    #: Meta's ``wamid`` for this message. Written to ``Message.external_message_id`` so a provider
    #: retry resolves to the row already written rather than appending a second turn.
    message_id: str
    text: str
    timestamp: datetime | None
    display_name: str | None
    addressed_to_business: bool = True

    @property
    def is_group(self) -> bool:
        return self.wa_id.endswith(GROUP_SUFFIX)

    def to_incoming_message(self) -> IncomingMessage:
        """The channel-neutral shape the runtime takes.

        ``thread_id`` is left unset: a WhatsApp 1:1 chat *is* the thread, so there is nothing to
        disambiguate. A provider that later supplies conversation grouping can start populating it
        without a change here, and :func:`app.channels.sessions.get_or_create_session` already keys
        on it.
        """
        identity = ChannelIdentity(channel=Channel.WHATSAPP, external_id=self.wa_id, thread_id=None)
        return IncomingMessage(
            identity=identity,
            text=self.text,
            received_at=self.timestamp or datetime.now(UTC),
            message_id=self.message_id,
            display_name=self.display_name,
            metadata={
                "addressed_to_business": self.addressed_to_business,
                "phone_number_id": self.phone_number_id,
                "display_phone_number": self.display_phone_number,
                "wa_id": self.wa_id,
            },
        )


def verify_signature(*, raw_body: bytes, signature: str | None, app_secret: str | None) -> None:
    """Raise unless the signature matches. Raises :class:`WebhookSignatureError` otherwise.

    Returns ``None`` rather than a bool so a caller cannot forget to check it - a ``verify()`` that
    is true on success reads like a predicate and invites ``if not verify(...)``, which is fine,
    but the failure mode of ignoring the return entirely is worse than an exception.

    ``hmac.compare_digest`` rather than ``==``: it is not short-circuiting, so the time taken does
    not depend on how many leading characters matched.
    """
    if not app_secret:
        # Deliberately not a signature *mismatch*. No configured secret is a deployment fault, and
        # reporting it as one stops the endpoint being wired up and left open.
        raise WebhookSignatureError("no WhatsApp app secret is configured")

    if not signature:
        raise WebhookSignatureError("missing X-Hub-Signature-256 header")

    if not signature.startswith(_SIGNATURE_PREFIX):
        raise WebhookSignatureError("signature header is not sha256= prefixed")

    expected = hmac.new(app_secret.encode("utf-8"), raw_body, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(f"{_SIGNATURE_PREFIX}{expected}", signature):
        raise WebhookSignatureError("signature does not match the request body")


def _dig(node: Any, *path: str) -> Any:
    """Walk nested mappings, returning ``None`` rather than raising on a missing or non-dict step.

    Meta adds fields without notice and the payload is provider-controlled, so every path is
    treated as optional and a shape change degrades to "this message is not usable" instead of a
    500 on the webhook - which Meta would then retry forever.
    """
    current = node
    for key in path:
        if not isinstance(current, Mapping):
            return None
        current = current.get(key)
    return current


def _text_of(message: Mapping[str, Any]) -> str | None:
    """The text body of a message, or ``None`` if this message is not text.

    Only ``text`` is handled. Images, audio, documents, locations, contacts and reactions all
    arrive with the same envelope and are ignored rather than guessed at - a caption is not the
    same thing as a photo of a passport, and answering "thanks, got it" to the latter is worse than
    silence. Non-text handling is a product decision, not a parsing one.
    """
    if message.get("type") != "text":
        return None
    body = _dig(message, "text", "body")
    if not isinstance(body, str) or not body.strip():
        return None
    return body


def _epoch_to_datetime(value: Any) -> datetime | None:
    """Meta sends timestamps as a Unix epoch **string** in seconds.

    Handled as a string deliberately: ``int`` would accept ``"1699..."`` happily, but a float
    timestamp from a future or malformed payload would raise ``OverflowError``/``OSError`` inside
    ``fromtimestamp`` on some platforms, which is a 500 from provider-controlled input.
    """
    if not isinstance(value, str) or not value.isdigit():
        return None
    try:
        return datetime.fromtimestamp(int(value), tz=UTC)
    except (OverflowError, OSError, ValueError):  # pragma: no cover - defensive
        return None


def _iter_changes(payload: Mapping[str, Any]) -> Iterator[Mapping[str, Any]]:
    """Yield every ``value`` block in the envelope, across all entries and all changes.

    The load-bearing loop of this module. See the module docstring for why ``entry[0]`` is wrong.
    """
    entries = payload.get("entry")
    if not isinstance(entries, Sequence) or isinstance(entries, (str, bytes)):
        return
    for entry in entries:
        if not isinstance(entry, Mapping):
            continue
        changes = entry.get("changes")
        if not isinstance(changes, Sequence) or isinstance(changes, (str, bytes)):
            continue
        for change in changes:
            if not isinstance(change, Mapping):
                continue
            value = change.get("value")
            if isinstance(value, Mapping):
                yield value


def _contact_name(value: Mapping[str, Any], wa_id: str) -> str | None:
    """The guest's profile name, which ``contacts`` holds *beside* rather than inside the message.

    The block is positional - ``contacts[0]`` corresponds to ``messages[0]`` - so it is matched on
    ``wa_id`` instead. Positional matching breaks the moment Meta sends two messages from
    different guests in one batch, which is exactly what happens when a booking channel is busy.
    """
    contacts = value.get("contacts")
    if not isinstance(contacts, Sequence) or isinstance(contacts, (str, bytes)):
        return None
    for contact in contacts:
        if not isinstance(contact, Mapping):
            continue
        if contact.get("wa_id") != wa_id:
            continue
        name = _dig(contact, "profile", "name")
        if isinstance(name, str) and name.strip():
            return name.strip()
    return None


def parse_webhook(payload: Mapping[str, Any]) -> list[WhatsAppInbound]:
    """Every usable inbound text message in the payload, in order.

    Returns an empty list for a payload carrying no text - a status update, an image, or a
    verification ping. The caller treats that as success: it is a valid delivery that simply has
    nothing to answer, and answering it with an error would have Meta retry it.
    """
    inbound: list[WhatsAppInbound] = []

    for value in _iter_changes(payload):
        # The business identity. Without it there is nothing to route on, so the whole change is
        # unusable - see the module docstring. `metadata` is where it lives; the top-level fallback
        # is not part of the documented shape and is deliberately not consulted, so a malformed
        # payload cannot spoof a tenant by putting the id somewhere unexpected.
        phone_number_id = _dig(value, "metadata", "phone_number_id")
        display_phone_number = _dig(value, "metadata", "display_phone_number")
        if not isinstance(phone_number_id, str) or not phone_number_id:
            logger.warning("whatsapp: change with no phone_number_id, skipping")
            continue

        messages = value.get("messages")
        if not isinstance(messages, Sequence) or isinstance(messages, (str, bytes)):
            continue

        for message in messages:
            if not isinstance(message, Mapping):
                continue
            wa_id = message.get("from")
            message_id = message.get("id")
            if not isinstance(wa_id, str) or not wa_id or not isinstance(message_id, str):
                continue
            text = _text_of(message)
            if text is None:
                continue

            is_group = wa_id.endswith(GROUP_SUFFIX)
            if is_group:
                logger.info("whatsapp: ignoring group message %s", message_id)

            inbound.append(
                WhatsAppInbound(
                    phone_number_id=phone_number_id,
                    display_phone_number=(
                        display_phone_number if isinstance(display_phone_number, str) else None
                    ),
                    wa_id=normalize_external_id(Channel.WHATSAPP, wa_id),
                    message_id=message_id,
                    text=text,
                    timestamp=_epoch_to_datetime(message.get("timestamp")),
                    display_name=_contact_name(value, wa_id),
                    addressed_to_business=not is_group,
                )
            )

    return inbound


__all__ = [
    "SIGNATURE_HEADER",
    "WebhookSignatureError",
    "WhatsAppInbound",
    "parse_webhook",
    "verify_signature",
]