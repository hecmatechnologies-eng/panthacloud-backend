"""Runtime chat pipeline (step B4/B5/B6): resolve tenant → rate limit → session → persist →
retrieve → assemble → model → persist reply.

The pipeline lives here rather than in the endpoint so it is testable without HTTP, and the
endpoint stays a thin adapter over the refusal/limit mapping.
"""

import hashlib
import logging
import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.channels.base import Channel, ChannelIdentity
from app.channels.sessions import get_or_create_session
from app.core.config import settings
from app.core.database import get_session_factory
from app.core.prompting import fence_untrusted

logger = logging.getLogger("fussion.runtime.chat")
from app.guardrails import redact_outbound
from app.guardrails.stream import guard_stream
from app.llm.base import (
    ModelDelta,
    ModelMessage,
    ModelRequest,
    StreamDone,
    Usage,
)
from app.llm.gateway import ModelGateway, UsageContext, get_model_gateway
from app.models.assistant import Assistant
from app.models.base import utc_now
from app.models.conversation import (
    Conversation,
    Message,
    MessageDirection,
    MessageRole,
    MessageStatus,
    VisitorSession,
)
from app.models.knowledge import KnowledgeBase
from app.runtime.assistant import CustomerAssistant, resolve_customer_assistant
from app.runtime.rate_limit import rate_limiter
from app.runtime.resolver import TenantContext, resolve_tenant
from app.schemas.knowledge import KnowledgeQueryRequest, KnowledgeQueryResultItem
from app.services.knowledge.retrieval import query_knowledge_base
from app.services.model_settings import effective_model_id


class AssistantDisabledError(Exception):
    """The tenant has switched their assistant off; the runtime must not answer."""


@dataclass(frozen=True, slots=True)
class ChatReply:
    session_id: uuid.UUID
    conversation_id: uuid.UUID
    reply: str
    citations: tuple[dict[str, Any], ...] = ()


async def _persist_inbound(
    db: AsyncSession,
    *,
    conversation_id: uuid.UUID,
    content: str,
    message_id: str | None,
) -> None:
    """Write the guest's turn, absorbing a provider retry.

    Returns silently when ``message_id`` has already been written, because a retry is not an error -
    it is the same message arriving twice, and the right response is to carry on and let the caller
    answer as it would have anyway. The webhook acknowledges either way; what must not happen is the
    guest's transcript gaining a second copy of the same sentence.

    The uniqueness is enforced by ``uq_message_external_id``, and the race is handled with a
    savepoint for the same reason ``app.channels.sessions`` does: a bare rollback would discard the
    session and conversation rows this turn just created.
    """
    row = Message(
        conversation_id=conversation_id,
        role=MessageRole.VISITOR,
        direction=MessageDirection.INBOUND,
        # No status: a guest's message has no delivery lifecycle, and writing SENT here would be
        # a fiction every status query would then have to special-case.
        content=content,
        external_message_id=message_id,
    )

    if message_id is None:
        db.add(row)
        # Flush before assembling the prompt, so the history includes the visitor's current turn.
        await db.flush()
        return

    try:
        async with db.begin_nested():
            db.add(row)
            await db.flush()
    except IntegrityError:
        logger.info(
            "channel: duplicate delivery %s already answered; not writing it twice", message_id
        )


@dataclass(frozen=True, slots=True)
class PreparedTurn:
    """A turn that is persisted and assembled, and has not called the model yet.

    Everything here is done before a stream starts, so the streaming path can commit and release
    its session before the first token (FR-118).
    """

    session_id: uuid.UUID
    conversation_id: uuid.UUID
    organization_id: uuid.UUID
    project_id: uuid.UUID
    #: ``None`` for a channel turn, which has no widget behind it. Already optional on
    #: ``UsageContext``, so the gateway's own usage rows were ready for this.
    integration_id: uuid.UUID | None
    request: ModelRequest
    citations: tuple[dict[str, Any], ...]
    # Which definition produced this turn, so the answer can be attributed after the fact even if
    # the business edits its instructions later (B9).
    assistant_version: str
    prompt_hash: str


@dataclass(frozen=True, slots=True)
class ChatStreamStart:
    """First event: the visitor's turn is committed and the prompt is assembled."""

    session_id: uuid.UUID
    conversation_id: uuid.UUID
    citations: tuple[dict[str, Any], ...]


