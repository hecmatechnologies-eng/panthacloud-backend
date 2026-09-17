import logging
import uuid
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Response, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import (
    get_current_project,
    get_current_user,
    get_current_website_integration,
    require_permission,
)
from app.core.database import get_db
from app.core.permissions import Permission
from app.core.secrets import secret_store
from app.core.tasks import cancel_task
from app.models.assistant import Assistant
from app.models.github_installation import GitHubInstallation
from app.models.knowledge import KnowledgeBase
from app.models.membership import Membership, RoleEnum
from app.models.organization import Organization
from app.models.project import Project
from app.models.user import User
from app.models.website_integration import (
    IntegrationRun,
    IntegrationRunStatus,
    WebsiteIntegration,
    WebsiteIntegrationStatus,
)
from app.schemas.website_analysis import AnalysisJobResponse, WebsiteAnalysisRead
from app.schemas.website_integration import (
    DiffFileItem,
    IntegrationPlanPayload,
    IntegrationRunRead,
    PullRequestInfo,
    RunDiffPayload,
    TargetStatus,
    ValidationResultPayload,
    WebsiteIntegrationCreate,
    WebsiteIntegrationRead,
    WebsiteIntegrationUpdate,
)
from app.services.analysis.analysis_service import analyze_website_integration
from app.services.analysis.queries import get_latest_analysis
from app.services.audit import record_audit
from app.services.integration.credentials import (
    GitHubCredentialError,
    resolve_github_token,
)
from app.services.integration.github import (
    GitHubAPIError,
    GitHubUnavailableError,
    get_git_provider,
)
from app.services.integration.pipeline import IntegrationRefusedError, pipeline_service
from app.services.integration.planner import IntegrationPlanner

logger = logging.getLogger("fussion.integration.api")

router = APIRouter(
    tags=["Website Integrations"],
)


def to_website_integration_read(integration: WebsiteIntegration) -> WebsiteIntegrationRead:
    return WebsiteIntegrationRead(
        id=integration.id,
        project_id=integration.project_id,
        provider=integration.provider,
        repository_owner=integration.repository_owner,
        repository_name=integration.repository_name,
        default_branch=integration.default_branch,
        integration_branch=integration.integration_branch,
        framework_skill_id=integration.framework_skill_id,
        website_root_dir=integration.website_root_dir,
        widget_target_path=integration.widget_target_path,
        status=integration.status,
        has_credentials=bool(
            integration.encrypted_secrets or integration.github_installation_id is not None
        ),
        github_installation_id=integration.github_installation_id,
        public_key=integration.public_key,
        last_error=integration.last_error,
        last_success_at=integration.last_success_at,
        created_at=integration.created_at,
        updated_at=integration.updated_at,
    )


@router.get(
    "",
    response_model=WebsiteIntegrationRead,
    summary="Get current website integration configuration",
)
async def get_website_integration(
    integration: Annotated[WebsiteIntegration, Depends(get_current_website_integration)],
    tenant: Annotated[
        tuple[Organization, Membership],
        Depends(require_permission(Permission.INTEGRATION_VIEW)),
    ],
) -> WebsiteIntegrationRead:
    return to_website_integration_read(integration)


@router.post(
    "",
    response_model=WebsiteIntegrationRead,
    status_code=status.HTTP_201_CREATED,
    summary="Create or configure website integration",
)
async def create_website_integration(
    payload: WebsiteIntegrationCreate,
    project: Annotated[Project, Depends(get_current_project)],
    tenant: Annotated[
        tuple[Organization, Membership],
        Depends(require_permission(Permission.INTEGRATION_CREATE)),
    ],
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> WebsiteIntegrationRead:
    # Check if integration already exists for this project
    stmt = select(WebsiteIntegration).where(WebsiteIntegration.project_id == project.id)
    existing = (await db.execute(stmt)).scalar_one_or_none()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="A website integration is already configured for this project.",
        )

    encrypted_blob: str | None = None
    if payload.github_token:
        encrypted_blob = secret_store.encrypt({"github_token": payload.github_token})

    # An App-linked integration must reference an installation this organization owns; the caller
    # cannot attach an arbitrary installation id (step E2).
    if payload.github_installation_id is not None:
        installation = (
            await db.execute(
                select(GitHubInstallation).where(
                    GitHubInstallation.organization_id == project.organization_id,
                    GitHubInstallation.installation_id == payload.github_installation_id,
                )
            )
        ).scalar_one_or_none()
        if installation is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="That GitHub installation is not connected to this organization.",
            )

    integration = WebsiteIntegration(
        project_id=project.id,
        provider="github",
        repository_owner=payload.repository_owner.strip(),
        repository_name=payload.repository_name.strip(),
        default_branch=payload.default_branch.strip() or "main",
        framework_skill_id=payload.framework_skill_id,
        website_root_dir=payload.website_root_dir.strip() or "/",
        widget_target_path=payload.widget_target_path.strip() or "app/layout.tsx",
        status=WebsiteIntegrationStatus.CONNECTED,
        encrypted_secrets=encrypted_blob,
        github_installation_id=payload.github_installation_id,
    )
    db.add(integration)
    await db.commit()
    await db.refresh(integration)

    await record_audit(
        db,
        project.organization_id,
        project.id,
        user.id,
        "integration.created",
        integration.id,
        {
            "repository": f"{integration.repository_owner}/{integration.repository_name}",
            "framework_skill_id": integration.framework_skill_id,
        },
    )

    return to_website_integration_read(integration)


