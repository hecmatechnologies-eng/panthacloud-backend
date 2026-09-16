"""Public chat endpoints (step B4, B7).

Unauthenticated by design: the public client key plus the request's ``Origin`` are the credential,
and the resolver decides the tenant from them. The key grants chat only — it is not a bearer token
and reaches no control-plane resource (FR-114).

CORS for customer origins is a B8 gate, not a B4 one: the app's global CORSMiddleware would
intercept a customer preflight before this handler runs, so the per-origin story belongs with the
real widget.

B7 adds the streaming twin. Refusals are resolved **before** the response starts, so tenancy, rate
limits and configuration still answer with the same HTTP status the JSON endpoint returns — a
refusal is never a 200 stream that then reports an error.
"""

import asyncio
import json
from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.llm.gateway import (
    BudgetExceededError,
    ContextTooLargeError,
    ModelCallError,
    ModelNotAllowedError,
    ModelNotConfiguredError,
)
from app.runtime.chat import (
    AssistantDisabledError,
    ChatStreamDelta,
    ChatStreamEvent,
    ChatStreamStart,
    handle_chat,
    start_chat_stream,
)
from app.runtime.rate_limit import RateLimitExceeded
from app.runtime.resolver import TenantResolutionError
from app.schemas.public_chat import ChatRequest, ChatResponse, Citation
from app.services.knowledge.embeddings import EmbeddingProviderError

router = APIRouter(tags=["Public Chat"])

# How long the stream may go quiet before a keepalive frame is sent. Proxies and load balancers
# close a silent connection; an SSE comment keeps it warm without the client seeing anything.
KEEPALIVE_SECONDS = 15.0

# Everything a caller may be refused for, in one place: two endpoints answer the same failures, and
# a per-endpoint `except` chain is how a new exception type silently becomes a 500.
_REFUSALS = (
    TenantResolutionError,
    RateLimitExceeded,
    AssistantDisabledError,
    ModelNotConfiguredError,
    ModelNotAllowedError,
    ModelCallError,
    ContextTooLargeError,
    BudgetExceededError,
    EmbeddingProviderError,
)


def _refusal(exc: Exception) -> HTTPException:
    if isinstance(exc, TenantResolutionError):
        # One status and one body for every tenancy refusal (the B2 gate): no branch here may
        # distinguish an unknown key from an unregistered or foreign origin.
        return HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc))
    if isinstance(exc, RateLimitExceeded):
        return HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many requests. Please slow down.",
            headers={"Retry-After": str(exc.retry_after)},
        )
    if isinstance(exc, AssistantDisabledError):
        return HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="This assistant is currently unavailable.",
        )
    if isinstance(exc, (ModelNotConfiguredError, ModelNotAllowedError)):
        # Fail loud, never fabricate (CLAUDE.md §4.10). An allowlist breach should be unreachable
        # after startup validation; caught so a misconfiguration is legible, not an unhandled 500.
        return HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="The assistant is not configured.",
        )
    if isinstance(exc, ContextTooLargeError):
        return HTTPException(
            status_code=status.HTTP_413_CONTENT_TOO_LARGE,
            detail="Your message is too long for this assistant.",
        )
    if isinstance(exc, BudgetExceededError):
        return HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail="This assistant has reached its usage limit.",
        )
    if isinstance(exc, EmbeddingProviderError):
        # Retrieval runs before the model; an embedding outage must be legible, not a 500.
        return HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="The assistant is temporarily unavailable.",
        )
    # ModelCallError: the provider failed after the bounded retries were exhausted.
    return HTTPException(
        status_code=status.HTTP_502_BAD_GATEWAY,
        detail="The assistant could not respond right now. Please try again.",
    )


@router.post(
    "/chat",
    response_model=ChatResponse,
    summary="Send a visitor message and receive a reply",
)
async def public_chat(
    request: Request,
    payload: ChatRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> ChatResponse:
    client_ip = request.client.host if request.client else None
    try:
        result = await handle_chat(
            db,
            public_key=payload.public_key,
            origin=request.headers.get("origin"),
            session_id=payload.session_id,
            message=payload.message,
            client_ip=client_ip,
        )
    except _REFUSALS as exc:
        raise _refusal(exc) from None

    return ChatResponse(
        session_id=result.session_id,
        conversation_id=result.conversation_id,
        reply=result.reply,
        citations=[Citation(**citation) for citation in result.citations],
    )


@router.post(
    "/chat/stream",
    summary="Send a visitor message and receive a streamed reply",
)
async def public_chat_stream(request: Request, payload: ChatRequest) -> StreamingResponse:
    """The SSE twin of ``POST /chat``.

    No ``get_db`` dependency: the turn's database work is committed before the first token and the
    reply is written in a fresh session afterwards, so no session is held for the life of the
    connection (FR-118).
    """
    client_ip = request.client.host if request.client else None
    try:
        events = await start_chat_stream(
            public_key=payload.public_key,
            origin=request.headers.get("origin"),
            session_id=payload.session_id,
            message=payload.message,
            client_ip=client_ip,
        )
    except _REFUSALS as exc:
        raise _refusal(exc) from None

    return StreamingResponse(
        _sse_frames(events),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            # Proxies buffer by default, which would hold every token back until the stream ended.
            "X-Accel-Buffering": "no",
        },
    )


def _frame(event: ChatStreamEvent) -> str:
    if isinstance(event, ChatStreamStart):
        return _sse(
            "start",
            {
                "session_id": str(event.session_id),
                "conversation_id": str(event.conversation_id),
                "citations": list(event.citations),
            },
        )
    if isinstance(event, ChatStreamDelta):
        return _sse("token", {"text": event.text})
    return _sse(
        "done",
        {
            "model": event.model,
            "usage": {
                "input_tokens": event.usage.input_tokens,
                "output_tokens": event.usage.output_tokens,
            },
        },
    )


def _sse(name: str, data: dict) -> str:
    return f"event: {name}\ndata: {json.dumps(data)}\n\n"


async def _sse_frames(events: AsyncIterator[ChatStreamEvent]) -> AsyncIterator[str]:
    """Frame a turn, keeping the connection warm while the model is quiet.

    The iteration runs in a task that is *not* cancelled when a keepalive is due: cancelling the
    pending ``__anext__`` would tear down the provider stream behind it.
    """
    iterator = events.__aiter__()
    while True:
        pending = asyncio.ensure_future(iterator.__anext__())
        while True:
            done, _ = await asyncio.wait({pending}, timeout=KEEPALIVE_SECONDS)
            if done:
                break
            yield ": keepalive\n\n"
        try:
            event = pending.result()
        except StopAsyncIteration:
            return
        yield _frame(event)