@dataclass(frozen=True, slots=True)
class ChatStreamDelta:
    text: str


@dataclass(frozen=True, slots=True)
class ChatStreamEnd:
    """Last event: the reply is persisted and the usage is on the ledger."""

    model: str
    usage: Usage


ChatStreamEvent = ChatStreamStart | ChatStreamDelta | ChatStreamEnd


@dataclass(frozen=True, slots=True)
class WidgetTurn:
    """A turn from the embedded widget.

    The session is named by a client-supplied id, which is untrusted and therefore re-checked
    against the project and origin on every turn rather than believed.
    """

    ctx: TenantContext
    #: ``None`` for a first-time visitor, which is not an error - it means a new session.
    session_id: uuid.UUID | None = None


@dataclass(frozen=True, slots=True)
class ChannelTurn:
    """A turn from a messaging channel (ADR-004).

    The session is found by the speaker's identity alone: there is no client-supplied id to trust,
    and none is wanted, because the identity *is* the addressing. Resolved through
    ``app.channels.sessions``, which is keyed on the unique index rather than on trust.

    The inbound provider message id is deliberately not carried here yet. Webhook delivery is
    retried by every provider, so the inbound row wants ``Message.external_message_id`` - and the
    existing unique constraint on it means a retried delivery has to be caught at the point this
    module writes the row, not in the adapter. Adding the field without that handling would turn a
    duplicate delivery into an IntegrityError and a 500. It lands with the first adapter.
    """

    ctx: TenantContext
    identity: ChannelIdentity
    #: The provider's own id for this message (``wamid.XXXX``), when the channel has one.
    #:
    #: Written to ``Message.external_message_id``, whose partial unique index is what makes webhook
    #: delivery idempotent. Every provider retries - a timeout is ambiguous from Meta's side - so
    #: without this a retried delivery appends a second copy of the same turn to the guest's
    #: transcript, and the guest sees themselves answered twice.
    #:
    #: The duplicate is caught in :func:`_persist_inbound` rather than in the adapter: the index is
    #: the authority, and an adapter that pre-checked "have I seen this id?" would race with a
    #: concurrent retry and both would write. Rescoped from "the first adapter" - see the WhatsApp
    #: webhook.
    message_id: str | None = None


#: Where a turn came from, which decides how it resolves to a session and what it is bounded by.
#: A union rather than two sets of optional arguments, so a caller cannot supply half of each shape
#: and get a turn that is neither.
TurnSource = WidgetTurn | ChannelTurn


async def _shed_by_ip(client_ip: str | None) -> None:
    """The caller's address, bounded before anything else is touched.

    Applied ahead of tenancy resolution on purpose: a flood from one address should cost a Redis
    round trip, not a database lookup and not a session insert. Shared by every entry point so that
    adding a channel cannot quietly skip the cheapest bound there is.
    """
    if client_ip:
        await rate_limiter.check(
            "ip",
            client_ip,
            settings.PUBLIC_CHAT_RATE_LIMIT_PER_IP,
            settings.PUBLIC_CHAT_RATE_LIMIT_WINDOW_SECONDS,
        )


async def handle_chat(
    db: AsyncSession,
    *,
    public_key: str | None,
    origin: str | None,
    session_id: uuid.UUID | None,
    message: str,
    client_ip: str | None,
) -> ChatReply:
    """One chat turn. Raises ``TenantResolutionError`` or ``RateLimitExceeded``; never returns a
    reply to a caller that is not entitled to one."""
    await _shed_by_ip(client_ip)
    ctx = await resolve_tenant(db, public_key, origin)
    return await complete_turn(
        db,
        source=WidgetTurn(ctx=ctx, session_id=session_id),
        message=message,
    )


async def handle_channel_message(
    db: AsyncSession,
    *,
    ctx: TenantContext,
    identity: ChannelIdentity,
    message: str,
    client_ip: str | None,
    message_id: str | None = None,
) -> ChatReply:
    """One turn from a messaging channel.

    There is no streaming variant, and that is the decision rather than the omission (ADR-004):
    streaming is a property of the channel, not of the assistant. The widget streams to a browser
    that renders tokens as they arrive; WhatsApp, email, Telegram and SMS each take one complete
    message. Adding a streaming path here would mean holding a database session open for the length
    of a generation on a transport that cannot use it, and would let a channel adapter reach the
    token stream *around* the lagged guard in ``app.guardrails.stream`` - which exists precisely to
    hold back a prefix so a partial stream cannot leak what a complete one would be redacted for.

    ``ctx`` is taken resolved rather than resolved here because a channel has no public key and no
    origin: the caller has already matched the speaker to a project by whatever that channel
    addresses by. Everything after that - rate limits, session resolution, persistence, retrieval,
    the model, and the outbound PII guard - is the same pipeline the widget runs. That is the point
    of putting this here instead of in the adapter.
    """
    await _shed_by_ip(client_ip)
    return await complete_turn(
        db,
        source=ChannelTurn(ctx=ctx, identity=identity, message_id=message_id),
        message=message,
    )