@router.patch(
    "",
    response_model=WebsiteIntegrationRead,
    summary="Update website integration configuration",
)
async def update_website_integration(
    payload: WebsiteIntegrationUpdate,
    integration: Annotated[WebsiteIntegration, Depends(get_current_website_integration)],
    tenant: Annotated[
        tuple[Organization, Membership],
        Depends(require_permission(Permission.INTEGRATION_UPDATE)),
    ],
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> WebsiteIntegrationRead:
    if payload.repository_owner is not None:
        integration.repository_owner = payload.repository_owner.strip()
    if payload.repository_name is not None:
        integration.repository_name = payload.repository_name.strip()
    if payload.default_branch is not None:
        integration.default_branch = payload.default_branch.strip()
    if payload.framework_skill_id is not None:
        integration.framework_skill_id = payload.framework_skill_id
    if payload.website_root_dir is not None:
        integration.website_root_dir = payload.website_root_dir.strip()
    if payload.widget_target_path is not None:
        integration.widget_target_path = payload.widget_target_path.strip()

    # Credential handling: only update if explicitly provided; do not clear if omitted
    if payload.github_token is not None:
        token_str = payload.github_token.strip()
        if token_str:
            integration.encrypted_secrets = secret_store.encrypt({"github_token": token_str})
        else:
            integration.encrypted_secrets = None

    await db.commit()
    await db.refresh(integration)

    await record_audit(
        db,
        tenant[0].id,
        integration.project_id,
        user.id,
        "integration.updated",
        integration.id,
        {"repository": f"{integration.repository_owner}/{integration.repository_name}"},
    )

    return to_website_integration_read(integration)


@router.delete(
    "",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete website integration",
)
async def delete_website_integration(
    integration: Annotated[WebsiteIntegration, Depends(get_current_website_integration)],
    tenant: Annotated[
        tuple[Organization, Membership],
        Depends(require_permission(Permission.INTEGRATION_VIEW)),
    ],
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> None:
    # RBAC: OWNER, ADMIN, and MEMBER are permitted to delete; VIEWER gets 403
    if tenant[1].role not in {RoleEnum.OWNER, RoleEnum.ADMIN, RoleEnum.MEMBER}:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have permission to delete this integration.",
        )

    await record_audit(
        db,
        tenant[0].id,
        integration.project_id,
        user.id,
        "integration.deleted",
        integration.id,
        {"repository": f"{integration.repository_owner}/{integration.repository_name}"},
    )

    await db.delete(integration)
    await db.commit()


@router.post(
    "/validate",
    response_model=ValidationResultPayload,
    summary="Validate repository connection and configuration",
)
async def validate_connection(
    project: Annotated[Project, Depends(get_current_project)],
    integration: Annotated[WebsiteIntegration, Depends(get_current_website_integration)],
    tenant: Annotated[
        tuple[Organization, Membership],
        Depends(require_permission(Permission.INTEGRATION_UPDATE)),
    ],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> ValidationResultPayload:
    try:
        raw_token = await resolve_github_token(integration)
    except GitHubCredentialError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)
        ) from exc

    issues: list[str] = []
    repo_ok = False
    git_provider = get_git_provider()

    try:
        await git_provider.get_repository(
            integration.repository_owner,
            integration.repository_name,
            token=raw_token,
        )
        repo_ok = True
    except GitHubAPIError as exc:
        issues.append(f"Repository connection check failed: {exc}")
    except (OSError, RuntimeError) as exc:
        issues.append(f"Network error during repository check: {exc}")

    # Check assistant configuration
    stmt_asst = select(Assistant).where(Assistant.project_id == project.id)
    assistant = (await db.execute(stmt_asst)).scalar_one_or_none()
    assistant_readiness = bool(assistant and assistant.is_enabled)
    if not assistant:
        issues.append("No assistant configured for this project.")
    elif not assistant.is_enabled:
        issues.append("Assistant is currently disabled.")

    # Check knowledge base
    stmt_kb = select(KnowledgeBase).where(KnowledgeBase.project_id == project.id)
    kb = (await db.execute(stmt_kb)).scalar_one_or_none()
    kb_readiness = bool(kb and len(kb.documents) > 0)

    is_valid = repo_ok and assistant_readiness and len(issues) == 0

    return ValidationResultPayload(
        status="VALID" if is_valid else "INVALID",
        is_valid=is_valid,
        repository=f"{integration.repository_owner}/{integration.repository_name}",
        owner=integration.repository_owner,
        repo=integration.repository_name,
        default_branch=integration.default_branch,
        framework_skill_id=integration.framework_skill_id,
        assistant_readiness=assistant_readiness,
        knowledge_base_readiness=kb_readiness,
        issues=issues,
    )


