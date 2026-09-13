import logging
import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.protected_paths import protected_reason
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
from app.services.integration.artifacts import WidgetInjectionError, generate_artifacts
from app.services.integration.changeset import build_change_set
from app.services.integration.credentials import GitHubCredentialError, resolve_github_token
from app.services.integration.github import get_git_provider
from app.services.integration.planner import IntegrationPlanner
from app.services.integration.sandbox import LocalWorkspaceProvider
from app.services.integration.validation import StaticValidator

logger = logging.getLogger("fussion.integration.pipeline")


class IntegrationRefusedError(Exception):
    """The integration was declined because its configuration cannot be applied safely."""


async def _record_audit(
    db: AsyncSession,
    org_id: uuid.UUID,
    project_id: uuid.UUID,
    user_id: uuid.UUID | None,
    event_type: str,
    resource_id: uuid.UUID,
    payload: dict[str, Any] | None = None,
) -> None:
    # Ensure secrets never leak into audit payload
    clean_payload = dict(payload or {})
    for key in ("token", "github_token", "encrypted_secrets", "secret", "password"):
        clean_payload.pop(key, None)

    event = AuditEvent(
        organization_id=org_id,
        project_id=project_id,
        user_id=user_id,
        event_type=event_type,
        resource_type="website_integration",
        resource_id=resource_id,
        payload=clean_payload,
    )
    db.add(event)
    await db.commit()


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

            # 6. Generate deterministic artifacts from the real file contents. A file with no safe
            # insertion point is refused, not guessed at: appending blind produced a layout that
            # did not compile, and the validator cannot see inside a managed block.
            try:
                generated_files = generate_artifacts(
                    project_id=project.id,
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
            await git_provider.create_branch(
                owner=integration.repository_owner,
                repo=integration.repository_name,
                base_branch=integration.default_branch,
                new_branch=branch_name,
                token=raw_token,
                base_sha=base_sha,
            )

            # 10. Commit changes
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

        except Exception as exc:
            now = datetime.now(UTC)
            error_msg = str(exc)
            refused = isinstance(exc, IntegrationRefusedError)
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