async def complete_turn(
    db: AsyncSession,
    *,
    source: TurnSource,
    message: str,
) -> ChatReply:
    """Run one turn end to end against an already-resolved tenant.

    The single completion path for every channel as well as the widget's JSON endpoint, so that the
    bounds, the persistence and the outbound guard cannot drift apart per entry point. The IP shed
    is not here because it must happen *before* tenancy is resolved; each entry point does it.
    """
    prepared = await _prepare_turn(db, source=source, message=message)

    gateway = get_model_gateway()
    response = await gateway.complete(
        db,
        prepared.request,
        UsageContext(
            organization_id=prepared.organization_id,
            project_id=prepared.project_id,
            integration_id=prepared.integration_id,
            conversation_id=prepared.conversation_id,
        ),
    )
    reply = _guard_reply(response.text, prepared)
    _persist_reply(db, prepared, reply)
    await db.flush()

    return ChatReply(
        session_id=prepared.session_id,
        conversation_id=prepared.conversation_id,
        reply=reply,
        citations=prepared.citations,
    )


async def start_chat_stream(
    *,
    public_key: str | None,
    origin: str | None,
    session_id: uuid.UUID | None,
    message: str,
    client_ip: str | None,
) -> AsyncIterator[ChatStreamEvent]:
    """Prepare a streamed turn and return the iterator that yields its events.

    Widget only. A channel takes one complete message; see :func:`handle_channel_message`.

    Deliberately a coroutine rather than an async generator: the preparation — tenancy, rate
    limits, persistence, budget — must run, and be able to **raise**, while the caller can still
    answer with a real HTTP status, before any part of the response has been sent.

    It manages its own sessions: the visitor's turn is persisted and **committed before the first
    token**, and the reply and usage are written in a second, short-lived session **after the
    last**. Nothing holds a database session open across the stream (FR-118, CLAUDE.md §3.6) — the
    failure that leaked the pool in the Studio's own feed.
    """
    session_factory = get_session_factory()
    gateway = get_model_gateway()

    async with session_factory() as db:
        await _shed_by_ip(client_ip)
        ctx = await resolve_tenant(db, public_key, origin)
        prepared = await _prepare_turn(
            db,
            source=WidgetTurn(ctx=ctx, session_id=session_id),
            message=message,
        )
        # `complete` checks the budget itself; `stream` cannot without a session, so the caller
        # does it here — before any token is paid for.
        await gateway.ensure_budget(db, prepared.organization_id)
        await db.commit()

    return _stream_events(session_factory, gateway, prepared)


async def _stream_events(
    session_factory: async_sessionmaker[AsyncSession],
    gateway: ModelGateway,
    prepared: PreparedTurn,
) -> AsyncIterator[ChatStreamEvent]:
    yield ChatStreamStart(
        session_id=prepared.session_id,
        conversation_id=prepared.conversation_id,
        citations=prepared.citations,
    )

    parts: list[str] = []
    done: StreamDone | None = None
    # The outbound guardrail, lagged: a streamed delta cannot be retracted, so the risky window is
    # held back rather than checked after sending. `allowed` is the composed turn, so a value the
    # guest supplied and the assistant is quoting back is not mangled.
    allowed = prepared.request.messages[-1].content if prepared.request.messages else ""
    async for event in guard_stream(gateway.stream(prepared.request), allowed=allowed):
        if isinstance(event, StreamDone):
            done = event
        elif isinstance(event, ModelDelta):
            parts.append(event.text)
            yield ChatStreamDelta(text=event.text)

    reply = done.text if done is not None else "".join(parts)

    async with session_factory() as db:
        _persist_reply(db, prepared, reply)
        if done is not None:
            # The ledger write the gateway could not do: the same seam the agent adapter uses.
            await gateway.record_external_usage(
                db,
                organization_id=prepared.organization_id,
                provider=done.provider,
                model=done.model,
                input_tokens=done.usage.input_tokens,
                output_tokens=done.usage.output_tokens,
                project_id=prepared.project_id,
                integration_id=prepared.integration_id,
                conversation_id=prepared.conversation_id,
            )
        await db.commit()

    yield ChatStreamEnd(
        model=done.model if done is not None else prepared.request.model,
        usage=done.usage if done is not None else Usage(input_tokens=0, output_tokens=0),
    )


