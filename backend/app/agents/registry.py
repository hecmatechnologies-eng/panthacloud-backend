"""Agent registry: resolve a name and version to its definition (FR-047).

Optimize for Deletion: an agent is removable by deleting its module and its one registration line.
"""

from app.agents.base import AgentDefinition


class AgentNotFoundError(Exception):
    """No agent is registered under the requested name and version."""


class AgentRegistry:
    def __init__(self) -> None:
        self._agents: dict[tuple[str, str], AgentDefinition] = {}

    def register(self, definition: AgentDefinition) -> None:
        key = (definition.name, definition.version)
        if key in self._agents:
            # Silently replacing would change what a persisted AgentRun cites (FR-089).
            raise ValueError(
                f"Agent {definition.name!r} version {definition.version!r} is already registered."
            )
        self._agents[key] = definition

    def get(self, name: str, version: str) -> AgentDefinition:
        try:
            return self._agents[(name, version)]
        except KeyError:
            raise AgentNotFoundError(f"No agent registered as {name!r} version {version!r}.") from None

    def list(self) -> list[AgentDefinition]:
        return [self._agents[key] for key in sorted(self._agents)]

    def clear(self) -> None:
        self._agents.clear()


registry = AgentRegistry()


def register_agent(definition: AgentDefinition) -> None:
    registry.register(definition)


def get_agent(name: str, version: str) -> AgentDefinition:
    return registry.get(name, version)
