"""Step C · C5 — the AgentRunner seam and the Pydantic AI adapter (ADR-001, FR-072, FR-125).

Structured output is validated (unparseable = a failed step), usage is returned and handed to a
recorder, and `pydantic_ai` is imported only in `app/llm/adapters/`. Tests use pydantic_ai's own
`TestModel`/`FunctionModel`; no paid API is called.
"""

import uuid
from decimal import Decimal
from pathlib import Path

import pytest
from pydantic import BaseModel
from pydantic_ai.messages import ModelResponse, TextPart
from pydantic_ai.models.function import AgentInfo, FunctionModel
from pydantic_ai.models.test import TestModel
from sqlalchemy import select

from app.agents.base import AgentDefinition, Budget
from app.core.database import get_session_factory
from app.harness.context import ExecutionContext
from app.harness.runner import AgentRunResult, StructuredOutputError
from app.llm.adapters.pydantic_ai_runner import PydanticAIAgentRunner, gateway_usage_recorder
from app.llm.gateway import ModelGateway
from app.llm.providers.fake import FakeModelProvider
from app.models.model_usage import ModelUsage


class Profile(BaseModel):
    framework: str
    confident: bool


def _definition(output_schema: type[BaseModel] | None = Profile) -> AgentDefinition:
    return AgentDefinition(
        name="website_analyst",
        version="1.0.0",
        instructions="Analyse the repository and report the framework.",
        capabilities=frozenset({"repository.read"}),
        tools=(),
        output_schema=output_schema,
        budget=Budget(tool_calls=10, tokens=1000, seconds=30, cost_usd=Decimal("0.10")),
    )


def _context() -> ExecutionContext:
    return ExecutionContext(
        organization_id=uuid.uuid4(),
        project_id=uuid.uuid4(),
        repository_id=uuid.uuid4(),
        environment="test",
        agent_name="website_analyst",
        agent_version="1.0.0",
        capabilities=frozenset({"repository.read"}),
    )


# ============================================================
# 1. Structured output and usage
# ============================================================


@pytest.mark.asyncio
async def test_structured_output_is_parsed_and_validated() -> None:
    runner = PydanticAIAgentRunner(model=TestModel())
    result = await runner.run(_definition(), _context(), prompt="What framework is this?")

    assert isinstance(result.output, Profile)
    assert result.text is None
    assert result.input_tokens > 0
    assert result.model_id


@pytest.mark.asyncio
async def test_usage_is_handed_to_the_recorder() -> None:
    recorded: list[AgentRunResult] = []

    async def recorder(result: AgentRunResult) -> None:
        recorded.append(result)

    runner = PydanticAIAgentRunner(model=TestModel())
    result = await runner.run(_definition(), _context(), prompt="hi", usage_recorder=recorder)

    assert recorded == [result]
    assert recorded[0].input_tokens > 0


@pytest.mark.asyncio
async def test_unparseable_output_is_a_failed_step() -> None:
    def bad_model(_messages: list, _info: AgentInfo) -> ModelResponse:
        return ModelResponse(parts=[TextPart("this is not the requested schema")])

    runner = PydanticAIAgentRunner(model=FunctionModel(bad_model))
    with pytest.raises(StructuredOutputError):
        await runner.run(_definition(), _context(), prompt="hi")


@pytest.mark.asyncio
async def test_text_output_is_returned_when_no_schema_is_set() -> None:
    runner = PydanticAIAgentRunner(model=TestModel())
    result = await runner.run(_definition(output_schema=None), _context(), prompt="hi")
    assert result.output is None
    assert isinstance(result.text, str)


# ============================================================
# 2. The seam holds: framework confined to the adapter
# ============================================================


def test_pydantic_ai_is_imported_only_in_the_adapter() -> None:
    import app

    root = Path(app.__file__).parent
    offenders = [
        str(path.relative_to(root))
        for path in root.rglob("*.py")
        if "adapters" not in path.parts and "pydantic_ai" in path.read_text(encoding="utf-8")
    ]
    assert offenders == []


@pytest.mark.asyncio
async def test_a_fake_runner_substitutes() -> None:
    class FakeRunner:
        async def run(self, definition, context, *, prompt, usage_recorder=None):
            result = AgentRunResult(
                output=None,
                text=f"fake:{prompt}",
                input_tokens=1,
                output_tokens=2,
                provider="fake",
                model_id="fake",
                model_version_reported=None,
            )
            if usage_recorder is not None:
                await usage_recorder(result)
            return result

    result = await FakeRunner().run(_definition(), _context(), prompt="hi")
    assert result.text == "fake:hi"


@pytest.mark.asyncio
async def test_usage_recorder_meters_through_the_gateway() -> None:
    gateway = ModelGateway(FakeModelProvider())
    context = _context()
    result = AgentRunResult(
        output=None,
        text="x",
        input_tokens=1000,
        output_tokens=500,
        provider="gemini",
        model_id="gemini-2.5-flash",
        model_version_reported=None,
    )

    session_factory = get_session_factory()
    async with session_factory() as db:
        recorder = gateway_usage_recorder(gateway, db, context)
        await recorder(result)
        await db.commit()

    async with session_factory() as db:
        usage = (await db.execute(select(ModelUsage))).scalar_one()
    assert usage.organization_id == context.organization_id
    assert (usage.input_tokens, usage.output_tokens) == (1000, 500)
    assert usage.provider == "gemini"
    assert usage.estimated_cost_usd > Decimal(0)