@router.get(
    "/plan",
    response_model=IntegrationPlanPayload,
    summary="Generate deterministic integration plan",
)
async def get_integration_plan(
    project: Annotated[Project, Depends(get_current_project)],
    integration: Annotated[WebsiteIntegration, Depends(get_current_website_integration)],
    tenant: Annotated[
        tuple[Organization, Membership],
        Depends(require_permission(Permission.INTEGRATION_VIEW)),
    ],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> IntegrationPlanPayload:
    stmt_asst = select(Assistant).where(Assistant.project_id == project.id)
    assistant = (await db.execute(stmt_asst)).scalar_one_or_none()
    asst_data = {"is_enabled": assistant.is_enabled} if assistant else None

    stmt_kb = select(KnowledgeBase).where(KnowledgeBase.project_id == project.id)
    kb = (await db.execute(stmt_kb)).scalar_one_or_none()
    has_kb = bool(kb and len(kb.documents) > 0)

    # A repository the analyst refused is refused here too, before any GitHub call (acceptance #10):
    # a plan for a repository Fussion will not integrate is a promise it cannot keep.
    analysis = await get_latest_analysis(db, integration.id)
    if analysis and analysis.unsupported_reason:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"This repository cannot be integrated: {analysis.unsupported_reason}",
        )

    # Resolve the branch head *first*, then read the file at that SHA — the same order the run
    # uses. Reading the path directly made a private repository, a wrong default branch and a bad
    # token all arrive as a 404, which the preview then reported as "file missing", sending the
    # user to fix a widget path that was never the problem (CLAUDE.md §3).
    #
    # A transient GitHub failure (unreachable, rate-limited) degrades the preview to "unknown";
    # the run re-checks before modifying anything. Any other failure is a configuration problem
    # the user must fix, so it is reported with its cause.
    target_status: TargetStatus = "unknown"
    provider = get_git_provider()
    try:
        token = await resolve_github_token(integration)
    except GitHubCredentialError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)
        ) from exc
    try:
        head_sha = await provider.get_branch_head(
            integration.repository_owner,
            integration.repository_name,
            integration.default_branch,
            token=token,
        )
    except GitHubUnavailableError as exc:
        logger.warning(f"Could not resolve branch head for integration {integration.id}: {exc}")
        head_sha = None
    except GitHubAPIError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"Cannot read repository '{integration.repository_owner}/"
                f"{integration.repository_name}' branch '{integration.default_branch}': {exc} "
                "Check the repository name, the default branch, and that the token can read it."
            ),
        ) from exc

    if head_sha is not None:
        try:
            target_content = await provider.get_file_contents(
                integration.repository_owner,
                integration.repository_name,
                integration.widget_target_path,
                ref=head_sha,
                token=token,
            )
            target_status = "exists" if target_content is not None else "missing"
        except GitHubUnavailableError as exc:
            logger.warning(f"Could not verify widget target for integration {integration.id}: {exc}")
        except GitHubAPIError as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Cannot read the widget target: {exc}",
            ) from exc

    plan = IntegrationPlanner.generate_plan(
        framework_skill_id=integration.framework_skill_id,
        widget_target_path=integration.widget_target_path,
        assistant_data=asst_data,
        has_knowledge_base=has_kb,
        target_status=target_status,
    )

    # A moved repository is a warning, not a refusal: the detected target may still be valid, and a
    # legitimate run must not be blocked by a commit that landed elsewhere. Re-analysis is the fix.
    if analysis and head_sha is not None and analysis.commit_sha != head_sha:
        plan.warnings.append(
            "The repository changed since it was analysed "
            f"(analysed {analysis.commit_sha[:12]}, head {head_sha[:12]}). Re-run the analysis to "
            "refresh the detected framework and integration point."
        )
    return plan