async def _prepare_turn(
    db: AsyncSession,
    *,
    source: TurnSource,
    message: str,
) -> PreparedTurn:
    """Rate limit, persist the visitor's turn, and assemble the prompt.

    Shared by the JSON and streaming paths, so both enforce the same bounds and build the same
    context; only the model call differs. Takes tenancy already resolved, because a channel has no
    public key to resolve it from.
    """
    window = settings.PUBLIC_CHAT_RATE_LIMIT_WINDOW_SECONDS
    ctx = source.ctx

    # These scopes are server-derived and cannot be reset by the caller. The widget is bounded per
    # integration, because that is what a public key names. A channel has no integration, so it is
    # bounded per project - the tenancy anchor, and the same granularity (one site, or one
    # business). Without that branch this would stringify None and put every channel tenant into a
    # single shared bucket, which is not a limit.
    if ctx.integration_id is not None:
        await rate_limiter.check(
            "integration",
            str(ctx.integration_id),
            settings.PUBLIC_CHAT_RATE_LIMIT_PER_INTEGRATION,
            window,
        )
    else:
        await rate_limiter.check(
            "project",
            str(ctx.project_id),
            settings.PUBLIC_CHAT_RATE_LIMIT_PER_INTEGRATION,
            window,
        )
    await rate_limiter.check(
        "organization",
        str(ctx.organization_id),
        settings.PUBLIC_CHAT_RATE_LIMIT_PER_ORGANIZATION,
        window,
    )

    session, conversation = await _resolve_or_create_session(db, source)

    # Session scope governs how many turns one resumed session may take. It is *not* an abuse
    # boundary: on the widget there is no server-set cookie, so a caller that omits or fabricates
    # session_id gets a fresh session (and a fresh counter) every time. The enforceable bounds are
    # the IP, integration/project and organization scopes above. A conversation scope is deferred
    # with B5's usage accounting — one conversation per session at MVP, so it would duplicate this.
    await rate_limiter.check(
        "session",
        str(session.id),
        settings.PUBLIC_CHAT_RATE_LIMIT_PER_SESSION,
        window,
    )

    await _persist_inbound(
        db,
        conversation_id=conversation.id,
        content=message,
        message_id=getattr(source, "message_id", None),
    )
    # Flush before assembling the prompt, so the history includes the visitor's current turn.
    await db.flush()

    request, citations, assistant = await _assemble_request(db, ctx, conversation)
    return PreparedTurn(
        session_id=session.id,
        conversation_id=conversation.id,
        organization_id=ctx.organization_id,
        project_id=ctx.project_id,
        integration_id=ctx.integration_id,
        request=request,
        citations=tuple(citations),
        assistant_version=assistant.version,
        prompt_hash=_instructions_hash(assistant.instructions),
    )


def _guard_reply(reply: str, prepared: PreparedTurn) -> str:
    """The outbound guardrail, applied to a completed turn.

    Redacts PII the model produced that it could only have *invented*: the context it was shown is
    the allow-list, so a value the guest supplied and the assistant is quoting back survives,
    because redacting that would break the answer and read to the guest as a fault. This is the
    first output-side check the runtime has — the input side has been fenced since the beginning,
    but nothing inspected what came back.

    **Known gap: streaming is not guarded here.** `_stream_events` yields deltas as the provider
    produces them, and a redacted string cannot un-send one. The streamed copy is therefore
    unredacted even though the persisted copy is not. Redacting mid-stream needs the match buffered
    until the span closes, which trades the first-token latency advantage for correctness; that is a
    deliberate change to make when streaming is the dominant path rather than here, where it would
    be an unflagged half-measure.
    """
    allowed = prepared.request.messages[-1].content if prepared.request.messages else ""
    return redact_outbound(reply, allowed=allowed)


