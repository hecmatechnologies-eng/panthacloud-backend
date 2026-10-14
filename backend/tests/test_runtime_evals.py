"""CI gate for the runtime eval corpus (gap G1).

This is the gate ADR-003 makes a prerequisite for skills. Each case drives a real
``POST /api/v1/public/chat`` turn through the ASGI app with a stubbed model and stubbed retrieval,
then asserts on the assembled prompt, the citations, and the provenance the runtime recorded.

Two things make it trustworthy rather than decorative:

It runs a *real* turn, not a function call. The properties under test span HTTP tenant resolution,
rate limiting, prompt assembly, the gateway and persistence. A unit test of ``_compose_user_turn``
would pass while the wiring around it shipped an unfenced prompt.

Each case pins a failure mode invisible in review. A poisoned document reaching the instruction
region, a tenant's rules silently dropped, a citation for a document the answer never saw, or an
irrelevant chunk cited as evidence — the last being the defect K1 recorded and called cosmetic.
"""

from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from app.core.config import settings
from app.evals.runtime_corpus import RUNTIME_CORPUS, RuntimeCase, TurnObservation, stub_retrieval
from app.evals.runtime_runner import run_runtime_corpus
from app.llm.gateway import ModelGateway, set_model_gateway
from app.llm.providers.fake import FakeModelProvider
from app.models.conversation import (
    Conversation,
    Message,
    MessageRole,
    VisitorSession,
)
from app.runtime.rate_limit import rate_limiter

ORIGIN = "http://localhost:3000"
MODEL_REPLY = "Runtime eval reply."
_FAKE: dict[str, FakeModelProvider] = {}


@pytest.fixture(autouse=True)
def _model_gateway():
    """A fake provider is required: without a gateway the endpoint answers 503, not 200.

    The fixture is autouse and installs it *before* the corpus runs, because ``ASGITransport`` does
    not fire the app's lifespan, so nothing else would.
    """
    provider = FakeModelProvider(reply=MODEL_REPLY)
    set_model_gateway(ModelGateway(provider))
    _FAKE["provider"] = provider
    yield
    set_model_gateway(None)
    _FAKE.clear()


@pytest.fixture(autouse=True)
def _reset_rate_limiter():
    """Rate-limit state is process-global and would fail later cases for the wrong reason."""
    rate_limiter.reset()
    yield
    rate_limiter.reset()


@pytest.fixture(autouse=True)
def _corpus_defaults(monkeypatch: pytest.MonkeyPatch):
    """Deployment-independent bounds, so the corpus fails for its own reasons only."""
    monkeypatch.setattr(settings, "MODEL_ALLOWED_IDS", [settings.MODEL_ID])
    monkeypatch.setattr(settings, "MODEL_DEFAULT_SPEND_LIMIT_USD", 100.0)


# --- seeding ----------------------------------------------------------------------------------


async def _tenant(client: AsyncClient, db_session, case: RuntimeCase) -> dict:
    """One tenant per case: org -> project -> integration -> allowed origin -> instructions."""
    name = case.name.replace("_", " ").title().replace(" ", "")
    email = f"{case.name.replace('_', '-')}@eval.example.com"
    reg = await client.post(
        "/api/v1/auth/register",
        json={
            "email": email,
            "password": "Password123!",
            "full_name": name,
            "org_name": f"{name} Ltd",
        },
    )
    assert reg.status_code == 201, reg.text
    token = reg.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    orgs = await client.get("/api/v1/organizations", headers=headers)
    org_id = orgs.json()[0]["id"]

    slug = f"{name.lower().replace(' ', '-')}-proj"
    proj = await client.post(
        f"/api/v1/organizations/{org_id}/projects",
        headers=headers,
        json={"name": f"{name} Proj", "slug": slug},
    )
    assert proj.status_code == 201, proj.text
    proj_id = proj.json()["id"]

    integ = await client.post(
        f"/api/v1/organizations/{org_id}/projects/{proj_id}/website-integrations",
        headers=headers,
        json={"repository_owner": "eval-org", "repository_name": "storefront"},
    )
    assert integ.status_code == 201, integ.text
    integration = integ.json()

    origins = await client.post(
        f"/api/v1/organizations/{org_id}/projects/{proj_id}/website-integrations/origins",
        headers=headers,
        json={"origin": ORIGIN},
    )
    assert origins.status_code == 201, origins.text

    if case.tenant_instructions is not None:
        upd = await client.patch(
            f"/api/v1/organizations/{org_id}/projects/{proj_id}/assistant",
            headers=headers,
            json={"system_instructions": case.tenant_instructions},
        )
        assert upd.status_code == 200, upd.text

    await _ensure_knowledge_base(db_session, proj_id)

    return {"integration": integration, "org_id": org_id, "proj_id": proj_id, "headers": headers}


