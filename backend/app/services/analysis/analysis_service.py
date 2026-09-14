"""Run the WebsiteAnalyst for a website integration and persist the result (step C10).

The wiring the read tools were waiting for: clone the repository at a pinned SHA, attach it to the
trusted `ExecutionContext`, run the analyst through the harness, persist the profile, and always
tear the workspace down.
"""

import logging

from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.website_analyst import WEBSITE_ANALYST
from app.agents.website_profile import WebsiteProfile
from app.core.config import settings
from app.harness.context import ExecutionContext
from app.llm.adapters.pydantic_ai_runner import PydanticAIAgentRunner
from app.llm.gateway import get_model_gateway
from app.models.organization import Organization
from app.models.project import Project
from app.models.website_analysis import WebsiteAnalysis
from app.models.website_integration import WebsiteIntegration
from app.services.analysis.analyst import analyze_repository
from app.services.analysis.clone import clone_repository, clone_url_for
from app.services.analysis.selection import select_target
from app.services.integration.credentials import resolve_github_token
from app.services.repository.reader import LocalWorkspaceReader
from app.services.repository.workspace import workspace_manager
from app.tools.gateway import ToolGateway
from app.tools.registry import ToolRegistry
from app.tools.repository import register_repository_tools

logger = logging.getLogger("fussion.analysis")


async def analyze_website_integration(
    db: AsyncSession,
    *,
    integration: WebsiteIntegration,
    organization: Organization,
    project: Project,
) -> WebsiteAnalysis:
    workspace_path, workspace_ref = workspace_manager.allocate_workspace(
        organization.id, project.id, integration.id
    )
    try:
        # Resolve the gateway before cloning: a no-model deployment must fail without touching
        # the repository.
        gateway = get_model_gateway()
        token = await resolve_github_token(integration)
        commit_sha = await clone_repository(
            clone_url_for(integration, token), integration.default_branch, workspace_path
        )
        workspace_manager.check_workspace_limits(workspace_path)

        context = ExecutionContext(
            organization_id=organization.id,
            project_id=project.id,
            repository_id=None,
            environment=settings.APP_ENV,
            agent_name=WEBSITE_ANALYST.name,
            agent_version=WEBSITE_ANALYST.version,
            capabilities=WEBSITE_ANALYST.capabilities,
            integration_id=integration.id,
            commit_sha=commit_sha,
            workspace_reference=workspace_ref,
        )
        registry = ToolRegistry()
        register_repository_tools(registry, lambda _ctx: LocalWorkspaceReader(workspace_path))

        try:
            run, profile = await analyze_repository(
                db,
                context=context,
                repo_root=workspace_path,
                runner=PydanticAIAgentRunner(),
                gateway=gateway,
                tool_gateway=ToolGateway(registry),
                registry=registry,
            )
        except Exception:
            # The harness marked the run FAILED and flushed it; commit so get_db's rollback does
            # not discard the failure record (FR-089).
            await db.commit()
            raise

        analysis = _build_analysis(integration.id, commit_sha, run.id, profile)
        db.add(analysis)

        # C11: the detected profile becomes the integration's configuration, so the plan and the
        # pull request use what was detected rather than a server default.
        #
        # Declining is not an error, and it is deliberately non-destructive: an unsupported
        # repository, a below-threshold candidate or an unsafe path leaves the integration's
        # existing configuration untouched (a fresh integration keeps its server defaults). The
        # Studio shows the ranked list for a human to choose.
        selected = select_target(profile) if profile is not None else None
        if selected is not None:
            integration.framework_skill_id = selected.framework_skill_id
            integration.widget_target_path = selected.widget_target_path
            logger.info(
                "Analysis configured integration %s: target '%s' (%s, confidence %.2f)",
                integration.id,
                selected.widget_target_path,
                selected.framework_skill_id,
                selected.confidence,
            )

        await db.commit()
        await db.refresh(analysis)
        return analysis
    finally:
        workspace_manager.cleanup_workspace(workspace_path)


def _build_analysis(integration_id, commit_sha: str, agent_run_id, profile: WebsiteProfile | None):
    if profile is None:
        return WebsiteAnalysis(
            integration_id=integration_id,
            commit_sha=commit_sha,
            agent_run_id=agent_run_id,
            unsupported_reason="The analyst produced no profile for this repository.",
        )
    return WebsiteAnalysis(
        integration_id=integration_id,
        commit_sha=commit_sha,
        agent_run_id=agent_run_id,
        framework_skill_id=profile.framework_skill_id,
        router=profile.router,
        language=profile.language,
        package_manager=profile.package_manager,
        build_command=profile.build_command,
        entry_points=profile.entry_points,
        integration_candidates=[c.model_dump() for c in profile.integration_candidates],
        design_tokens=profile.design_tokens.model_dump(),
        protected_paths=profile.protected_paths,
        unsupported_reason=profile.unsupported_reason,
    )
