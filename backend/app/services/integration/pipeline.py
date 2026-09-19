import asyncio
import logging
import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.protected_paths import protected_reason
from app.core.tasks import create_cancellation_event, register_task
from app.models.assistant import Assistant
from app.models.audit_event import AuditEvent
from app.models.knowledge import KnowledgeBase
from app.models.project import Project
from app.models.website_integration import (
    IntegrationRun,
    IntegrationRunStatus,
    WebsiteIntegration,
    WebsiteIntegrationStatus,
)
from app.services.analysis.queries import get_latest_analysis
from app.services.audit import record_audit as _record_audit
from app.services.integration.artifacts import WidgetInjectionError, generate_artifacts
from app.services.integration.changeset import build_change_set
from app.services.integration.credentials import GitHubCredentialError, resolve_github_token
from app.services.integration.github import get_git_provider
from app.services.integration.planner import IntegrationPlanner
from app.services.integration.sandbox import LocalWorkspaceProvider
from app.services.integration.validation import StaticValidationError, StaticValidator

logger = logging.getLogger("fussion.integration.pipeline")


class IntegrationRefusedError(Exception):
    """The integration was declined because its configuration cannot be applied safely."""


class IntegrationPipeline:
    def __init__(self, workspace_provider: LocalWorkspaceProvider | None = None) -> None:
        self.workspace = workspace_provider or LocalWorkspaceProvider()

    async def execute(
        self,
        db: AsyncSession,
        org_id: uuid.UUID,
        project: Project,
        integration: WebsiteIntegration,
        user_id: uuid.UUID | None = None,
    ) -> IntegrationRun:
        # Resolve the credential: an installation token for an App-linked integration, else the
        # decrypted PAT. A failure here is a configuration problem, refused before any work.
        try:
            raw_token = await resolve_github_token(integration)
        except GitHubCredentialError as exc:
            raise IntegrationRefusedError(str(exc)) from exc

        # Fetch assistant configuration
        stmt_asst = select(Assistant).where(Assistant.project_id == project.id)
        asst_result = await db.execute(stmt_asst)
        assistant = asst_result.scalar_one_or_none()
        asst_data: dict[str, Any] = {}
        if assistant:
            asst_data = {
                "id": str(assistant.id),
                "name": assistant.name,
                "welcome_message": assistant.welcome_message,
                "brand_color": assistant.brand_color,
                "text_color": assistant.text_color,
                "position": assistant.position.value if hasattr(assistant.position, "value") else str(assistant.position),
                "avatar_url": assistant.avatar_url,
                "starter_prompt": assistant.starter_prompt,
                "is_enabled": assistant.is_enabled,
            }

        # Check knowledge base status
        stmt_kb = select(KnowledgeBase).where(KnowledgeBase.project_id == project.id)
        kb_result = await db.execute(stmt_kb)
        kb = kb_result.scalar_one_or_none()
        has_kb = bool(kb and len(kb.documents) > 0) if kb else False

        # A repository the analyst refused is refused before any work (acceptance #10): no sandbox
        # is allocated and no run is recorded for a repository Fussion will not integrate.
        latest_analysis = await get_latest_analysis(db, integration.id)
        if latest_analysis and latest_analysis.unsupported_reason:
            raise IntegrationRefusedError(
                f"This repository cannot be integrated: {latest_analysis.unsupported_reason}"
            )

        run_id = uuid.uuid4()
        short_run = run_id.hex[:8]
        branch_name = f"fussion/integration/{short_run}"

        cancel_event = create_cancellation_event()
        current_task = asyncio.current_task()
        if current_task is not None:
            await register_task(run_id, current_task, cancel_event)

        def _assert_not_cancelled() -> None:
            if cancel_event.is_set():
                raise asyncio.CancelledError(f"Integration run {run_id} cancelled.")

        # 1. Allocate sandbox
        sandbox_path, sandbox_ref = self.workspace.allocate(org_id, project.id, run_id)

        # 2. Record initial IntegrationRun (the plan is recorded once the target has been read)
        run = IntegrationRun(
            id=run_id,
            integration_id=integration.id,
            status=IntegrationRunStatus.RUNNING,
            branch_name=branch_name,
            sandbox_ref=sandbox_ref,
            started_at=datetime.now(UTC),
        )
        db.add(run)
        integration.status = WebsiteIntegrationStatus.GENERATING
        await db.commit()
        await db.refresh(run)

        await _record_audit(
            db,
            org_id,
            project.id,
            user_id,
            "integration.run.started",
            run.id,
            {"branch": branch_name, "framework_skill_id": integration.framework_skill_id},
        )

        git_provider = get_git_provider()

        try:
            # 2b. A protected target is refused before anything is read or created (FR-096,
            # CLAUDE.md §4.9). `widget_target_path` is typed by hand, so this is as likely a
            # mistake as an attack, and the validator's later check is the backstop, not the gate.
            target_reason = protected_reason(integration.widget_target_path)
            if target_reason:
                raise IntegrationRefusedError(
                    f"Widget target '{integration.widget_target_path}' is a protected path "
                    f"({target_reason}). Fussion never writes there; point the widget target at "
                    "the application shell instead."
                )

            # 3. Verify repository existence
            await git_provider.get_repository(
                integration.repository_owner,
                integration.repository_name,
                token=raw_token,
            )

            # 4. Pin the commit to build on, and read the real target at exactly that commit
            # (CLAUDE.md §4.8). The branch is later created from the same commit, so a customer
            # commit landing meanwhile surfaces as a PR conflict instead of a silent revert.
            base_sha = await git_provider.get_branch_head(
                integration.repository_owner,
                integration.repository_name,
                integration.default_branch,
                token=raw_token,
            )
            target_path = integration.widget_target_path
            original_target = await git_provider.get_file_contents(
                integration.repository_owner,
                integration.repository_name,
                target_path,
                ref=base_sha,
                token=raw_token,
            )

            # 5. Generate deterministic plan
            plan = IntegrationPlanner.generate_plan(
                framework_skill_id=integration.framework_skill_id,
                widget_target_path=target_path,
                assistant_data=asst_data,
                has_knowledge_base=has_kb,
                target_status="exists" if original_target is not None else "missing",
            )
            run.plan_summary = {**plan.model_dump(), "base_sha": base_sha}
            await db.commit()

            # A missing target is a configuration error, never an invitation to create one.
            if original_target is None:
                raise IntegrationRefusedError(
                    f"Widget target '{target_path}' was not found on branch "
                    f"'{integration.default_branch}' at commit {base_sha[:12]}. Fussion only "
                    "modifies an existing file; check the widget target path and default branch."
                )

            # 6. Pre-populate target in sandbox
            self.workspace.write_file(sandbox_path, target_path, original_target)

            # Check if autonomous CodingAgent can be invoked
            from app.llm.gateway import ModelNotConfiguredError, get_model_gateway

            try:
                gateway = get_model_gateway()
            except ModelNotConfiguredError:
                gateway = None
            generated_files = None

            if gateway is not None and getattr(settings, "ENABLE_CODING_AGENT", True) and settings.APP_ENV != "test":
                try:
                    from app.harness.context import ExecutionContext
                    from app.harness.runner import PydanticAIRunner
                    from app.services.integration.coder import execute_coding_agent
                    from app.tools.gateway import ApprovedPlan, ToolGateway
                    from app.tools.registry import registry as global_registry

                    context = ExecutionContext(
                        organization_id=org_id,
                        project_id=project.id,
                        repository_id=None,
                        environment=settings.APP_ENV,
                        agent_name="coding_agent",
                        agent_version="1.0.0",
                        capabilities=frozenset({"repository.read", "workspace.write"}),
                        integration_id=integration.id,
                        commit_sha=base_sha,
                        workspace_reference=str(sandbox_path),
                    )
                    approved_plan = ApprovedPlan(
                        plan_id=str(run_id), approved_by=user_id or org_id
                    )
                    tool_gateway = ToolGateway(global_registry)
                    runner = PydanticAIRunner()

                    _, generated_files = await execute_coding_agent(
                        db,
                        context=context,
                        plan=plan,
                        approved_plan=approved_plan,
                        sandbox_path=sandbox_path,
                        integration=integration,
                        assistant_data=asst_data,
                        original_target=original_target,
                        runner=runner,
                        gateway=gateway,
                        tool_gateway=tool_gateway,
                        registry=global_registry,
                        workspace_provider=self.workspace,
                    )
                except Exception as exc:  # noqa: BLE001 - Resilient fallback to deterministic generator
                    logger.warning(
                        "Autonomous CodingAgent failed (%s), falling back to deterministic artifact generator",
                        exc,
                    )
                    generated_files = None

            # Fallback to deterministic generator if CodingAgent wasn't run or failed
            if not generated_files:
                try:
                    generated_files = generate_artifacts(
                        public_key=integration.public_key,
                        script_url=settings.widget_script_url,
                        assistant_data=asst_data,
                        framework_skill_id=integration.framework_skill_id,
                        widget_target_path=target_path,
                        existing_target_content=original_target,
                    )
                except WidgetInjectionError as exc:
                    raise IntegrationRefusedError(
                        f"Cannot integrate into '{target_path}': {exc}"
                    ) from exc

            # 6b. Record the exact change set this run generated, so the Studio serves what the pull
            # request contains rather than re-deriving it (C12, CLAUDE.md §3.7). Recorded before
            # validation, so a run that later fails still shows what it had generated.
            run.change_set = build_change_set(
                generated_files,
                plan.files_to_create,
                {target_path: original_target},
            )

            # 7. Write files into sandbox
            for rel_path, content in generated_files.items():
                self.workspace.write_file(sandbox_path, rel_path, content)

            # 8. Static validation
            integration.status = WebsiteIntegrationStatus.VALIDATING
            await db.commit()

            issues = StaticValidator.validate(
                integration.framework_skill_id,
                plan,
                generated_files,
                original_files={target_path: original_target},
            )
            if issues:
                raise RuntimeError(f"Static validation failed: {'; '.join(issues)}")

            run.status = IntegrationRunStatus.VALIDATING
            await db.commit()

            await _record_audit(
                db,
                org_id,
                project.id,
                user_id,
                "integration.run.validated",
                run.id,
                {"files_count": len(generated_files)},
            )

            # 9. Create integration branch
            _assert_not_cancelled()
            await git_provider.create_branch(
                owner=integration.repository_owner,
                repo=integration.repository_name,
                base_branch=integration.default_branch,
                new_branch=branch_name,
                token=raw_token,
                base_sha=base_sha,
            )

            # 10. Commit changes
            _assert_not_cancelled()
            commit_message = f"feat(fussion): integrate assistant widget [run: {short_run}]"
            commit_sha = await git_provider.commit_files(
                owner=integration.repository_owner,
                repo=integration.repository_name,
                branch=branch_name,
                commit_message=commit_message,
                files=generated_files,
                token=raw_token,
            )

            # 11. Create Pull Request
            _assert_not_cancelled()
            pr_title = "Integrate Fussion Assistant"
            pr_body = f"""## Fussion Assistant Integration

This automated Pull Request adds the Fussion storefront assistant integration for **{project.name}**.

### Changes Summary
- Framework: `{integration.framework_skill_id}`
- Files created: `{', '.join(plan.files_to_create)}`
- Files modified: `{', '.join(plan.files_to_modify)}`

### Assistant Blueprint
- Name: **{asst_data.get('name', 'Fussion Assistant')}**
- Position: `{asst_data.get('position', 'BOTTOM_RIGHT')}`
- Knowledge Base: `{'Connected' if has_kb else 'Not connected (Empty)'}`

### What Fussion checked
- Static validation: **passed** — every changed path was declared in the plan, existing content
  outside Fussion's marked blocks is unchanged, and the generated code carries no credentials.
- Generation: **deterministic** — no AI model was involved in producing this change.
- Your default branch: **untouched** — these commits are on `{branch_name}`.

### What Fussion did NOT check
- **Fussion did not install dependencies, type-check, or build your project.** Please verify
  locally before merging.

---
*Opened by Fussion. Human review and approval are required before merge.*
"""
            pr_data = await git_provider.create_pull_request(
                owner=integration.repository_owner,
                repo=integration.repository_name,
                title=pr_title,
                body=pr_body,
                head_branch=branch_name,
                base_branch=integration.default_branch,
                token=raw_token,
            )

            # 12. Update run & integration records to completion
            _assert_not_cancelled()
            now = datetime.now(UTC)
            run.status = IntegrationRunStatus.PR_CREATED
            run.commit_sha = commit_sha
            run.pull_request_number = pr_data.get("number")
            run.pull_request_url = pr_data.get("html_url")
            run.generated_files_count = len(plan.files_to_create)
            run.modified_files_count = len(plan.files_to_modify)
            run.completed_at = now

            integration.status = WebsiteIntegrationStatus.PR_CREATED
            integration.integration_branch = branch_name
            integration.last_error = None
            integration.last_success_at = now
            await db.commit()
            await db.refresh(run)

            await _record_audit(
                db,
                org_id,
                project.id,
                user_id,
                "integration.pull_request.created",
                run.id,
                {
                    "pr_number": run.pull_request_number,
                    "pr_url": run.pull_request_url,
                    "commit_sha": run.commit_sha,
                },
            )

            return run

        except (asyncio.CancelledError, Exception) as exc:
            now = datetime.now(UTC)
            if isinstance(exc, asyncio.CancelledError):
                logger.info(f"Integration pipeline run {run_id} cancelled by user request.")
                run.status = IntegrationRunStatus.CANCELLED
                run.completed_at = now
                integration.status = WebsiteIntegrationStatus.CONNECTED
                await db.commit()
                await db.refresh(run)
                await _record_audit(
                    db,
                    org_id,
                    project.id,
                    user_id,
                    "integration.run.cancelled",
                    run.id,
                    {"reason": "Cancelled by user request."},
                )
                raise

            error_msg = str(exc)
            refused = isinstance(exc, (IntegrationRefusedError, StaticValidationError))
            if refused:
                logger.warning(f"Integration pipeline run {run_id} refused: {error_msg}")
            else:
                logger.error(f"Integration pipeline run {run_id} failed: {error_msg}")

            run.status = IntegrationRunStatus.FAILED
            run.error_message = error_msg
            run.completed_at = now

            integration.status = WebsiteIntegrationStatus.FAILED
            integration.last_error = error_msg
            await db.commit()
            await db.refresh(run)

            await _record_audit(
                db,
                org_id,
                project.id,
                user_id,
                "integration.run.refused" if refused else "integration.run.failed",
                run.id,
                {"error": error_msg[:500]},
            )
            raise

        finally:
            # Clean up sandbox workspace files safely
            self.workspace.cleanup(sandbox_path)


pipeline_service = IntegrationPipeline()
