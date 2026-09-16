"""Step B · B4/B5 — public chat endpoint (FR-107, FR-108, FR-113, FR-114, FR-119).

The runtime plane's first reachable surface. It must be correctly tenanted (the public key and
Origin, never a client-supplied identifier, decide the tenant), rate-limited, and it must persist
the conversation. B5 replaced the canned reply with a model call through the gateway; every test
here installs a deterministic fake gateway, so nothing hits a paid API.

CORS for customer origins is deliberately not here: the app's global CORSMiddleware would
intercept a customer preflight, and the browser story belongs to B8. Logged as a B8 gate.
"""

import json
import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from httpx import AsyncClient, Response
from sqlalchemy import func, select

from app.core.config import settings
from app.core.database import get_session_factory
from app.llm.gateway import ModelGateway, set_model_gateway
from app.llm.providers.fake import FakeModelProvider
from app.models.assistant import Assistant
from app.models.conversation import Conversation, Message, MessageRole, VisitorSession
from app.models.knowledge import KnowledgeBase
from app.models.model_usage import ModelUsage
from app.runtime.chat import ChatStreamEnd, ChatStreamStart, start_chat_stream
from app.runtime.rate_limit import rate_limiter

CHAT_URL = "/api/v1/public/chat"
STREAM_URL = "/api/v1/public/chat/stream"
ORIGIN = "https://shop.example.com"
MODEL_REPLY = "This is the fake model's reply."

# The installed fake provider, so a test can inspect the prompt the runtime assembled.
_FAKE: dict[str, FakeModelProvider] = {}


@pytest.fixture(autouse=True)
def _reset_rate_limiter():
    """Rate-limit state is process-global; every test starts from empty (FIRST: Isolated)."""
    rate_limiter.reset()
    yield
    rate_limiter.reset()


@pytest.fixture(autouse=True)
def _model_gateway():
    """Install a deterministic fake model gateway; tests never reach a paid API."""
    provider = FakeModelProvider(reply=MODEL_REPLY)
    set_model_gateway(ModelGateway(provider))
    _FAKE["provider"] = provider
    yield
    set_model_gateway(None)
    _FAKE.clear()


# ============================================================
# Fixtures / helpers
# ============================================================


async def register_user(client: AsyncClient, email: str, name: str) -> tuple[str, str]:
    resp = await client.post(
        "/api/v1/auth/register",
        json={
            "email": email,
            "password": "Password123!",
            "full_name": name,
            "org_name": f"{name}'s Org",
        },
    )
    assert resp.status_code == 201
    token = resp.json()["access_token"]
    orgs = await client.get(
        "/api/v1/organizations", headers={"Authorization": f"Bearer {token}"}
    )
    return token, orgs.json()[0]["id"]


async def create_project(client: AsyncClient, token: str, org_id: str, name: str) -> str:
    resp = await client.post(
        f"/api/v1/organizations/{org_id}/projects",
        headers={"Authorization": f"Bearer {token}"},
        json={"name": name, "slug": name.lower().replace(" ", "-")},
    )
    assert resp.status_code == 201
    return resp.json()["id"]


async def create_integration(
    client: AsyncClient, token: str, org_id: str, proj_id: str
) -> dict:
    resp = await client.post(
        f"/api/v1/organizations/{org_id}/projects/{proj_id}/website-integrations",
        headers={"Authorization": f"Bearer {token}"},
        json={"repository_owner": "fussion-org", "repository_name": "storefront"},
    )
    assert resp.status_code == 201
    return resp.json()


async def register_origin(
    client: AsyncClient, token: str, org_id: str, proj_id: str, origin: str
) -> None:
    resp = await client.post(
        f"/api/v1/organizations/{org_id}/projects/{proj_id}/website-integrations/origins",
        headers={"Authorization": f"Bearer {token}"},
        json={"origin": origin},
    )
    assert resp.status_code == 201


