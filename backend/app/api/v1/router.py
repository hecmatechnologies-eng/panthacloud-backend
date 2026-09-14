from fastapi import APIRouter

from app.api.v1.endpoints import (
    agent_runs,
    allowed_origins,
    assistant,
    auth,
    discovery,
    github_app,
    health,
    integrations,
    knowledge,
    memberships,
    organizations,
    projects,
    public_chat,
    repositories,
    snapshots,
    studio_events,
    website_integrations,
)

api_v1_router = APIRouter()
api_v1_router.include_router(health.router)
api_v1_router.include_router(auth.router)
api_v1_router.include_router(organizations.router)
api_v1_router.include_router(memberships.router)
api_v1_router.include_router(projects.router)
api_v1_router.include_router(studio_events.router)
api_v1_router.include_router(integrations.router)
api_v1_router.include_router(repositories.router)
api_v1_router.include_router(snapshots.router)
api_v1_router.include_router(discovery.router)
api_v1_router.include_router(knowledge.router)
api_v1_router.include_router(assistant.router)
api_v1_router.include_router(github_app.router)
api_v1_router.include_router(agent_runs.router)
api_v1_router.include_router(agent_runs.usage_router)
api_v1_router.include_router(agent_runs.budget_router)
api_v1_router.include_router(
    website_integrations.router,
    prefix="/organizations/{org_id}/projects/{project_id}/website-integrations",
)
api_v1_router.include_router(
    allowed_origins.router,
    prefix="/organizations/{org_id}/projects/{project_id}/website-integrations/origins",
)
api_v1_router.include_router(
    website_integrations.router,
    prefix="/organizations/{org_id}/projects/{project_id}/website-integration",
)
# Runtime plane: unauthenticated, tenanted by public key + Origin (B4).
api_v1_router.include_router(public_chat.router, prefix="/public")