def _persist_reply(db: AsyncSession, prepared: PreparedTurn, reply: str) -> None:
    db.add(
        Message(
            conversation_id=prepared.conversation_id,
            role=MessageRole.ASSISTANT,
            direction=MessageDirection.OUTBOUND,
            # Inserted in the same request that produced it, so it is sent by definition. DRAFTED
            # and AWAITING_APPROVAL belong to K5's approval gate, which does not exist yet - and
            # claiming either here would be a state this row never passed through.
            status=MessageStatus.SENT,
            content=reply,
            citations=list(prepared.citations),
            assistant_version=prepared.assistant_version,
            prompt_hash=prepared.prompt_hash,
        )
    )


def _instructions_hash(instructions: str) -> str:
    """Fingerprint the instruction layer that was actually sent.

    Not the model's whole input: the retrieved context and the question change every turn, and a
    hash that changes every turn identifies nothing. The instructions are the stable part, and the
    part a business edits.
    """
    return hashlib.sha256(instructions.encode("utf-8")).hexdigest()


async def _resolve_or_create_session(
    db: AsyncSession, source: TurnSource
) -> tuple[VisitorSession, Conversation]:
    """Find the session this turn belongs to, and its conversation.

    The two sources resolve differently because what they can trust differs. A widget names its
    session with a client-supplied id, which is checked rather than believed. A channel names its
    session with the speaker's identity, which is addressing rather than a claim.
    """
    if isinstance(source, ChannelTurn):
        found = await get_or_create_session(
            db, project_id=source.ctx.project_id, identity=source.identity
        )
        return await _conversation_for(db, found.session)

    return await _resolve_widget_session(db, source.ctx, source.session_id)


async def _resolve_widget_session(
    db: AsyncSession, ctx: TenantContext, session_id: uuid.UUID | None
) -> tuple[VisitorSession, Conversation]:
    """Reuse a live session that belongs to this project, else start a new one.

    A session id that is unknown, expired, or belongs to another project is not an error: the caller
    gets a fresh session. Tenancy was already decided by the resolver, so this can never cross
    tenants — it only declines to trust a client-supplied id.

    Scoped by ``project_id`` rather than ``integration_id``. Both were once the same test and the
    widget's origin was the third condition; scoping by project keeps the tenant boundary while
    letting a session exist without a widget, which is what every non-web channel needs.

    The origin check stays, and is now widget-only by construction: a session with no integration
    has no origin to compare, so it is exempt. That is the intended behaviour, not a loophole —
    an origin only ever identified a browser, and a phone number has none.
    """
    if session_id is not None:
        session = (
            await db.execute(
                select(VisitorSession).where(
                    VisitorSession.id == session_id,
                    VisitorSession.project_id == ctx.project_id,
                )
            )
        ).scalar_one_or_none()
        if (
            session is not None
            and not _is_expired(session.expires_at)
            and (session.origin is None or session.origin == ctx.origin)
        ):
            return await _conversation_for(db, session)

    session = VisitorSession(
        project_id=ctx.project_id,
        integration_id=ctx.integration_id,
        channel=Channel.WEB,
        origin=ctx.origin,
        expires_at=utc_now() + timedelta(hours=settings.PUBLIC_SESSION_TTL_HOURS),
    )
    db.add(session)
    await db.flush()
    return await _conversation_for(db, session)


async def _conversation_for(
    db: AsyncSession, session: VisitorSession
) -> tuple[VisitorSession, Conversation]:
    """This session's current conversation, opening one if the session has none yet.

    A session outlives its conversations - a guest can lapse and come back, and the session is
    revived rather than replaced - so "latest or new" is the normal case for every turn after a
    lapse, not an edge case.
    """
    conversation = await _latest_conversation(db, session.id)
    if conversation is None:
        conversation = _new_conversation(session.id)
        db.add(conversation)
        await db.flush()
    return session, conversation


def _new_conversation(session_id: uuid.UUID) -> Conversation:
    return Conversation(
        session_id=session_id,
        retention_expires_at=utc_now()
        + timedelta(days=settings.PUBLIC_CONVERSATION_RETENTION_DAYS),
    )


async def _latest_conversation(db: AsyncSession, session_id: uuid.UUID) -> Conversation | None:
    stmt = (
        select(Conversation)
        .where(Conversation.session_id == session_id)
        .order_by(Conversation.created_at.desc(), Conversation.id.desc())
        .limit(1)
    )
    return (await db.execute(stmt)).scalar_one_or_none()


