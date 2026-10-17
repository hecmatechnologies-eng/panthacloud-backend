from fastapi import APIRouter

from app.api.v1.endpoints import (
    agent_runs,
    allowed_origins,
    assistant,
    auth,
    branding,
    channels,
    conversations,
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
    webhooks_email,
    webhooks_whatsapp,
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
# After assistant rather than beside knowledge: the inbox reads what the assistant wrote, and the
# two endpoints answer questions about the same conversations from opposite ends.
api_v1_router.include_router(conversations.router)
api_v1_router.include_router(channels.router)
api_v1_router.include_router(branding.router)
api_v1_router.include_router(github_app.router)
# The two callbacks live here as well as at the application root. GitHub's redirect URI is
# fixed by the GitHub App's settings and cannot be version-prefixed, so main.py mounts them
# bare; including them here too keeps /api/v1/github/callback working for clients and tests
# that address the versioned API like everything else. Two addresses is correct for these two
# routes and only these two.
api_v1_router.include_router(github_app.callback_router)
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
# GitHub and third-party webhooks
api_v1_router.include_router(webhooks.router, prefix="/webhooks")
api_v1_router.include_router(webhooks_whatsapp.router, prefix="/webhooks")
api_v1_router.include_router(webhooks_email.router, prefix="/webhooks")
# Runtime plane: unauthenticated, tenanted by public key + Origin (B4).
api_v1_router.include_router(public_chat.router, prefix="/public")
# The widget bundle itself is public and unauthenticated (B8); it is a classic script, not an API.
api_v1_router.include_router(public_widget.router, prefix="/public")
