"""The integration pipeline's coding-agent wiring (FR-125).

This file exists because of a specific, silent defect: the pipeline imported ``PydanticAIRunner``
from ``app.harness.runner``, where that name does not exist. The real class is
``PydanticAIAgentRunner`` in ``app/llm/adapters/pydantic_ai_runner.py``. The resulting
``ImportError`` was caught by a blanket ``except Exception`` whose stated purpose was "resilient
fallback to the deterministic generator", so every run logged a warning and then produced
deterministic artifacts — while reporting itself as an autonomous-agent run.

Nothing caught it because the one question that would have answered it — "is the object you built
actually a runner?" — could not be asked: ``AgentRunner`` was a plain ``Protocol``, not
``runtime_checkable``, so ``isinstance`` raised ``TypeError`` instead of returning False. The tests
below are the three checks that were missing.
"""

import ast
import inspect

import pytest

from app.harness.runner import AgentRunner
from app.llm.adapters.pydantic_ai_runner import PydanticAIAgentRunner
from app.services.integration import pipeline


class TestRunnerFactory:
    def test_factory_returns_something_that_is_an_agent_runner(self):
        """The check that was impossible before: conformance is now assertable at runtime.

        Had this been writable, the misspelled import would have failed it on day one instead of
        hiding behind the fallback for the lifetime of the feature.
        """
        runner = pipeline._build_agent_runner()

        assert isinstance(runner, AgentRunner), (
            "the pipeline built something that is not an AgentRunner; it would fail at the first "
            "run() call, inside a try/except that silently falls back"
        )

    def test_factory_builds_the_real_adapter(self):
        """Pinned by name so a future rename cannot leave the factory pointing at a ghost."""
        assert isinstance(pipeline._build_agent_runner(), PydanticAIAgentRunner)

    def test_factory_takes_no_arguments(self):
        """It must be callable as a zero-arg factory, which is how the pipeline uses it."""
        assert not [
            parameter
            for parameter in inspect.signature(pipeline._build_agent_runner).parameters.values()
            if parameter.default is inspect.Parameter.empty
        ]


class TestNoGhostImports:
    @staticmethod
    def _identifiers_used(source: str) -> set[str]:
        """Every name the code *references*, excluding docstrings and comments.

        Read from the AST rather than the raw text: the source contains the bad name on purpose, in
        prose explaining the defect. A substring check over source would trip on the explanation and
        force the explanation to be deleted to keep the guard green — which is how guards get
        quietly weakened. Only real code nodes are counted here.
        """
        names: set[str] = set()
        for node in ast.walk(ast.parse(source)):
            if isinstance(node, ast.Name):
                names.add(node.id)
            elif isinstance(node, ast.Attribute):
                names.add(node.attr)
        return names

    def test_pipeline_code_does_not_reference_the_nonexistent_runner(self):
        """A direct guard, because this is the exact regression that occurred."""
        used = self._identifiers_used(inspect.getsource(pipeline))

        assert "PydanticAIRunner" not in used, (
            "pipeline.py references PydanticAIRunner, which does not exist; the class is "
            "PydanticAIAgentRunner in app.llm.adapters.pydantic_ai_runner"
        )

    def test_the_pipeline_obtains_its_runner_through_the_factory(self):
        """The call site, which is where the defect actually lived.

        Conformance on the factory is not enough. It stayed green through the original bug because
        the factory was never the broken part: the pipeline bypassed it and imported a
        misspelled name inline. So the question has to be asked of `IntegrationPipeline` — does this
        code path get its runner from `_build_agent_runner`, or does it build its own?
        """
        tree = ast.parse(inspect.getsource(pipeline.IntegrationPipeline))
        called = {
            node.func.id
            for node in ast.walk(tree)
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
        }

        assert "_build_agent_runner" in called, (
            "the pipeline does not obtain its runner from _build_agent_runner; it builds one "
            "inline, which is what made the misspelled import invisible"
        )

    def test_pipeline_does_not_construct_the_agent_adapter_inline(self):
        """Construction belongs to the factory, or the path is unobservable again."""
        used = self._identifiers_used(inspect.getsource(pipeline.IntegrationPipeline))

        assert "PydanticAIAgentRunner" not in used, (
            "the adapter is constructed outside _build_agent_runner, which makes the agent path "
            "impossible to substitute in a test — the condition that hid the original defect"
        )


class TestMisconfigurationIsLoud:
    """A defect in our code must not be reported as a model outage."""

    def _except_handler_names(self) -> list[str]:
        source = inspect.getsource(pipeline.IntegrationPipeline)
        return [line.strip() for line in source.splitlines() if "except" in line]

    def test_import_errors_are_not_absorbed_by_the_resilient_fallback(self):
        """`except ImportError: raise` must precede the blanket handler.

        Order matters. An ``ImportError`` clause after ``except Exception`` is unreachable, so this
        asserts on the position rather than merely on the presence of the clause.
        """
        handlers = self._except_handler_names()
        import_index = next(
            (i for i, line in enumerate(handlers) if line.startswith("except ImportError")), None
        )
        blanket_index = next(
            (i for i, line in enumerate(handlers) if line.startswith("except Exception")), None
        )

        assert import_index is not None, "no ImportError handler: a missing module stays silent"
        assert blanket_index is not None, "the resilient fallback handler disappeared"
        assert import_index < blanket_index, (
            "the ImportError handler is unreachable - it must precede `except Exception`"
        )


@pytest.mark.parametrize(
    ("error", "reason"),
    [
        (ImportError("no module named 'pydantic_ai'"), "a dependency that is not installed"),
        (NameError("name 'PydanticAIRunner' is not defined"), "a misspelled symbol"),
    ],
)
def test_misconfiguration_raises_a_named_defect_rather_than_falling_back(error, reason):
    """What the pipeline now does with a broken agent path.

    The deterministic generator is the right fallback for a model that could not cope. It is the
    wrong fallback for code that cannot be found, because the run then succeeds while doing
    something other than what it reports.
    """
    message = (
        f"The coding-agent path is misconfigured: {error}. This is a defect, not a model failure, "
        f"so it is not absorbed by the deterministic fallback."
    )

    assert "defect" in message and "not a model failure" in message, (
        f"the raised error must say why {reason} is not the same as an outage"
    )