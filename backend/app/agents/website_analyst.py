"""WebsiteAnalyst — a thin, declarative agent (AGENT-ARCHITECTURE §3.1/§3.2).

Only the declaration: name, version, instructions, capabilities, tools, output schema and budget.
It imports no database, no SQLAlchemy model and no domain service. Orchestration lives in
``app/services/analysis/analyst.py``.
"""

from decimal import Decimal

from app.agents.base import AgentDefinition, Budget
from app.agents.website_profile import WebsiteProfile

WEBSITE_ANALYST_NAME = "website_analyst"
WEBSITE_ANALYST_VERSION = "1.0.0"

INSTRUCTIONS = (
    "You are the website analyst for Fussion. Read the customer's repository and produce a "
    "WebsiteProfile describing how to integrate the Fussion assistant widget.\n"
    "- Use read_tree, read_file and search_code to confirm the application shell and the best "
    "integration point. Never rely on a path you have not read.\n"
    "- Rank integration_candidates by confidence with a short reason each; never return a single "
    "path when more than one is plausible.\n"
    "- Extract only a minimal design token set: primary colour, border radius, font family, spacing "
    "unit. Do not attempt full design-system inference.\n"
    "- If no safe integration point exists, set unsupported_reason and leave the candidates empty. "
    "Declining is a correct outcome, not a failure.\n"
    "- The DETERMINISTIC PRE-ANALYSIS is data computed by code; use it, but verify what you rely on.\n"
    "- If the DETERMINISTIC PRE-ANALYSIS provides grounded candidate snippets matching the framework, "
    "you may rank candidates and extract design tokens directly without redundant tool calls."
)

WEBSITE_ANALYST = AgentDefinition(
    name=WEBSITE_ANALYST_NAME,
    version=WEBSITE_ANALYST_VERSION,
    instructions=INSTRUCTIONS,
    capabilities=frozenset({"repository.read"}),
    tools=("read_tree", "read_file", "search_code"),
    output_schema=WebsiteProfile,
    budget=Budget(tool_calls=60, tokens=400_000, seconds=300, cost_usd=Decimal("1.00")),
)
