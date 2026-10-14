"""Runtime chat pipeline (step B4/B5/B6): resolve tenant → rate limit → session → persist →
retrieve → assemble → model → persist reply.

The pipeline lives here rather than in the endpoint so it is testable without HTTP, and the
endpoint stays a thin adapter over the refusal/limit mapping.
"""

import hashlib
import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.channels.base import Channel
from app.core.config import settings
from app.core.database import get_session_factory
from app.core.prompting import fence_untrusted
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
    integration_id: uuid.UUID
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
    prepared = await _prepare_turn(
        db,
        public_key=public_key,
        origin=origin,
        session_id=session_id,
        message=message,
        client_ip=client_ip,
    )

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
        prepared = await _prepare_turn(
            db,
            public_key=public_key,
            origin=origin,
            session_id=session_id,
            message=message,
            client_ip=client_ip,
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
    public_key: str | None,
    origin: str | None,
    session_id: uuid.UUID | None,
    message: str,
    client_ip: str | None,
) -> PreparedTurn:
    """Rate limit, resolve the tenant, persist the visitor's turn, and assemble the prompt.

    Shared by the JSON and streaming paths, so both enforce the same bounds and build the same
    context; only the model call differs.
    """
    window = settings.PUBLIC_CHAT_RATE_LIMIT_WINDOW_SECONDS
    # IP first: it is the cheapest shed, and it does not require the tenant to be known yet.
    if client_ip:
        await rate_limiter.check("ip", client_ip, settings.PUBLIC_CHAT_RATE_LIMIT_PER_IP, window)

    ctx = await resolve_tenant(db, public_key, origin)

    # IP, integration and organization are all server-derived and cannot be reset by the caller.
    await rate_limiter.check(
        "integration",
        str(ctx.integration_id),
        settings.PUBLIC_CHAT_RATE_LIMIT_PER_INTEGRATION,
        window,
    )
    await rate_limiter.check(
        "organization",
        str(ctx.organization_id),
        settings.PUBLIC_CHAT_RATE_LIMIT_PER_ORGANIZATION,
        window,
    )

    session, conversation = await _resolve_or_create_session(db, ctx, session_id)

    # Session scope governs how many turns one resumed session may take. It is *not* an abuse
    # boundary: there is no server-set cookie, so a caller that omits or fabricates session_id
    # gets a fresh session (and a fresh counter) every time. The enforceable bounds are the IP,
    # integration and organization scopes above. A conversation scope is deferred with B5's usage
    # accounting — one conversation per session at MVP, so it would duplicate this one.
    await rate_limiter.check(
        "session",
        str(session.id),
        settings.PUBLIC_CHAT_RATE_LIMIT_PER_SESSION,
        window,
    )

    db.add(
        Message(
            conversation_id=conversation.id,
            role=MessageRole.VISITOR,
            direction=MessageDirection.INBOUND,
            # No status: a guest's message has no delivery lifecycle, and writing SENT here would be
            # a fiction every status query would then have to special-case.
            content=message,
        )
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
            conversation = await _latest_conversation(db, session.id)
            if conversation is None:
                conversation = _new_conversation(session.id)
                db.add(conversation)
                await db.flush()
            return session, conversation

    session = VisitorSession(
        project_id=ctx.project_id,
        integration_id=ctx.integration_id,
        channel=Channel.WEB,
        origin=ctx.origin,
        expires_at=utc_now() + timedelta(hours=settings.PUBLIC_SESSION_TTL_HOURS),
    )
    db.add(session)
    await db.flush()
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