async def tenant(
    client: AsyncClient, email: str, name: str, origin: str = ORIGIN
) -> tuple[dict, str, str]:
    """An org/project/integration with one registered origin."""
    token, org_id = await register_user(client, email, name)
    proj_id = await create_project(client, token, org_id, f"{name} Proj")
    integration = await create_integration(client, token, org_id, proj_id)
    await register_origin(client, token, org_id, proj_id, origin)
    return integration, org_id, proj_id


async def chat(
    client: AsyncClient,
    public_key: str | None,
    message: str = "Hello",
    *,
    origin: str | None = ORIGIN,
    session_id: str | uuid.UUID | None = None,
) -> Response:
    headers = {} if origin is None else {"Origin": origin}
    body: dict = {"public_key": public_key, "message": message}
    if session_id is not None:
        body["session_id"] = str(session_id)
    return await client.post(CHAT_URL, json=body, headers=headers)


async def seed_session(
    integration_id: str,
    origin: str = ORIGIN,
    expires_in: timedelta = timedelta(hours=1),
) -> uuid.UUID:
    session_factory = get_session_factory()
    async with session_factory() as db:
        session = VisitorSession(
            integration_id=uuid.UUID(integration_id),
            origin=origin,
            expires_at=datetime.now(UTC) + expires_in,
        )
        db.add(session)
        await db.commit()
        await db.refresh(session)
        return session.id


async def counts() -> tuple[int, int, int]:
    session_factory = get_session_factory()
    async with session_factory() as db:
        return (
            (await db.execute(select(func.count()).select_from(VisitorSession))).scalar_one(),
            (await db.execute(select(func.count()).select_from(Conversation))).scalar_one(),
            (await db.execute(select(func.count()).select_from(Message))).scalar_one(),
        )


async def messages_of(conversation_id: uuid.UUID) -> list[Message]:
    session_factory = get_session_factory()
    async with session_factory() as db:
        stmt = (
            select(Message)
            .where(Message.conversation_id == conversation_id)
            .order_by(Message.created_at, Message.id)
        )
        return list((await db.execute(stmt)).scalars().all())


# ============================================================
# 1. Happy path — session, persistence, model reply
# ============================================================


@pytest.mark.asyncio
async def test_first_turn_creates_session_conversation_and_messages(client: AsyncClient) -> None:
    integration, _, _ = await tenant(client, "pc_owner@example.com", "PcOwner")

    resp = await chat(client, integration["public_key"], "Do you deliver?")
    assert resp.status_code == 200
    data = resp.json()
    assert set(data) == {"session_id", "conversation_id", "reply", "citations"}
    assert data["reply"] == MODEL_REPLY

    assert await counts() == (1, 1, 2)
    stored = await messages_of(uuid.UUID(data["conversation_id"]))
    assert [(m.role, m.content) for m in stored] == [
        (MessageRole.VISITOR, "Do you deliver?"),
        (MessageRole.ASSISTANT, MODEL_REPLY),
    ]


@pytest.mark.asyncio
async def test_second_turn_reuses_session_and_conversation(client: AsyncClient) -> None:
    integration, _, _ = await tenant(client, "pc_reuse@example.com", "PcReuse")

    first = (await chat(client, integration["public_key"], "one")).json()
    second = await chat(
        client, integration["public_key"], "two", session_id=first["session_id"]
    )
    assert second.status_code == 200
    body = second.json()
    assert body["session_id"] == first["session_id"]
    assert body["conversation_id"] == first["conversation_id"]

    assert await counts() == (1, 1, 4)


