"""Public chat endpoint (step B4).

Unauthenticated by design: the public client key plus the request's ``Origin`` are the credential,
and the resolver decides the tenant from them. The key grants chat only — it is not a bearer token
and reaches no control-plane resource (FR-114).

CORS for customer origins is a B8 gate, not a B4 one: the app's global CORSMiddleware would
intercept a customer preflight before this handler runs, so the per-origin story belongs with the
real widget.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.llm.gateway import (
    BudgetExceededError,
    ContextTooLargeError,
    ModelCallError,
    ModelNotAllowedError,
    ModelNotConfiguredError,
)
from app.runtime.chat import AssistantDisabledError, handle_chat
from app.runtime.rate_limit import RateLimitExceeded
from app.runtime.resolver import TenantResolutionError
from app.schemas.public_chat import ChatRequest, ChatResponse, Citation
from app.services.knowledge.embeddings import EmbeddingProviderError

router = APIRouter(tags=["Public Chat"])


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
    except TenantResolutionError as exc:
        # One status and one body for every tenancy refusal (the B2 gate): no branch here may
        # distinguish an unknown key from an unregistered or foreign origin.
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(exc),
        ) from None
    except RateLimitExceeded as exc:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many requests. Please slow down.",
            headers={"Retry-After": str(exc.retry_after)},
        ) from None
    except AssistantDisabledError:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="This assistant is currently unavailable.",
        ) from None
    except ModelNotConfiguredError:
        # Fail loud, never fabricate (CLAUDE.md §4.10).
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="The assistant is not configured.",
        ) from None
    except ModelNotAllowedError:
        # Startup validation should make this unreachable; caught so a misconfiguration is a
        # legible 503, not an unhandled 500.
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="The assistant is not configured.",
        ) from None
    except ModelCallError:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="The assistant could not respond right now. Please try again.",
        ) from None
    except ContextTooLargeError:
        raise HTTPException(
            status_code=status.HTTP_413_CONTENT_TOO_LARGE,
            detail="Your message is too long for this assistant.",
        ) from None
    except BudgetExceededError:
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail="This assistant has reached its usage limit.",
        ) from None
    except EmbeddingProviderError:
        # Retrieval runs before the model; an embedding outage must be a legible 503, not a 500.
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="The assistant is temporarily unavailable.",
        ) from None

    return ChatResponse(
        session_id=result.session_id,
        conversation_id=result.conversation_id,
        reply=result.reply,
        citations=[Citation(**citation) for citation in result.citations],
    )
