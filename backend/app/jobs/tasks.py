"""ARQ async background tasks for Panthacloud.

Runs long-running repository analysis and integration pipelines asynchronously off the web
API event loop, saving CPU and event-loop time for client HTTP requests.
"""

import logging
import uuid
from typing import Any

from sqlalchemy import select

from app.core.database import get_session_factory
from app.models.organization import Organization
from app.models.project import Project
from app.models.website_integration import WebsiteIntegration
from app.services.analysis.analysis_service import analyze_website_integration
from app.services.audit import record_audit
from app.services.integration.pipeline import pipeline_service

logger = logging.getLogger("fussion.jobs.tasks")


async def analyze_website_integration_task(
    ctx: dict[str, Any],
    org_id: str,
    proj_id: str,
    integration_id: str,
) -> dict[str, Any]:
    """Execute repository analysis for a website integration as a background task."""
    logger.info("Starting background analysis task for integration %s", integration_id)
    session_factory = get_session_factory()

    async with session_factory() as db:
        org = await db.get(Organization, uuid.UUID(org_id))
        project = await db.get(Project, uuid.UUID(proj_id))
        stmt = select(WebsiteIntegration).where(WebsiteIntegration.id == uuid.UUID(integration_id))
        integration = (await db.execute(stmt)).scalar_one_or_none()

        if not org or not project or not integration:
            err = f"Entity not found: org={bool(org)}, proj={bool(project)}, int={bool(integration)}"
            logger.error(err)
            return {"status": "failed", "error": err}

        await record_audit(
            db,
            org.id,
            project.id,
            None,
            "website.analysis.started",
            integration.id,
            {"integration_id": str(integration.id)},
        )

        try:
            analysis = await analyze_website_integration(
                db, integration=integration, organization=org, project=project
            )
            await record_audit(
                db,
                org.id,
                project.id,
                None,
                "website.analysis.completed",
                integration.id,
                {
                    "analysis_id": str(analysis.id),
                    "commit_sha": analysis.commit_sha,
                    "framework_skill_id": analysis.framework_skill_id,
                },
            )
            return {
                "status": "completed",
                "analysis_id": str(analysis.id),
                "framework_skill_id": analysis.framework_skill_id,
                "commit_sha": analysis.commit_sha,
            }
        except Exception as exc:
            logger.exception("Analysis background task failed")
            await record_audit(
                db,
                org.id,
                project.id,
                None,
                "website.analysis.failed",
                integration.id,
                {"error": str(exc)},
            )
            return {"status": "failed", "error": str(exc)}


async def execute_integration_pipeline_task(
    ctx: dict[str, Any],
    org_id: str,
    proj_id: str,
    integration_id: str,
    user_id: str | None = None,
) -> dict[str, Any]:
    """Execute the full integration pipeline (sandbox, code generation, PR) in the background."""
    logger.info("Starting background integration pipeline for integration %s", integration_id)
    session_factory = get_session_factory()

    async with session_factory() as db:
        project = await db.get(Project, uuid.UUID(proj_id))
        stmt = select(WebsiteIntegration).where(WebsiteIntegration.id == uuid.UUID(integration_id))
        integration = (await db.execute(stmt)).scalar_one_or_none()

        if not project or not integration:
            err = f"Entity not found: proj={bool(project)}, int={bool(integration)}"
            logger.error(err)
            return {"status": "failed", "error": err}

        u_id = uuid.UUID(user_id) if user_id else None
        try:
            run = await pipeline_service.execute(
                db=db,
                org_id=uuid.UUID(org_id),
                project=project,
                integration=integration,
                user_id=u_id,
            )
            return {
                "status": "completed",
                "run_id": str(run.id),
                "run_status": run.status.value if hasattr(run.status, "value") else str(run.status),
            }
        except Exception as exc:
            logger.exception("Pipeline execution background task failed")
            return {"status": "failed", "error": str(exc)}
