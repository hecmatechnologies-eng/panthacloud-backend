import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.assistant import Assistant, AssistantPosition
from app.models.audit_event import AuditEvent
from app.models.knowledge import KnowledgeBase
from app.models.project import Project
from app.schemas.assistant import (
    AssistantPreview,
    AssistantRead,
    AssistantUpdate,
    KnowledgeBaseStatus,
    MockPreviewPayload,
)
from app.services.assistant.validation import validate_assistant_fields


def get_default_assistant_data(project_name: str) -> dict[str, Any]:
    """Return default configuration parameters for a new assistant."""
    return {
        "name": "Fussion Assistant",
        "description": f"AI Assistant for {project_name}",
        "welcome_message": "Hi! How can I help you today?",
        "system_instructions": None,
        "brand_color": "#6366F1",
        "text_color": "#FFFFFF",
        "position": AssistantPosition.BOTTOM_RIGHT,
        "avatar_url": None,
        "starter_prompt": "What can you tell me about your products?",
        "is_enabled": True,
    }


async def _record_audit(
    db: AsyncSession,
    org_id: uuid.UUID,
    project_id: uuid.UUID,
    user_id: uuid.UUID | None,
    event_type: str,
    resource_id: uuid.UUID,
    payload: dict[str, Any] | None = None,
) -> None:
    event = AuditEvent(
        organization_id=org_id,
        project_id=project_id,
        user_id=user_id,
        event_type=event_type,
        resource_type="assistant",
        resource_id=resource_id,
        payload=payload or {},
    )
    db.add(event)
    await db.commit()


async def update_assistant_configuration(
    assistant: Assistant,
    update_data: AssistantUpdate,
    org_id: uuid.UUID,
    project_id: uuid.UUID,
    user_id: uuid.UUID | None,
    db: AsyncSession,
) -> Assistant:
    """Validate and update the assistant configuration."""
    data = update_data.model_dump(exclude_unset=True)
    validate_assistant_fields(data)

    for key, value in data.items():
        setattr(assistant, key, value)

    db.add(assistant)
    await db.commit()
    await db.refresh(assistant)

    await _record_audit(
        db=db,
        org_id=org_id,
        project_id=project_id,
        user_id=user_id,
        event_type="assistant.configuration.updated",
        resource_id=assistant.id,
        payload={k: str(v) for k, v in data.items()},
    )

    return assistant


async def reset_assistant_configuration(
    assistant: Assistant,
    project_name: str,
    org_id: uuid.UUID,
    project_id: uuid.UUID,
    user_id: uuid.UUID | None,
    db: AsyncSession,
) -> Assistant:
    """Reset the assistant configuration to the canonical default values."""
    defaults = get_default_assistant_data(project_name)

    for key, value in defaults.items():
        setattr(assistant, key, value)

    db.add(assistant)
    await db.commit()
    await db.refresh(assistant)

    await _record_audit(
        db=db,
        org_id=org_id,
        project_id=project_id,
        user_id=user_id,
        event_type="assistant.configuration.reset",
        resource_id=assistant.id,
        payload={"reset_to_defaults": True},
    )

    return assistant


async def build_assistant_preview_payload(
    assistant: Assistant,
    project: Project,
    db: AsyncSession,
) -> AssistantPreview:
    """
    Build client-side preview payload communicating assistant styling,
    knowledge base grounding availability, and deterministic mock responses.
    Zero external LLM calls.
    """
    # Check knowledge base connection
    stmt = (
        select(KnowledgeBase)
        .where(KnowledgeBase.project_id == project.id)
        .options(selectinload(KnowledgeBase.documents))
    )
    result = await db.execute(stmt)
    kb = result.scalar_one_or_none()

    docs_count = len(kb.documents) if kb else 0
    chunks_count = sum(d.chunks_count for d in kb.documents) if kb else 0
    has_kb = kb is not None and docs_count > 0

    if has_kb:
        grounding_status = "Online • Grounded in Knowledge Base"
        sample_resp = (
            f"Hello! I am {assistant.name}. Based on {docs_count} document(s) in your Knowledge Base, "
            "I can answer questions regarding your products, services, and policies."
        )
    else:
        grounding_status = "Online • No Knowledge Base Connected"
        sample_resp = (
            f"Hello! I am {assistant.name}. Connect your business documentation in the Knowledge Base "
            "tab to enable grounded answers for your customers."
        )

    sample_user = assistant.starter_prompt or "What can you tell me about your products?"

    return AssistantPreview(
        assistant=AssistantRead.model_validate(assistant),
        knowledge_base=KnowledgeBaseStatus(
            has_knowledge_base=has_kb,
            documents_count=docs_count,
            ready_chunks_count=chunks_count,
        ),
        mock_preview=MockPreviewPayload(
            sample_user_message=sample_user,
            sample_assistant_response=sample_resp,
            grounding_status=grounding_status,
        ),
    )