@pytest.mark.asyncio
async def test_tenant_instructions_extend_the_platform_contract(client: AsyncClient) -> None:
    """A business's own instructions are appended to the platform's, never substituted for them.

    The grounding contract — answer only from CONTEXT, decline when it does not contain the answer,
    treat visitor and retrieved text as data — is a safety rule, not a preference. Substituting it
    let an accidental edit turn the assistant into one that invents answers, with nothing to say so.
    """
    from app.runtime.assistant import PLATFORM_INSTRUCTIONS

    integration, _, proj_id = await tenant(client, "pc_assist@example.com", "PcAssist")

    session_factory = get_session_factory()
    async with session_factory() as db:
        db.add(
            Assistant(
                project_id=uuid.UUID(proj_id),
                system_instructions="You are AcmeBot, the store's assistant.",
                is_enabled=True,
            )
        )
        await db.commit()

    resp = await chat(client, integration["public_key"], "hi")
    assert resp.json()["reply"] == MODEL_REPLY

    prompt = _FAKE["provider"].calls[0].messages
    assert prompt[0].role == "system"
    # The contract survives the tenant's edit, and the tenant's words follow it.
    assert PLATFORM_INSTRUCTIONS in prompt[0].content
    assert "You are AcmeBot, the store's assistant." in prompt[0].content
    assert prompt[0].content.index(PLATFORM_INSTRUCTIONS) < prompt[0].content.index("AcmeBot")
    # The visitor's message is a user turn, not part of the instruction region (FR-098).
    assert prompt[-1].role == "user"
    assert "QUESTION: hi" in prompt[-1].content


