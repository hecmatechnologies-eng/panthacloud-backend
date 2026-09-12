"""Public chat request/response DTOs (step B4)."""

import uuid

from pydantic import BaseModel, Field, field_validator

# The generated key is `fussion_pk_` + token_urlsafe(24), 43 characters; 64 bounds the untrusted
# input without coupling to the exact generator length.
MAX_PUBLIC_KEY_LENGTH = 64
MAX_MESSAGE_LENGTH = 4000


class ChatRequest(BaseModel):
    public_key: str = Field(..., min_length=1, max_length=MAX_PUBLIC_KEY_LENGTH)
    session_id: uuid.UUID | None = None
    message: str = Field(..., min_length=1, max_length=MAX_MESSAGE_LENGTH)

    @field_validator("message")
    @classmethod
    def _not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Message must not be blank.")
        return value


class Citation(BaseModel):
    document_id: uuid.UUID
    filename: str
    chunk_index: int
    page_number: int | None = None
    score: float


class ChatResponse(BaseModel):
    session_id: uuid.UUID
    conversation_id: uuid.UUID
    reply: str
    citations: list[Citation] = []