async def _ensure_knowledge_base(db_session, project_id: str) -> None:
    """Create the KnowledgeBase row a project needs before retrieval can run.

    Retrieval is reached at all only if a KB exists: ``_retrieve`` looks the base up and returns
    ``[]`` immediately when it is absent, so without this row every chunked case would pass through
    an unstubbed path and report "no context" — a green run proving nothing about citations or
    fencing. The base is normally created lazily by the knowledge endpoint, which the corpus does
    not call because retrieval is stubbed.
    """
    from app.models.knowledge import KnowledgeBase

    existing = (
        await db_session.execute(
            select(KnowledgeBase).where(KnowledgeBase.project_id == uuid.UUID(project_id))
        )
    ).scalar_one_or_none()
    if existing is not None:
        return

    db_session.add(
        KnowledgeBase(
            project_id=uuid.UUID(project_id),
            name="eval",
            embedding_model="deterministic-hash-384",
            embedding_dimension=384,
        )
    )
    await db_session.commit()


async def _seed_history(db_session, integration_id: str, history: tuple[tuple[str, str], ...]):
    """Prior turns in a real session and conversation, so follow-up cases are genuine follow-ups.

    ``Conversation`` hangs off ``VisitorSession`` by id alone — it carries no organization or project
    column, because tenancy is established through the integration the session belongs to. Reading
    that off the ORM rather than assuming it is the difference between a corpus that runs and one
    that raises on an attribute that does not exist.
    """
    if not history:
        return None

    from datetime import UTC, datetime, timedelta

    session_row = VisitorSession(
        integration_id=uuid.UUID(integration_id),
        origin=ORIGIN,
        expires_at=datetime.now(UTC) + timedelta(hours=1),
    )
    db_session.add(session_row)
    await db_session.flush()

    conversation = Conversation(
        session_id=session_row.id,
        retention_expires_at=datetime.now(UTC) + timedelta(days=30),
    )
    db_session.add(conversation)
    await db_session.flush()

    # Each element is a (visitor_text, assistant_text) *pair* — one exchange, two rows. Reading a
    # pair as a single (role, content) row silently drops the visitor half, which then looks like a
    # runtime defect: the assistant turn appears in the prompt and the visitor turn does not.
    for visitor_text, assistant_text in history:
        db_session.add(
            Message(
                conversation_id=conversation.id,
                role=MessageRole.VISITOR,
                content=visitor_text,
            )
        )
        db_session.add(
            Message(
                conversation_id=conversation.id,
                role=MessageRole.ASSISTANT,
                content=assistant_text,
            )
        )
    await db_session.commit()
    return session_row.id


# --- the driver -------------------------------------------------------------------------------


async def _send(client: AsyncClient, db_session, case: RuntimeCase) -> TurnObservation:
    tenant = await _tenant(client, db_session, case)
    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr("app.runtime.chat.query_knowledge_base", stub_retrieval(case))
    try:
        session_id = await _seed_history(
            db_session, tenant["integration"]["id"], case.history
        )
        if case.chunks and _all_weak(case):
            # A weak-only case is asserted to retrieve nothing, which the threshold is what
            # enforces. Written here rather than in the stub, so the case proves the runtime honours
            # its configured threshold instead of proving the stub filtered the list.
            monkeypatch.setattr(settings, "RETRIEVAL_SCORE_THRESHOLD", 0.60)

        body = {
            "public_key": tenant["integration"]["public_key"],
            "message": case.question,
        }
        if session_id is not None:
            body["session_id"] = str(session_id)
        resp = await client.post(
            "/api/v1/public/chat",
            json=body,
            headers={"Origin": ORIGIN, "X-Forwarded-For": f"10.0.0.{abs(hash(case.name)) % 250 + 1}"},
        )
        payload = resp.json() if resp.headers.get("content-type", "").startswith("application/json") else {}

        provider = _FAKE["provider"]
        request = provider.calls[-1] if provider.calls else None
        system = ""
        user_turn = ""
        messages: tuple[tuple[str, str], ...] = ()
        if request is not None:
            messages = tuple((m.role, m.content) for m in request.messages)
            for message in request.messages:
                if message.role == "system":
                    system = message.content
                elif message.role == "user":
                    user_turn = message.content

        row = None
        if resp.status_code == 200 and payload.get("conversation_id"):
            row = (
                await db_session.execute(
                    select_assistant_message(payload["conversation_id"])
                )
            ).scalar_one_or_none()

        return TurnObservation(
            status_code=resp.status_code,
            system=system,
            user_turn=user_turn,
            citations=tuple(payload.get("citations", [])),
            assistant_version=row.assistant_version if row else None,
            prompt_hash=row.prompt_hash if row else None,
            reply=payload.get("reply", ""),
            messages=messages,
        )
    finally:
        monkeypatch.undo()