@router.post(
    "/runs",
    response_model=IntegrationRunRead,
    status_code=status.HTTP_201_CREATED,
    summary="Start an integration pipeline run",
)
async def start_integration_run(
    project: Annotated[Project, Depends(get_current_project)],
    integration: Annotated[WebsiteIntegration, Depends(get_current_website_integration)],
    tenant: Annotated[
        tuple[Organization, Membership],
        Depends(require_permission(Permission.INTEGRATION_EXECUTE)),
    ],
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> IntegrationRunRead:
    try:
        run = await pipeline_service.execute(
            db=db,
            org_id=tenant[0].id,
            project=project,
            integration=integration,
            user_id=user.id,
        )
        return IntegrationRunRead.model_validate(run)
    except IntegrationRefusedError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"Integration refused: {exc}",
        ) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Integration pipeline execution failed: {exc}",
        ) from exc


@router.get(
    "/runs",
    response_model=list[IntegrationRunRead],
    summary="List historical integration runs",
)
async def list_integration_runs(
    integration: Annotated[WebsiteIntegration, Depends(get_current_website_integration)],
    tenant: Annotated[
        tuple[Organization, Membership],
        Depends(require_permission(Permission.INTEGRATION_VIEW)),
    ],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> list[IntegrationRunRead]:
    stmt = (
        select(IntegrationRun)
        .where(IntegrationRun.integration_id == integration.id)
        .order_by(IntegrationRun.created_at.desc())
    )
    result = await db.execute(stmt)
    runs = result.scalars().all()
    return [IntegrationRunRead.model_validate(r) for r in runs]


@router.get(
    "/runs/{run_id}",
    response_model=IntegrationRunRead,
    summary="Get integration run details",
)
async def get_integration_run(
    run_id: uuid.UUID,
    integration: Annotated[WebsiteIntegration, Depends(get_current_website_integration)],
    tenant: Annotated[
        tuple[Organization, Membership],
        Depends(require_permission(Permission.INTEGRATION_VIEW)),
    ],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> IntegrationRunRead:
    stmt = select(IntegrationRun).where(
        IntegrationRun.id == run_id,
        IntegrationRun.integration_id == integration.id,
    )
    result = await db.execute(stmt)
    run = result.scalar_one_or_none()
    if not run:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Integration run not found.",
        )
    return IntegrationRunRead.model_validate(run)


@router.post(
    "/runs/{run_id}/cancel",
    response_model=IntegrationRunRead,
    summary="Cancel active or pending integration run",
)
async def cancel_integration_run(
    run_id: uuid.UUID,
    integration: Annotated[WebsiteIntegration, Depends(get_current_website_integration)],
    tenant: Annotated[
        tuple[Organization, Membership],
        Depends(require_permission(Permission.INTEGRATION_EXECUTE)),
    ],
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> IntegrationRunRead:
    stmt = select(IntegrationRun).where(
        IntegrationRun.id == run_id,
        IntegrationRun.integration_id == integration.id,
    )
    result = await db.execute(stmt)
    run = result.scalar_one_or_none()
    if not run:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Integration run not found.",
        )

    if run.status in (IntegrationRunStatus.PENDING, IntegrationRunStatus.RUNNING, IntegrationRunStatus.VALIDATING):
        run.status = IntegrationRunStatus.CANCELLED
        run.completed_at = datetime.now(UTC)
        integration.status = WebsiteIntegrationStatus.CONNECTED
        await db.commit()
        await db.refresh(run)

        # Signal and abort the in-flight pipeline task
        await cancel_task(run.id)

        await record_audit(
            db,
            tenant[0].id,
            integration.project_id,
            user.id,
            "integration.run.cancelled",
            run.id,
            {"run_id": str(run.id)},
        )

    return IntegrationRunRead.model_validate(run)


@router.get(
    "/runs/{run_id}/diff",
    response_model=RunDiffPayload,
    summary="Retrieve generated file diff for an integration run",
)
async def get_run_diff(
    run_id: uuid.UUID,
    project: Annotated[Project, Depends(get_current_project)],
    integration: Annotated[WebsiteIntegration, Depends(get_current_website_integration)],
    tenant: Annotated[
        tuple[Organization, Membership],
        Depends(require_permission(Permission.INTEGRATION_VIEW)),
    ],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> RunDiffPayload:
    stmt = select(IntegrationRun).where(
        IntegrationRun.id == run_id,
        IntegrationRun.integration_id == integration.id,
    )
    result = await db.execute(stmt)
    run = result.scalar_one_or_none()
    if not run:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Integration run not found.",
        )

    # Served from what this run recorded, never re-derived (CLAUDE.md §3.1, §3.7). The change set
    # is computed once at generation time from the exact bytes the run wrote, so what the Studio
    # shows is what the pull request contains.
    plan_summary = run.plan_summary or {}
    change_set = run.change_set or []

    if change_set:
        diff_items = [
            DiffFileItem(
                path=str(item.get("path", "")),
                action=str(item.get("action", "")),
                diff=str(item.get("diff", "")),
            )
            for item in change_set
        ]
    else:
        # A run that predates C12, or one refused or failed before generating anything: report the
        # paths it planned and point at the pull request for any content.
        created = [str(path) for path in plan_summary.get("files_to_create", [])]
        modified = [str(path) for path in plan_summary.get("files_to_modify", [])]
        diff_items = [
            DiffFileItem(
                path=path,
                action=action,
                diff=(
                    "This run recorded no change set. If it opened a pull request, review it for "
                    "the exact diff Fussion committed."
                ),
            )
            for action, paths in (("create", created), ("modify", modified))
            for path in paths
        ]

    if not diff_items:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "This run recorded no file plan, so there is nothing to show. It was refused or "
                "failed before generating changes; see the run's error message."
            ),
        )

    base_sha = str(plan_summary.get("base_sha", ""))[:12]
    summary = (
        f"{len(diff_items)} file(s) on branch {run.branch_name}"
        + (f", built on commit {base_sha}" if base_sha else "")
    )
    return RunDiffPayload(run_id=run.id, files=diff_items, summary=summary)


