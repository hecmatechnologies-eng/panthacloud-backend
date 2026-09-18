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
    model_settings,
    organizations,
    projects,
    public_chat,
    public_widget,
    repositories,
    snapshots,
    studio_events,
    webhooks,
    website_integrations,
    workspace,
)

api_v1_router = APIRouter()
api_v1_router.include_router(health.router)
api_v1_router.include_router(auth.router)
api_v1_router.include_router(organizations.router)
api_v1_router.include_router(memberships.router)
api_v1_router.include_router(model_settings.router)
api_v1_router.include_router(projects.router)
api_v1_router.include_router(workspace.router)
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
# GitHub and third-party webhooks
api_v1_router.include_router(webhooks.router, prefix="/webhooks")
# Runtime plane: unauthenticated, tenanted by public key + Origin (B4).
api_v1_router.include_router(public_chat.router, prefix="/public")
# The widget bundle itself is public and unauthenticated (B8); it is a classic script, not an API.
api_v1_router.include_router(public_widget.router, prefix="/public")
