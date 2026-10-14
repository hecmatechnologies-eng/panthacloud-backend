"""The internal message shape every channel speaks (ADR-004).

A channel adapter's whole job is translation, and translation needs a fixed shape to translate
*into*. Without one, each adapter would call the turn path with its own arguments and the first
divergence — one channel forgetting to pass a tenant, another skipping the guard — would be a bug
per channel rather than one bug in one place.

Three things this deliberately is **not**:

- **Not a channel implementation.** No webhook handling, no provider SDK, no HTTP. An adapter for
  WhatsApp or Telegram lives beside the model this file defines and converts to it.
- **Not a send function.** Delivery is the adapter's, per ADR-004: the widget streams with the lagged
  guard, everything else sends one complete message. Sending from here would put the delivery rules
  in the wrong layer and make the guarded path optional.
- **Not a tenant resolution mechanism.** ``ChannelIdentity`` is a *lookup result*, not a resolver.
  Resolving a phone number to an organisation is deliberately left to the adapter, because the
  evidence available differs per channel and only the adapter knows it.

**On identity.** ``external_id`` is whatever the provider calls the person: a WhatsApp wa_id, a
Telegram chat id, an email address. It is opaque here and never parsed. The temptation to treat a
phone number or an email as structured data is exactly the assumption that breaks when a provider
changes its format — a Telegram chat id is not a phone number, and a group id is neither.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum


class Channel(str, Enum):
    """Where a conversation came from and where the answer goes.

    Values are stored, so renaming one is a migration. ``web`` is the widget and maps onto an
    existing ``WebsiteIntegration``; the rest are org-level ``Channel`` rows.
    """

    WEB = "web"
    WHATSAPP = "whatsapp"
    TELEGRAM = "telegram"
    EMAIL = "email"
    SMS = "sms"


@dataclass(frozen=True, slots=True)
class ChannelIdentity:
    """Who is speaking, on which channel, and where the conversation already lives.

    ``external_id`` is opaque and provider-specific. ``thread_id`` separates distinct conversations
    with the same person - a WhatsApp message and an email from one guest must not share history,
    and on some channels the provider supplies the grouping while on others it must be derived.
    """

    channel: Channel
    external_id: str
    thread_id: str | None = None

    def key(self) -> tuple[str, str, str | None]:
        """The tuple a session is scoped by.

        Normalised defensively: WhatsApp wa_ids arrive with and without a leading '+', and the same
        person messaging from two numbers must not become two people.
        """
        return (
            self.channel.value,
            self.external_id.strip().lstrip("+"),
            self.thread_id.strip() if self.thread_id else None,
        )


@dataclass(frozen=True, slots=True)
class IncomingMessage:
    """One inbound turn, normalised.

    ``message_id`` is the provider's own identifier when it has one, used to make webhook delivery
    idempotent: providers retry, and answering a guest twice because their first request was
    retried is the kind of bug a customer notices before you do.
    """

    identity: ChannelIdentity
    text: str
    received_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    message_id: str | None = None
    display_name: str | None = None
    metadata: Mapping[str, object] = field(default_factory=dict)

    @property
    def is_addressed_to_us(self) -> bool:
        """False for a group message the business is not the subject of.

        Guests writing in a WhatsApp group talk to each other, not to the hotel. Treating that as a
        turn would have the assistant answering conversations it was not invited into, so the
        adapter sets this and the runtime honours it.
        """
        if self.identity.channel is not Channel.WHATSAPP:
            return True
        explicit = self.metadata.get("addressed_to_business")
        return bool(explicit) if explicit is not None else True


def message_key(inbound: IncomingMessage) -> tuple[str, str, str | None]:
    """The stable key for "this conversation", across a provider's retry of the same message."""
    return inbound.identity.key()


__all__ = [
    "Channel",
    "ChannelIdentity",
    "IncomingMessage",
    "message_key",
]