@router.get(
    "/runs/{run_id}/pull-request",
    response_model=PullRequestInfo,
    summary="Retrieve Pull Request metadata for an integration run",
)
async def get_run_pull_request(
    run_id: uuid.UUID,
    integration: Annotated[WebsiteIntegration, Depends(get_current_website_integration)],
    tenant: Annotated[
        tuple[Organization, Membership],
        Depends(require_permission(Permission.INTEGRATION_VIEW)),
    ],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> PullRequestInfo:
    stmt = select(IntegrationRun).where(
        IntegrationRun.id == run_id,
        IntegrationRun.integration_id == integration.id,
    )
    result = await db.execute(stmt)
    run = result.scalar_one_or_none()
    if not run or not run.pull_request_number:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Pull Request not found for this run.",
        )

    return PullRequestInfo(
        pull_request_number=run.pull_request_number,
        pull_request_url=run.pull_request_url,
        branch_name=run.branch_name,
        base_branch=integration.default_branch,
        title="Integrate Fussion Assistant",
    )


@router.post(
    "/analyze",
    response_model=WebsiteAnalysisRead | AnalysisJobResponse,
    summary="Analyse the repository and detect the integration profile",
)
async def analyze_website_integration_endpoint(
    response: Response,
    integration: Annotated[WebsiteIntegration, Depends(get_current_website_integration)],
    project: Annotated[Project, Depends(get_current_project)],
    tenant: Annotated[
        tuple[Organization, Membership],
        Depends(require_permission(Permission.INTEGRATION_UPDATE)),
    ],
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    run_async: Annotated[bool, Query(alias="async", description="Execute analysis asynchronously via ARQ task queue")] = False,
    prefer: Annotated[str | None, Header()] = None,
) -> WebsiteAnalysisRead | AnalysisJobResponse:
    """Clone the repository at a pinned revision, run the analyst, and persist the detected profile."""
    should_run_async = run_async or (prefer is not None and "respond-async" in prefer.lower())
    if should_run_async:
        from app.jobs.queue import enqueue_analysis

        job_id = await enqueue_analysis(
            org_id=tenant[0].id,
            proj_id=project.id,
            integration_id=integration.id,
        )
        if job_id:
            response.status_code = status.HTTP_202_ACCEPTED
            return AnalysisJobResponse(
                status="queued",
                job_id=job_id,
                poll_url=f"/api/v1/organizations/{tenant[0].id}/projects/{project.id}/website-integrations/analyze/jobs/{job_id}",
                events_url=f"/api/v1/organizations/{tenant[0].id}/projects/{project.id}/events/stream",
            )
        logger.info("ARQ Redis unconfigured or unavailable; executing analysis synchronously")

    from app.harness.budget import RunBudgetExceeded
    from app.harness.runner import AgentBudgetExceededError, AgentRunnerError, StructuredOutputError
    from app.llm.gateway import BudgetExceededError, ModelNotConfiguredError
    from app.services.analysis.clone import RepositoryCloneError

    try:
        analysis = await analyze_website_integration(
            db, integration=integration, organization=tenant[0], project=project
        )
    except ModelNotConfiguredError:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="No model provider is configured; the analysis cannot run.",
        ) from None
    except BudgetExceededError:
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail="This organization has reached its model spend budget.",
        ) from None
    except (RepositoryCloneError, TimeoutError):
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="The repository could not be read. Check the repository, branch and token.",
        ) from None
    except GitHubCredentialError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)
        ) from exc
    except (StructuredOutputError, AgentRunnerError):
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="The analyst could not produce a valid profile. Please try again.",
        ) from None
    except (AgentBudgetExceededError, RunBudgetExceeded) as exc:
        # A run budget overrun is an outcome the user can act on, not an opaque server fault. It
        # reached the UI as "an unexpected error occurred" while the record held the real reason.
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"The analysis stopped at its run budget: {exc}",
        ) from exc

    await record_audit(
        db,
        tenant[0].id,
        project.id,
        user.id,
        "website.analysis.completed",
        integration.id,
        {"commit_sha": analysis.commit_sha, "framework_skill_id": analysis.framework_skill_id},
    )
    return WebsiteAnalysisRead.model_validate(analysis)