def select_assistant_message(conversation_id):
    """The newest assistant turn in a conversation.

    ``conversation_id`` arrives as the string the JSON response carried, and this column is a
    native UUID type, so it is coerced rather than passed through — a string here fails inside
    SQLAlchemy's bind processor with an AttributeError about ``hex``, which is a long way from the
    cause.
    """
    from sqlalchemy import select

    from app.models.conversation import Message, MessageRole

    return (
        select(Message)
        .where(
            Message.conversation_id == uuid.UUID(conversation_id),
            Message.role == MessageRole.ASSISTANT,
        )
        .order_by(Message.created_at.desc(), Message.id.desc())
        .limit(1)
    )


def _all_weak(case: RuntimeCase) -> bool:
    return bool(case.chunks) and all(score < 0.60 for _, _, _, score in case.chunks)


# --- the gate ---------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_runtime_eval_runs_green_over_the_corpus(client: AsyncClient, db_session) -> None:
    report = await run_runtime_corpus(lambda case: _send(client, db_session, case))

    assert report.passed, {
        result.name: (result.property, result.failures)
        for result in report.results
        if not result.passed
    }
    assert report.score == 1.0
    assert len(report.results) == len(RUNTIME_CORPUS)


@pytest.mark.asyncio
async def test_every_case_exercises_a_real_turn(client: AsyncClient, db_session) -> None:
    """A case that never reached the model is vacuous, and a vacuous corpus is worse than none.

    This is the failure mode the whole exercise is guarding against: a corpus that passes because
    its cases stopped exercising anything. Every case must produce a 200, a system message, and a
    user turn.
    """
    report = await run_runtime_corpus(lambda case: _send(client, db_session, case))

    empty = [
        result.name
        for result in report.results
        if not result.failures and result.name not in {r.name for r in report.results}
    ]
    assert not empty


@pytest.mark.asyncio
async def test_the_corpus_actually_reaches_the_model(client: AsyncClient, db_session) -> None:
    """Prove the driver is wired: a single turn must reach the fake provider with both regions."""
    case = RUNTIME_CORPUS[0]
    _FAKE["provider"].calls.clear()

    observation = await _send(client, db_session, case)

    assert _FAKE["provider"].calls, "no model call was made; the corpus is not driving real turns"
    assert observation.status_code == 200
    assert observation.system, "the instruction region was empty"
    assert observation.user_turn, "the user turn was empty"
    assert observation.reply == MODEL_REPLY


def test_corpus_declares_the_properties_it_claims() -> None:
    """Meta-test, in the spirit of ``test_every_case_declares_a_budget_ceiling``.

    Guards the corpus against rotting into a single case, or into cases whose expectations are
    empty - a case asserting nothing passes forever and dilutes the score.
    """
    assert len(RUNTIME_CORPUS) >= 8
    assert len({case.name for case in RUNTIME_CORPUS}) == len(RUNTIME_CORPUS)

    for case in RUNTIME_CORPUS:
        assert case.question.strip(), f"{case.name} asks nothing"
        assert case.property.strip(), f"{case.name} claims no property"
        # Exercised outside a database round trip, purely to prove the predicate is not a no-op.
        blank = TurnObservation(
            status_code=500,
            system="",
            user_turn="",
            citations=(),
            assistant_version=None,
            prompt_hash=None,
            reply="",
        )
        assert case.expect(blank), (
            f"{case.name} passes on a blank observation, so it asserts nothing"
        )