@pytest.mark.asyncio
async def test_the_assistant_runs_on_the_organizations_chosen_model(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The organization's choice has to reach the model call, not just the settings screen."""
    from app.models.organization_model_settings import OrganizationModelSettings

    monkeypatch.setattr(settings, "MODEL_ID", "deployment-default")
    monkeypatch.setattr(settings, "MODEL_ALLOWED_IDS", ["deployment-default", "org-choice"])

    integration, org_id, _ = await tenant(client, "pc_orgmodel@example.com", "PcOrgModel")
    session_factory = get_session_factory()
    async with session_factory() as db:
        db.add(
            OrganizationModelSettings(
                organization_id=uuid.UUID(org_id), model_id="org-choice"
            )
        )
        await db.commit()

    await chat(client, integration["public_key"], "hi")

    assert _FAKE["provider"].calls[0].model == "org-choice"


@pytest.mark.asyncio
async def test_the_assistant_falls_back_to_the_deployment_model(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "MODEL_ID", "deployment-default")
    monkeypatch.setattr(settings, "MODEL_ALLOWED_IDS", ["deployment-default"])

    integration, _, _ = await tenant(client, "pc_fallback@example.com", "PcFallback")

    await chat(client, integration["public_key"], "hi")

    assert _FAKE["provider"].calls[0].model == "deployment-default"


@pytest.mark.asyncio
async def test_model_answers_without_an_assistant(client: AsyncClient) -> None:
    integration, _, _ = await tenant(client, "pc_noassist@example.com", "PcNoAssist")
    resp = await chat(client, integration["public_key"], "hi")
    assert resp.status_code == 200
    assert resp.json()["reply"] == MODEL_REPLY


@pytest.mark.asyncio
async def test_usage_is_recorded_for_the_organization(client: AsyncClient) -> None:
    integration, org_id, proj_id = await tenant(client, "pc_usage@example.com", "PcUsage")

    assert (await chat(client, integration["public_key"], "hi")).status_code == 200

    session_factory = get_session_factory()
    async with session_factory() as db:
        usage = (await db.execute(select(ModelUsage))).scalar_one()
    assert usage.organization_id == uuid.UUID(org_id)
    assert usage.project_id == uuid.UUID(proj_id)
    assert usage.provider == "fake"
    assert usage.estimated_cost_usd > Decimal(0)


@pytest.mark.asyncio
async def test_disabled_assistant_returns_503(client: AsyncClient) -> None:
    integration, _, proj_id = await tenant(client, "pc_disabled@example.com", "PcDisabled")
    session_factory = get_session_factory()
    async with session_factory() as db:
        db.add(Assistant(project_id=uuid.UUID(proj_id), is_enabled=False))
        await db.commit()

    assert (await chat(client, integration["public_key"], "hi")).status_code == 503


@pytest.mark.asyncio
async def test_unconfigured_model_returns_503(client: AsyncClient) -> None:
    integration, _, _ = await tenant(client, "pc_nomodel@example.com", "PcNoModel")
    set_model_gateway(None)
    assert (await chat(client, integration["public_key"], "hi")).status_code == 503


@pytest.mark.asyncio
async def test_exhausted_budget_returns_402(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    integration, org_id, _ = await tenant(client, "pc_budget@example.com", "PcBudget")
    monkeypatch.setattr(settings, "MODEL_DEFAULT_SPEND_LIMIT_USD", 0.5)

    session_factory = get_session_factory()
    async with session_factory() as db:
        db.add(
            ModelUsage(
                organization_id=uuid.UUID(org_id),
                provider="seed",
                model="gemini-2.5-flash",
                estimated_cost_usd=Decimal("1.0"),
            )
        )
        await db.commit()

    assert (await chat(client, integration["public_key"], "hi")).status_code == 402


# ============================================================
# 2. Tenancy — the public key and Origin decide the tenant
# ============================================================


@pytest.mark.asyncio
async def test_unknown_key_and_unregistered_origin_are_indistinguishable(
    client: AsyncClient,
) -> None:
    integration, _, _ = await tenant(client, "pc_enum@example.com", "PcEnum")

    unknown_key = await chat(client, "fussion_pk_" + "z" * 32)
    wrong_origin = await chat(client, integration["public_key"], origin="https://evil.example.com")

    assert unknown_key.status_code == 403
    assert wrong_origin.status_code == 403
    assert unknown_key.json() == wrong_origin.json()


@pytest.mark.asyncio
async def test_missing_origin_is_refused(client: AsyncClient) -> None:
    integration, _, _ = await tenant(client, "pc_noorigin@example.com", "PcNoOrigin")
    resp = await chat(client, integration["public_key"], origin=None)
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_cross_integration_origin_is_refused(client: AsyncClient) -> None:
    integration_a, _, _ = await tenant(
        client, "pc_x_a@example.com", "PcXA", origin="https://a.example.com"
    )
    integration_b, _, _ = await tenant(
        client, "pc_x_b@example.com", "PcXB", origin="https://b.example.com"
    )

    # Each key only accepts its own registered origin.
    assert (await chat(client, integration_a["public_key"], origin="https://b.example.com")).status_code == 403
    assert (await chat(client, integration_b["public_key"], origin="https://a.example.com")).status_code == 403
    assert (await chat(client, integration_a["public_key"], origin="https://a.example.com")).status_code == 200


@pytest.mark.asyncio
async def test_foreign_session_id_starts_a_new_session_under_the_right_tenant(
    client: AsyncClient,
) -> None:
    integration_a, _, _ = await tenant(client, "pc_fs_a@example.com", "PcFsA")
    integration_b, _, _ = await tenant(client, "pc_fs_b@example.com", "PcFsB")

    session_a = await seed_session(integration_a["id"])

    # Integration B's key presented with integration A's session id.
    resp = await chat(
        client, integration_b["public_key"], "hello", session_id=session_a
    )
    assert resp.status_code == 200
    assert resp.json()["session_id"] != str(session_a)

    session_factory = get_session_factory()
    async with session_factory() as db:
        new_session = (
            await db.execute(
                select(VisitorSession).where(
                    VisitorSession.id == uuid.UUID(resp.json()["session_id"])
                )
            )
        ).scalar_one()
        # The new session belongs to B, never to A.
        assert new_session.integration_id == uuid.UUID(integration_b["id"])


@pytest.mark.asyncio
async def test_expired_session_starts_a_new_session(client: AsyncClient) -> None:
    integration, _, _ = await tenant(client, "pc_exp@example.com", "PcExp")
    expired = await seed_session(integration["id"], expires_in=timedelta(seconds=-60))

    resp = await chat(client, integration["public_key"], "hi", session_id=expired)
    assert resp.status_code == 200
    assert resp.json()["session_id"] != str(expired)


@pytest.mark.asyncio
async def test_session_cannot_be_resumed_from_a_different_registered_origin(
    client: AsyncClient,
) -> None:
    token, org_id = await register_user(client, "pc_bind@example.com", "PcBind")
    proj_id = await create_project(client, token, org_id, "PcBind Proj")
    integration = await create_integration(client, token, org_id, proj_id)
    await register_origin(client, token, org_id, proj_id, "https://a.example.com")
    await register_origin(client, token, org_id, proj_id, "https://b.example.com")

    first = await chat(client, integration["public_key"], "one", origin="https://a.example.com")
    session_id = first.json()["session_id"]

    # Same key and integration, but a different registered origin: the session must not carry over.
    second = await chat(
        client,
        integration["public_key"],
        "two",
        origin="https://b.example.com",
        session_id=session_id,
    )
    assert second.status_code == 200
    assert second.json()["session_id"] != session_id

    session_factory = get_session_factory()
    async with session_factory() as db:
        new_session = (
            await db.execute(
                select(VisitorSession).where(
                    VisitorSession.id == uuid.UUID(second.json()["session_id"])
                )
            )
        ).scalar_one()
        assert new_session.origin == "https://b.example.com"


@pytest.mark.asyncio
async def test_stored_messages_are_tenant_scoped(client: AsyncClient) -> None:
    integration_a, _, _ = await tenant(client, "pc_iso_a@example.com", "PcIsoA")
    integration_b, _, _ = await tenant(client, "pc_iso_b@example.com", "PcIsoB")

    await chat(client, integration_a["public_key"], "message for A")
    await chat(client, integration_b["public_key"], "message for B")

    session_factory = get_session_factory()
    async with session_factory() as db:
        contents = sorted(
            (await db.execute(select(Message.content))).scalars().all()
        )
    assert "message for A" in contents
    assert "message for B" in contents
    assert await counts() == (2, 2, 4)


# ============================================================
# 3. Rate limiting (FR-113)
# ============================================================


@pytest.mark.asyncio
async def test_session_rate_limit_returns_429_with_retry_after(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    integration, _, _ = await tenant(client, "pc_rl_s@example.com", "PcRlS")
    monkeypatch.setattr(settings, "PUBLIC_CHAT_RATE_LIMIT_PER_SESSION", 1)

    first = await chat(client, integration["public_key"], "one")
    assert first.status_code == 200
    second = await chat(
        client, integration["public_key"], "two", session_id=first.json()["session_id"]
    )
    assert second.status_code == 429
    assert second.headers.get("retry-after")


@pytest.mark.asyncio
async def test_integration_rate_limit_returns_429(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    integration, _, _ = await tenant(client, "pc_rl_i@example.com", "PcRlI")
    monkeypatch.setattr(settings, "PUBLIC_CHAT_RATE_LIMIT_PER_INTEGRATION", 1)

    assert (await chat(client, integration["public_key"], "one")).status_code == 200
    assert (await chat(client, integration["public_key"], "two")).status_code == 429


@pytest.mark.asyncio
async def test_organization_rate_limit_returns_429(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    integration, _, _ = await tenant(client, "pc_rl_o@example.com", "PcRlO")
    monkeypatch.setattr(settings, "PUBLIC_CHAT_RATE_LIMIT_PER_ORGANIZATION", 1)

    assert (await chat(client, integration["public_key"], "one")).status_code == 200
    assert (await chat(client, integration["public_key"], "two")).status_code == 429


@pytest.mark.asyncio
async def test_ip_rate_limit_returns_429(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    integration, _, _ = await tenant(client, "pc_rl_ip@example.com", "PcRlIp")
    monkeypatch.setattr(settings, "PUBLIC_CHAT_RATE_LIMIT_PER_IP", 1)

    assert (await chat(client, integration["public_key"], "one")).status_code == 200
    # The IP scope applies before the tenant is known and cannot be varied by the caller.
    assert (await chat(client, integration["public_key"], "two")).status_code == 429


# ============================================================
# 4. Input bounds & capability separation
# ============================================================


@pytest.mark.parametrize("message", ["", "   ", "x" * 5000])
@pytest.mark.asyncio
async def test_message_is_required_and_bounded(client: AsyncClient, message: str) -> None:
    integration, _, _ = await tenant(client, "pc_msg@example.com", "PcMsg")
    resp = await chat(client, integration["public_key"], message)
    assert resp.status_code == 422
    # Nothing was persisted for a rejected request.
    assert await counts() == (0, 0, 0)


@pytest.mark.asyncio
async def test_public_key_grants_no_control_plane_access(client: AsyncClient) -> None:
    integration, _, _ = await tenant(client, "pc_scope@example.com", "PcScope")
    resp = await client.get(
        "/api/v1/organizations",
        headers={"Authorization": f"Bearer {integration['public_key']}"},
    )
    assert resp.status_code == 401


# ============================================================
# 5. Knowledge grounding (B6)
# ============================================================


async def upload_document(
    client: AsyncClient, token: str, org_id: str, proj_id: str, filename: str, content: str
) -> dict:
    resp = await client.post(
        f"/api/v1/organizations/{org_id}/projects/{proj_id}/knowledge/documents",
        headers={"Authorization": f"Bearer {token}"},
        files={"file": (filename, content, "text/plain")},
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


async def tenant_with_docs(
    client: AsyncClient, email: str, name: str, doc_text: str
) -> tuple[dict, str, str, dict]:
    token, org_id = await register_user(client, email, name)
    proj_id = await create_project(client, token, org_id, f"{name} Proj")
    integration = await create_integration(client, token, org_id, proj_id)
    await register_origin(client, token, org_id, proj_id, ORIGIN)
    doc = await upload_document(client, token, org_id, proj_id, "faq.txt", doc_text)
    return integration, org_id, proj_id, doc


@pytest.mark.asyncio
async def test_answer_is_grounded_in_the_tenants_document(client: AsyncClient) -> None:
    integration, _, _, doc = await tenant_with_docs(
        client,
        "b6_owner@example.com",
        "B6Owner",
        "Refund policy: customers may request a full refund within 30 days of purchase.",
    )

    resp = await chat(client, integration["public_key"], "What is the refund policy?")
    assert resp.status_code == 200
    data = resp.json()
    assert data["reply"] == MODEL_REPLY
    assert len(data["citations"]) >= 1
    assert data["citations"][0]["document_id"] == doc["id"]
    assert data["citations"][0]["filename"] == "faq.txt"

    # FR-098: the retrieved chunk is fenced as data in a user turn, never in the instruction region.
    prompt = _FAKE["provider"].calls[-1].messages
    assert prompt[0].role == "system"
    assert "30 days" not in prompt[0].content
    assert prompt[-1].role == "user"
    assert "CONTEXT" in prompt[-1].content
    assert "30 days" in prompt[-1].content
    assert "QUESTION: What is the refund policy?" in prompt[-1].content


@pytest.mark.asyncio
async def test_no_knowledge_base_means_no_context(client: AsyncClient) -> None:
    integration, _, _ = await tenant(client, "b6_nokb@example.com", "B6NoKb")
    resp = await chat(client, integration["public_key"], "anything?")
    assert resp.status_code == 200
    assert resp.json()["citations"] == []
    user_turn = _FAKE["provider"].calls[-1].messages[-1]
    assert "No knowledge base context" in user_turn.content


@pytest.mark.asyncio
async def test_retrieval_is_tenant_filtered(client: AsyncClient) -> None:
    _, _, _, doc_a = await tenant_with_docs(
        client, "b6_a@example.com", "B6A", "Secret A policy: alpha only, never shared."
    )
    integration_b, _, _, _ = await tenant_with_docs(
        client, "b6_b@example.com", "B6B", "Beta refund policy: 7 days."
    )

    data = (await chat(client, integration_b["public_key"], "What is the policy?")).json()
    assert all(citation["document_id"] != doc_a["id"] for citation in data["citations"])
    prompt_text = " ".join(m.content for m in _FAKE["provider"].calls[-1].messages)
    assert "Secret A" not in prompt_text


@pytest.mark.asyncio
async def test_citations_are_persisted_on_the_assistant_message(client: AsyncClient) -> None:
    integration, _, _, doc = await tenant_with_docs(
        client, "b6_persist@example.com", "B6Persist", "Shipping takes 3 to 5 business days."
    )
    await chat(client, integration["public_key"], "How long is shipping?")

    session_factory = get_session_factory()
    async with session_factory() as db:
        assistant = (
            await db.execute(select(Message).where(Message.role == MessageRole.ASSISTANT))
        ).scalar_one()
    assert assistant.citations[0]["document_id"] == doc["id"]


async def _set_knowledge_base(proj_id: str, **values: object) -> None:
    session_factory = get_session_factory()
    async with session_factory() as db:
        kb = (
            await db.execute(
                select(KnowledgeBase).where(KnowledgeBase.project_id == uuid.UUID(proj_id))
            )
        ).scalar_one()
        for key, value in values.items():
            setattr(kb, key, value)
        await db.commit()


@pytest.mark.asyncio
async def test_embedding_provider_failure_returns_503(client: AsyncClient) -> None:
    integration, _, proj_id, _ = await tenant_with_docs(
        client, "b6_embedfail@example.com", "B6EmbedFail", "Refund policy: 30 days."
    )
    # A stored model the factory cannot resolve must be a legible 503, not a 500.
    await _set_knowledge_base(proj_id, embedding_model="unknown-embedding-model")
    assert (await chat(client, integration["public_key"], "refund?")).status_code == 503


@pytest.mark.asyncio
async def test_embedding_dimension_mismatch_returns_503(client: AsyncClient) -> None:
    integration, _, proj_id, _ = await tenant_with_docs(
        client, "b6_dim@example.com", "B6Dim", "Refund policy: 30 days."
    )
    # Query would embed at 768 while the stored chunks are 384: fail closed, do not return garbage.
    await _set_knowledge_base(proj_id, embedding_dimension=768)
    assert (await chat(client, integration["public_key"], "refund?")).status_code == 503


# ============================================================
# B7 — the streamed twin
# ============================================================


def _events(body: str) -> list[tuple[str, dict]]:
    """Parse an SSE body into its (event, data) pairs, ignoring keepalive comments."""
    parsed: list[tuple[str, dict]] = []
    for block in body.strip().split("\n\n"):
        if not block or block.startswith(":"):
            continue
        name, data = "", ""
        for line in block.splitlines():
            if line.startswith("event: "):
                name = line[len("event: ") :]
            elif line.startswith("data: "):
                data = line[len("data: ") :]
        parsed.append((name, json.loads(data) if data else {}))
    return parsed


async def stream(
    client: AsyncClient,
    public_key: str | None,
    message: str = "Hello",
    *,
    origin: str | None = ORIGIN,
) -> Response:
    headers = {} if origin is None else {"Origin": origin}
    return await client.post(
        STREAM_URL,
        json={"public_key": public_key, "message": message},
        headers=headers,
    )


@pytest.mark.asyncio
async def test_stream_emits_start_tokens_and_a_terminal_event(client: AsyncClient) -> None:
    integration, _, _ = await tenant(client, "b7_ok@example.com", "B7Ok")

    resp = await stream(client, integration["public_key"])

    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/event-stream")
    events = _events(resp.text)
    assert events[0][0] == "start"
    assert events[0][1]["session_id"] and events[0][1]["conversation_id"]
    # The deltas are the answer, in order, and reassemble to exactly the reply.
    assert "".join(data["text"] for name, data in events if name == "token") == MODEL_REPLY
    assert events[-1][0] == "done"
    assert events[-1][1]["usage"] == {"input_tokens": 10, "output_tokens": 5}


@pytest.mark.asyncio
async def test_stream_persists_the_turn_and_records_the_usage(client: AsyncClient) -> None:
    integration, _, _ = await tenant(client, "b7_persist@example.com", "B7Persist")

    resp = await stream(client, integration["public_key"])
    conversation_id = uuid.UUID(_events(resp.text)[0][1]["conversation_id"])

    stored = await messages_of(conversation_id)
    assert [message.role for message in stored] == [MessageRole.VISITOR, MessageRole.ASSISTANT]
    assert stored[1].content == MODEL_REPLY

    session_factory = get_session_factory()
    async with session_factory() as db:
        usage = (await db.execute(select(ModelUsage))).scalars().all()
    assert len(usage) == 1
    assert usage[0].conversation_id == conversation_id


@pytest.mark.asyncio
async def test_the_visitors_turn_is_committed_before_the_first_token(
    client: AsyncClient,
) -> None:
    """FR-118: nothing holds a database session across the stream.

    The generator is driven directly because httpx's ASGI transport buffers the whole response —
    the middle of a stream is not observable over HTTP. If the pre-stream work were still in an
    open transaction, an independent session could not see the visitor's turn.
    """
    integration, _, _ = await tenant(client, "b7_commit@example.com", "B7Commit")

    events = await start_chat_stream(
        public_key=integration["public_key"],
        origin=ORIGIN,
        session_id=None,
        message="Hello",
        client_ip="127.0.0.1",
    )
    first = await anext(events)
    assert isinstance(first, ChatStreamStart)

    session_factory = get_session_factory()
    async with session_factory() as db:
        visitor_rows = (
            await db.execute(select(Message).where(Message.role == MessageRole.VISITOR))
        ).scalars().all()
    assert len(visitor_rows) == 1
    assert visitor_rows[0].content == "Hello"

    rest = [event async for event in events]
    assert isinstance(rest[-1], ChatStreamEnd)

    async with session_factory() as db:
        roles = sorted(
            row.role.value
            for row in (await db.execute(select(Message))).scalars().all()
        )
    assert roles == ["ASSISTANT", "VISITOR"]


@pytest.mark.asyncio
async def test_stream_refuses_before_the_response_starts(client: AsyncClient) -> None:
    """A refusal must be a status, never a 200 stream that then reports an error."""
    integration, _, _ = await tenant(client, "b7_refuse@example.com", "B7Refuse")

    foreign = await stream(client, integration["public_key"], origin="https://evil.example.com")
    assert foreign.status_code == 403
    assert "text/event-stream" not in foreign.headers.get("content-type", "")

    unknown = await stream(client, "fk_not_a_real_key")
    assert unknown.status_code == 403


@pytest.mark.asyncio
async def test_stream_returns_503_for_a_disabled_assistant(client: AsyncClient) -> None:
    integration, _, proj_id = await tenant(client, "b7_disabled@example.com", "B7Disabled")
    session_factory = get_session_factory()
    async with session_factory() as db:
        db.add(Assistant(project_id=uuid.UUID(proj_id), is_enabled=False))
        await db.commit()

    resp = await stream(client, integration["public_key"])
    assert resp.status_code == 503
    assert "text/event-stream" not in resp.headers.get("content-type", "")


@pytest.mark.asyncio
async def test_the_assistant_turn_records_the_definition_that_produced_it(
    client: AsyncClient,
) -> None:
    """An answer stays attributable after the business edits its instructions (B9).

    Recorded per turn rather than per conversation: instructions can change mid-conversation, and
    the earlier answers were produced by a definition that no longer exists.
    """
    from app.runtime.assistant import CUSTOMER_ASSISTANT

    integration, _, _ = await tenant(client, "pc_trace@example.com", "PcTrace")

    resp = await chat(client, integration["public_key"], "hi")
    conversation_id = uuid.UUID(resp.json()["conversation_id"])

    assistant_message = (await messages_of(conversation_id))[-1]
    assert assistant_message.role == MessageRole.ASSISTANT
    assert assistant_message.assistant_version == CUSTOMER_ASSISTANT.version
    assert assistant_message.prompt_hash


@pytest.mark.asyncio
async def test_the_recorded_prompt_hash_follows_the_instructions(
    client: AsyncClient,
) -> None:
    """The hash is what identifies the definition: a version alone would not, because a business
    edits its instructions without any version changing."""
    integration, _, proj_id = await tenant(client, "pc_hash@example.com", "PcHash")

    first = await chat(client, integration["public_key"], "hi")
    first_hash = (await messages_of(uuid.UUID(first.json()["conversation_id"])))[-1].prompt_hash

    session_factory = get_session_factory()
    async with session_factory() as db:
        db.add(
            Assistant(
                project_id=uuid.UUID(proj_id),
                system_instructions="Always mention our free returns policy.",
                is_enabled=True,
            )
        )
        await db.commit()

    second = await chat(client, integration["public_key"], "hi again")
    second_hash = (await messages_of(uuid.UUID(second.json()["conversation_id"])))[-1].prompt_hash

    assert first_hash and second_hash
    assert first_hash != second_hash
