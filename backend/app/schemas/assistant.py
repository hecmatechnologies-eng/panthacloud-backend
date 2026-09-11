import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models.assistant import AssistantPosition


class AssistantRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    project_id: uuid.UUID
    name: str
    description: str | None = None
    welcome_message: str
    system_instructions: str | None = None
    brand_color: str
    text_color: str
    position: AssistantPosition
    avatar_url: str | None = None
    starter_prompt: str | None = None
    is_enabled: bool
    created_at: datetime
    updated_at: datetime


class AssistantCreate(BaseModel):
    name: str = Field("Fussion Assistant", min_length=1, max_length=100)
    description: str | None = Field(None, max_length=1000)
    welcome_message: str = Field("Hi! How can I help you today?", min_length=1, max_length=1000)
    system_instructions: str | None = Field(None, max_length=5000)
    brand_color: str = Field("#6366F1", max_length=20)
    text_color: str = Field("#FFFFFF", max_length=20)
    position: AssistantPosition = AssistantPosition.BOTTOM_RIGHT
    avatar_url: str | None = Field(None, max_length=500)
    starter_prompt: str | None = Field("What can you tell me about your products?", max_length=500)
    is_enabled: bool = True


class AssistantUpdate(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=100)
    description: str | None = Field(None, max_length=1000)
    welcome_message: str | None = Field(None, min_length=1, max_length=1000)
    system_instructions: str | None = Field(None, max_length=5000)
    brand_color: str | None = Field(None, max_length=20)
    text_color: str | None = Field(None, max_length=20)
    position: AssistantPosition | None = None
    avatar_url: str | None = Field(None, max_length=500)
    starter_prompt: str | None = Field(None, max_length=500)
    is_enabled: bool | None = None


class KnowledgeBaseStatus(BaseModel):
    has_knowledge_base: bool
    documents_count: int
    ready_chunks_count: int


class MockPreviewPayload(BaseModel):
    sample_user_message: str
    sample_assistant_response: str
    grounding_status: str


class AssistantPreview(BaseModel):
    assistant: AssistantRead
    knowledge_base: KnowledgeBaseStatus
    mock_preview: MockPreviewPayload