async def _assemble_request(
    db: AsyncSession, ctx: TenantContext, conversation: Conversation
) -> tuple[ModelRequest, list[dict[str, Any]], CustomerAssistant]:
    """Assemble one turn's prompt, without calling the model.

    The system prompt is the trusted instruction region, and it is the *definition's* — resolved
    from the tenant's configuration, with the platform's grounding layer always present
    (`resolve_customer_assistant`). Retrieved knowledge is fenced as labelled data inside the final
    user turn, never concatenated into the instruction region (FR-098).
    """
    assistant_row = await _load_assistant(db, ctx.project_id)
    if assistant_row is not None and not assistant_row.is_enabled:
        raise AssistantDisabledError()

    assistant = resolve_customer_assistant(assistant_row)

    history = await _load_history(db, conversation.id, settings.MODEL_HISTORY_MAX_MESSAGES)
    question, prior_turns = _split_question(history)

    retrieved = await _retrieve(db, ctx.project_id, question)
    citations = [_citation(item) for item in retrieved]

    messages = [ModelMessage(role="system", content=assistant.instructions)]
    messages += [
        ModelMessage(
            role="user" if message.role == MessageRole.VISITOR else "assistant",
            content=message.content,
        )
        for message in prior_turns
    ]
    messages.append(ModelMessage(role="user", content=_compose_user_turn(question, retrieved)))

    request = ModelRequest(
        model=await effective_model_id(db, ctx.organization_id),
        messages=messages,
        max_output_tokens=assistant.max_output_tokens,
    )
    return request, citations, assistant


def _split_question(history: list[Message]) -> tuple[str, list[Message]]:
    """The current visitor turn is the last row (flushed just before this runs)."""
    if not history:
        return "", []
    return history[-1].content, history[:-1]


async def _retrieve(
    db: AsyncSession, project_id: uuid.UUID, question: str
) -> list[KnowledgeQueryResultItem]:
    """Tenant-filtered retrieval (FR-109). No knowledge base means no context, not an error."""
    kb = (
        await db.execute(select(KnowledgeBase).where(KnowledgeBase.project_id == project_id))
    ).scalar_one_or_none()
    if kb is None or not question.strip():
        return []
    response = await query_knowledge_base(
        db,
        kb,
        KnowledgeQueryRequest(
            query=question,
            top_k=settings.RETRIEVAL_TOP_K,
            score_threshold=settings.RETRIEVAL_SCORE_THRESHOLD,
        ),
    )
    return list(response.results)


def _citation(item: KnowledgeQueryResultItem) -> dict[str, Any]:
    return {
        "document_id": str(item.document_id),
        "filename": item.document_filename,
        "chunk_index": item.chunk_index,
        "page_number": item.page_number,
        "score": item.score,
    }


def _compose_user_turn(question: str, retrieved: list[KnowledgeQueryResultItem]) -> str:
    if not retrieved:
        return (
            f"QUESTION: {question}\n\n"
            "No knowledge base context is available for this question."
        )
    lines = [
        fence_untrusted(
            "\n".join(
                f"[{index}] {item.document_filename} (chunk {item.chunk_index}): {item.text}"
                for index, item in enumerate(retrieved, start=1)
            ),
            source="retrieved knowledge base",
            purpose=(
                "The only material you may answer from. Quote from it, cite it, and when it "
                "does not contain the answer, say so."
            ),
        )
    ]
    lines.append("")
    lines.append(f"QUESTION: {question}")
    return "\n".join(lines)


async def _load_assistant(db: AsyncSession, project_id: uuid.UUID) -> Assistant | None:
    stmt = select(Assistant).where(Assistant.project_id == project_id)
    return (await db.execute(stmt)).scalar_one_or_none()


async def _load_history(
    db: AsyncSession, conversation_id: uuid.UUID, limit: int
) -> list[Message]:
    """The most recent turns, returned oldest-first. Bounded so the context cap is not a surprise."""
    stmt = (
        select(Message)
        .where(Message.conversation_id == conversation_id)
        .order_by(Message.created_at.desc(), Message.id.desc())
        .limit(limit)
    )
    rows = list((await db.execute(stmt)).scalars().all())
    rows.reverse()
    return rows


def _is_expired(value: datetime) -> bool:
    # SQLite returns a naive datetime for a timezone-aware column; normalise before comparing.
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value <= utc_now()
