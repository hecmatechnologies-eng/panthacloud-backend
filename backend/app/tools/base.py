"""The ``Tool`` contract (FR-064, FR-067, FR-068, FR-070).

A tool declares its name, a description written for the model, the capability it requires, whether
it reads or writes, and the Pydantic schema of its arguments. ``execute`` receives the trusted
``ExecutionContext`` and validated arguments; it resolves resource scope from the context, never
from an argument the model supplied.
"""

import abc
import enum
from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel

from app.harness.context import ExecutionContext


class ToolKind(str, enum.Enum):
    READ = "read"
    WRITE = "write"


class ToolError(Exception):
    """A tool failure whose message is safe and useful to show the model (FR-068).

    Raise this with a recovery hint — ``"File not found: components/App.tsx. Did you mean
    src/components/App.tsx?"`` — never a stack trace.

    ``benign=True`` marks the failure as *information rather than breakage*: the tool ran
    correctly and the answer is "no". A file that does not exist is a legitimate result of
    exploring a repository, not a sign the agent is stuck. The harness's circuit breaker
    excludes benign failures so a normal search cannot trip it, while a tool that is truly
    malfunctioning still does.
    """

    def __init__(self, message: str, *, benign: bool = False) -> None:
        super().__init__(message)
        self.benign = benign


@dataclass(frozen=True, slots=True)
class ToolResult:
    output: Any = None
    # Set when a paginated tool returned less than the full result (FR-067).
    truncated: bool = False
    error: str | None = None
    # True when the gateway refused the call on policy grounds, not because the tool failed.
    denied: bool = False
    # True when ``error`` describes a legitimate "not found" rather than a malfunction.
    # See ToolError for why this exists.
    benign: bool = False

    @property
    def is_error(self) -> bool:
        return self.error is not None


class Tool(abc.ABC):
    name: str
    description: str
    kind: ToolKind
    required_capability: str
    input_schema: type[BaseModel]

    @abc.abstractmethod
    async def execute(self, context: ExecutionContext, arguments: BaseModel) -> ToolResult:
        """Run the tool. Scope comes from ``context``; ``arguments`` are already validated."""
        ...
