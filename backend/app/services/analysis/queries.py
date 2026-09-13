"""Read-side queries over persisted analyses.

Shared by the control plane (which serves the latest analysis and refuses an unsupported repository)
and the integration pipeline (which refuses before doing any work), so the "latest analysis" is
defined in exactly one place.
"""

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.website_analysis import WebsiteAnalysis


async def get_latest_analysis(
    db: AsyncSession, integration_id: uuid.UUID
) -> WebsiteAnalysis | None:
    """The most recent analysis for an integration, or None if it has never been analysed."""
    stmt = (
        select(WebsiteAnalysis)
        .where(WebsiteAnalysis.integration_id == integration_id)
        .order_by(WebsiteAnalysis.created_at.desc(), WebsiteAnalysis.id.desc())
        .limit(1)
    )
    return (await db.execute(stmt)).scalar_one_or_none()
