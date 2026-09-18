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

    def contains(self, name: str, version: str) -> bool:
        return (name, version) in self._agents

    def clear(self) -> None:
        self._agents.clear()


registry = AgentRegistry()


def register_agent(definition: AgentDefinition) -> None:
    registry.register(definition)


def register_default_agents() -> None:
    """Register the built-in agents. One line per agent — adding one is not a core edit."""
    from app.agents.coding_agent import CODING_AGENT
    from app.agents.website_analyst import WEBSITE_ANALYST

    if not registry.contains(WEBSITE_ANALYST.name, WEBSITE_ANALYST.version):
        registry.register(WEBSITE_ANALYST)
    if not registry.contains(CODING_AGENT.name, CODING_AGENT.version):
        registry.register(CODING_AGENT)


def get_agent(name: str, version: str) -> AgentDefinition:
    return registry.get(name, version)
