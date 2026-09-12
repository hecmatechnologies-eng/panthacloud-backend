import logging
import uuid
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
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
from app.core.secrets import SecretStoreError, secret_store
from app.models.assistant import Assistant
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
from app.services.audit import record_audit
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


def _decrypt_github_token(integration: WebsiteIntegration) -> str | None:
    if not integration.encrypted_secrets:
        return None
    try:
        return secret_store.decrypt(integration.encrypted_secrets).get("github_token")
    except SecretStoreError:
        # Reachable whenever the encryption key changes — e.g. development keys are now generated
        # per installation, so ciphertext stored under the old hardcoded key cannot be read. The
        # caller proceeds unauthenticated, which fails confusingly, so say why here.
        logger.warning(
            "Stored credentials for integration %s could not be decrypted with the current "
            "SECRET_ENCRYPTION_KEY; the token must be re-entered.",
            integration.id,
        )
        return None


def to_website_integration_read(integration: WebsiteIntegration) -> WebsiteIntegrationRead:
    return WebsiteIntegrationRead(
        id=integration.id,
        project_id=integration.project_id,
        provider=integration.provider,
        repository_owner=integration.repository_owner,
        repository_name=integration.repository_name,
        default_branch=integration.default_branch,
        integration_branch=integration.integration_branch,
        framework=integration.framework,
        website_root_dir=integration.website_root_dir,
        widget_target_path=integration.widget_target_path,
        status=integration.status,
        has_credentials=bool(integration.encrypted_secrets),
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

    integration = WebsiteIntegration(
        project_id=project.id,
        provider="github",
        repository_owner=payload.repository_owner.strip(),
        repository_name=payload.repository_name.strip(),
        default_branch=payload.default_branch.strip() or "main",
        framework=payload.framework,
        website_root_dir=payload.website_root_dir.strip() or "/",
        widget_target_path=payload.widget_target_path.strip() or "app/layout.tsx",
        status=WebsiteIntegrationStatus.CONNECTED,
        encrypted_secrets=encrypted_blob,
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
            "framework": integration.framework.value,
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
    if payload.framework is not None:
        integration.framework = payload.framework
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
    raw_token = _decrypt_github_token(integration)

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
        framework=integration.framework,
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
    token = _decrypt_github_token(integration)
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

    return IntegrationPlanner.generate_plan(
        framework=integration.framework,
        widget_target_path=integration.widget_target_path,
        assistant_data=asst_data,
        has_knowledge_base=has_kb,
        target_status=target_status,
    )


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

    # Served from what this run actually recorded, never re-derived. Re-deriving from the *current*
    # assistant configuration and a stub layout is what showed the Studio a file the pull request
    # never contained (CLAUDE.md §3.1), and re-deriving content now would repeat that: the run's
    # inputs were the repository at a pinned commit, which is not what the config says today.
    #
    # File *content* is not persisted yet (§3.7), so this reports the paths and actions the run
    # committed and points at the pull request for the content itself. Raising a TypeError here —
    # which is what re-deriving did — meant a 500 on every successful run.
    plan_summary = run.plan_summary or {}
    created = [str(path) for path in plan_summary.get("files_to_create", [])]
    modified = [str(path) for path in plan_summary.get("files_to_modify", [])]

    diff_items = [
        DiffFileItem(
            path=path,
            action=action,
            diff=(
                "Content is not retained for completed runs. Review the pull request for the exact "
                "diff Fussion committed."
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
        status="open",
    )
