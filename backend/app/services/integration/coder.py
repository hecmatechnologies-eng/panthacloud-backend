"""CodingAgent service — drives the autonomous CodingAgent through the harness loop (Step D).

Includes:
- Observe -> Write -> Validate -> Repair execution loop.
- Sandboxed write tools scoped to the ephemeral run directory.
- Neurosymbolic physical verification against StaticValidator.
- Autonomous repair turn if static validation flags issues.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.coding_agent import CODING_AGENT
from app.core.config import settings
from app.harness.context import ExecutionContext
from app.harness.loop import run_agent
from app.harness.runner import AgentRunner, AgentRunResult
from app.llm.gateway import ModelGateway
from app.models.agent_run import AgentRun
from app.models.website_integration import WebsiteIntegration
from app.schemas.website_integration import IntegrationPlanPayload
from app.services.integration.sandbox import LocalWorkspaceProvider
from app.services.integration.validation import StaticValidationError, StaticValidator
from app.services.killswitch import is_halted
from app.tools.gateway import ApprovedPlan, ToolGateway
from app.tools.registry import ToolRegistry
from app.tools.workspace import build_workspace_tools

logger = logging.getLogger("fussion.services.coder")


def build_coding_prompt(
    integration: WebsiteIntegration,
    plan: IntegrationPlanPayload,
    assistant_data: dict[str, Any],
) -> str:
    return (
        f"Integrate the Fussion chat widget into '{integration.widget_target_path}'.\n\n"
        f"FRAMEWORK SKILL: {integration.framework_skill_id}\n"
        f"PUBLIC KEY: {integration.public_key}\n"
        f"SCRIPT URL: {settings.widget_script_url}\n"
        f"ASSISTANT CONFIG:\n{json.dumps(assistant_data, indent=2)}\n\n"
        f"TARGET FILE: {integration.widget_target_path}\n"
        f"PLAN FILES TO CREATE: {plan.files_to_create}\n"
        f"PLAN FILES TO MODIFY: {plan.files_to_modify}\n\n"
        "Instructions:\n"
        "1. Inspect the target file using read_file.\n"
        "2. If the plan includes files to create, write them with full content using write_file.\n"
        "3. Inject the widget snippet cleanly into the target layout using write_file or apply_patch.\n"
        "4. Enclose injected markup within Fussion markers: "
        "<!-- Fussion Assistant Widget --> or /* Fussion Assistant Widget */.\n"
        "5. Conclude with CodingAgentOutput detailing the files and integration summary."
    )


async def execute_coding_agent(
    db: AsyncSession,
    *,
    context: ExecutionContext,
    plan: IntegrationPlanPayload,
    approved_plan: ApprovedPlan,
    sandbox_path: Path,
    integration: WebsiteIntegration,
    assistant_data: dict[str, Any],
    original_target: str,
    runner: AgentRunner,
    gateway: ModelGateway,
    tool_gateway: ToolGateway,
    registry: ToolRegistry,
    workspace_provider: LocalWorkspaceProvider,
    max_repair_turns: int = 1,
) -> tuple[AgentRun, dict[str, str]]:
    """Execute the autonomous CodingAgent to produce and verify integration files.

    Returns the completed AgentRun and the dictionary of generated/modified files.
    """
    # 1. Register read and write tools scoped to this sandbox
    from app.services.repository.reader import LocalWorkspaceReader
    from app.tools.repository import build_repository_tools

    existing_tool_names = {t.name for t in registry.list()}
    if "read_file" not in existing_tool_names:
        reader = LocalWorkspaceReader(sandbox_path)
        for tool in build_repository_tools(lambda ctx: reader):
            if tool.name not in existing_tool_names:
                registry.register(tool)

    scoped_tools = build_workspace_tools(
        resolve_path=lambda ctx: sandbox_path,
        provider=workspace_provider,
    )
    for tool in scoped_tools:
        if tool.name not in {t.name for t in registry.list()}:
            registry.register(tool)

    captured: list[AgentRunResult] = []

    async def on_result(res: AgentRunResult) -> None:
        captured.append(res)

    prompt = build_coding_prompt(integration, plan, assistant_data)

    logger.info("Executing CodingAgent for integration %s at %s", integration.id, sandbox_path)
    org_id = context.organization_id
    run = await run_agent(
        db,
        context=context,
        definition=CODING_AGENT,
        prompt=prompt,
        runner=runner,
        gateway=gateway,
        tool_gateway=tool_gateway,
        registry=registry,
        approved_plan=approved_plan,
        on_result=on_result,
        # Consulted before every tool call, so an operator can stop a runaway run without
        # waiting for the current step. Bound to this organization, so halting one tenant does
        # not stop the others.
        halt_check=lambda: is_halted(org_id),
    )

    # 2. Extract generated files from sandbox
    target_path = integration.widget_target_path
    generated_files: dict[str, str] = {}

    for rel_path in plan.files_to_create + plan.files_to_modify:
        try:
            content = workspace_provider.read_file(sandbox_path, rel_path)
            generated_files[rel_path] = content
        except FileNotFoundError:
            pass

    # 3. Static Validation & Self-Healing Loop
    original_files = {target_path: original_target}
    issues: list[str] = []
    try:
        StaticValidator.validate(
            integration.framework_skill_id,
            plan,
            generated_files,
            original_files=original_files,
        )
    except StaticValidationError as exc:
        issues = list(exc.issues)

    if issues and max_repair_turns > 0:
        logger.warning(
            "CodingAgent produced validation issues (%s). Triggering self-healing repair turn...",
            issues,
        )
        repair_prompt = (
            "Static validation of your changes failed with the following issues:\n"
            + "\n".join(f"- {issue}" for issue in issues)
            + "\nPlease inspect the files and repair them using write_file or apply_patch."
        )
        await run_agent(
            db,
            context=context,
            definition=CODING_AGENT,
            prompt=repair_prompt,
            runner=runner,
            gateway=gateway,
            tool_gateway=tool_gateway,
            registry=registry,
            approved_plan=approved_plan,
            # The repair turn is the ASI08 cascade risk: it re-enters the same loop with the
            # same tools. It carries the same halt check so an operator can stop the pair.
            halt_check=lambda: is_halted(org_id),
        )
        # Re-read files from sandbox
        generated_files.clear()
        for rel_path in plan.files_to_create + plan.files_to_modify:
            try:
                content = workspace_provider.read_file(sandbox_path, rel_path)
                generated_files[rel_path] = content
            except FileNotFoundError:
                pass

        # Final validation
        try:
            StaticValidator.validate(
                integration.framework_skill_id,
                plan,
                generated_files,
                original_files=original_files,
            )
        except StaticValidationError as exc:
            raise RuntimeError(
                f"Static validation failed after self-healing: {'; '.join(exc.issues)}"
            ) from exc

    return run, generated_files