@router.get(
    "/analyze/jobs/{job_id}",
    summary="Check status and result of background repository analysis job",
)
async def get_analysis_job_status(
    job_id: str,
    integration: Annotated[WebsiteIntegration, Depends(get_current_website_integration)],
    project: Annotated[Project, Depends(get_current_project)],
    tenant: Annotated[
        tuple[Organization, Membership],
        Depends(require_permission(Permission.INTEGRATION_VIEW)),
    ],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict[str, object]:
    """Return status, completion state, and detected profile of a background analysis job."""
    from typing import Any

    from app.jobs.queue import get_job_info
    from app.models.website_analysis import WebsiteAnalysis

    info: dict[str, Any] | None = await get_job_info(job_id)
    if info is not None:
        if info.get("status") == "complete":
            stmt = (
                select(WebsiteAnalysis)
                .where(WebsiteAnalysis.integration_id == integration.id)
                .order_by(WebsiteAnalysis.created_at.desc())
                .limit(1)
            )
            analysis = (await db.execute(stmt)).scalar_one_or_none()
            if analysis:
                info["analysis"] = WebsiteAnalysisRead.model_validate(analysis).model_dump(mode="json")
        return info

    stmt = (
        select(WebsiteAnalysis)
        .where(WebsiteAnalysis.integration_id == integration.id)
        .order_by(WebsiteAnalysis.created_at.desc())
        .limit(1)
    )
    analysis = (await db.execute(stmt)).scalar_one_or_none()
    if analysis:
        return {
            "job_id": job_id,
            "status": "complete",
            "analysis": WebsiteAnalysisRead.model_validate(analysis).model_dump(mode="json"),
        }

    return {
        "job_id": job_id,
        "status": "not_found",
    }


@router.get(
    "/analysis",
    response_model=WebsiteAnalysisRead | None,
    summary="Get the latest analysis for this integration",
)
async def get_latest_website_analysis(
    integration: Annotated[WebsiteIntegration, Depends(get_current_website_integration)],
    tenant: Annotated[
        tuple[Organization, Membership],
        Depends(require_permission(Permission.INTEGRATION_VIEW)),
    ],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> WebsiteAnalysisRead | None:
    analysis = await get_latest_analysis(db, integration.id)
    return WebsiteAnalysisRead.model_validate(analysis) if analysis else None
