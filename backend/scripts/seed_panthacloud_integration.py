import asyncio
import sys
import uuid
from datetime import datetime, timezone

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

from app.core.database import get_session_factory
from sqlalchemy import select, text
from app.models.organization import Organization
from app.models.project import Project
from app.models.website_integration import WebsiteIntegration, WebsiteIntegrationStatus
from app.models.assistant import Assistant
from app.models.allowed_origin import AllowedOrigin
from app.models.user import User
from app.models.membership import Membership, RoleEnum
from app.core.security import hash_password

PUBLIC_KEY = "fussion_pk_panthacloud_live_frontend"

async def main():
    session_factory = get_session_factory()
    async with session_factory() as session:
        # Schema guard
        await session.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS token_version INTEGER NOT NULL DEFAULT 1;"))
        await session.commit()

        # 1. User
        stmt = select(User).where(User.email == "demo@panthacloud.com")
        user = (await session.execute(stmt)).scalar_one_or_none()
        if not user:
            user = User(
                id=uuid.uuid4(),
                email="demo@panthacloud.com",
                full_name="Abel Byamukama",
                hashed_password=hash_password("Password123!"),
                is_active=True,
                is_superuser=False,
            )
            session.add(user)
            await session.flush()
            print(f"Created user: {user.email}")
        else:
            print(f"Existing user: {user.email}")

        # 2. Organization
        stmt = select(Organization).where(Organization.slug == "panthacloud")
        org = (await session.execute(stmt)).scalar_one_or_none()
        if not org:
            org = Organization(
                id=uuid.uuid4(),
                name="Panthacloud",
                slug="panthacloud",
            )
            session.add(org)
            await session.flush()
            print(f"Created org: {org.name} ({org.slug})")
        else:
            print(f"Existing org: {org.name} ({org.slug})")

        # Membership
        stmt = select(Membership).where(
            Membership.organization_id == org.id, Membership.user_id == user.id
        )
        membership = (await session.execute(stmt)).scalar_one_or_none()
        if not membership:
            membership = Membership(
                id=uuid.uuid4(),
                organization_id=org.id,
                user_id=user.id,
                role=RoleEnum.OWNER,
            )
            session.add(membership)
            await session.flush()

        # 3. Project
        stmt = select(Project).where(
            Project.organization_id == org.id, Project.slug == "panthacloud-frontend"
        )
        project = (await session.execute(stmt)).scalar_one_or_none()
        if not project:
            project = Project(
                id=uuid.uuid4(),
                organization_id=org.id,
                name="Panthacloud Frontend",
                slug="panthacloud-frontend",
                description="The Panthacloud Next.js Studio and marketing web frontend",
            )
            session.add(project)
            await session.flush()
            print(f"Created project: {project.name} ({project.slug})")
        else:
            print(f"Existing project: {project.name} ({project.slug})")

        # 4. WebsiteIntegration
        stmt = select(WebsiteIntegration).where(WebsiteIntegration.project_id == project.id)
        integration = (await session.execute(stmt)).scalar_one_or_none()
        if not integration:
            integration = WebsiteIntegration(
                id=uuid.uuid4(),
                project_id=project.id,
                provider="github",
                repository_owner="hecmatechnologies-eng",
                repository_name="panthacloud",
                default_branch="main",
                framework_skill_id="nextjs-app-router",
                website_root_dir="/",
                widget_target_path="src/app/layout.tsx",
                status=WebsiteIntegrationStatus.CONNECTED,
                public_key=PUBLIC_KEY,
            )
            session.add(integration)
            await session.flush()
            print(f"Created integration for {integration.repository_owner}/{integration.repository_name}")
        else:
            integration.public_key = PUBLIC_KEY
            integration.repository_owner = "hecmatechnologies-eng"
            integration.repository_name = "panthacloud"
            integration.widget_target_path = "src/app/layout.tsx"
            integration.framework_skill_id = "nextjs-app-router"
            await session.flush()
            print(f"Updated integration {integration.id}")

        # 5. Assistant
        stmt = select(Assistant).where(Assistant.project_id == project.id)
        assistant = (await session.execute(stmt)).scalar_one_or_none()
        if not assistant:
            assistant = Assistant(
                id=uuid.uuid4(),
                project_id=project.id,
                name="Panthacloud Assistant",
                welcome_message="Hi! I am the Panthacloud Assistant. Ask me anything about Panthacloud!",
                system_instructions=(
                    "You are the Panthacloud AI Assistant. You help visitors and engineers understand "
                    "Panthacloud — the autonomous AI integration engineer that connects to web codebases, "
                    "analyzes frameworks and design tokens, and safely deploys AI assistants with "
                    "knowledge grounding and automated pull requests."
                ),
                brand_color="#7415E0",
                text_color="#FFFFFF",
                is_enabled=True,
            )
            session.add(assistant)
            await session.flush()
            print(f"Created assistant: {assistant.name}")
        else:
            assistant.is_enabled = True
            assistant.name = "Panthacloud Assistant"
            assistant.brand_color = "#7415E0"
            assistant.welcome_message = "Hi! I am the Panthacloud Assistant. Ask me anything about Panthacloud!"
            assistant.system_instructions = (
                "You are the Panthacloud AI Assistant. You help visitors and engineers understand "
                "Panthacloud — the autonomous AI integration engineer that connects to web codebases, "
                "analyzes frameworks and design tokens, and safely deploys AI assistants with "
                "knowledge grounding and automated pull requests."
            )
            await session.flush()
            print(f"Updated assistant: {assistant.name}")

        # 6. Allowed Origins
        origins_to_add = ["http://localhost:3000", "http://127.0.0.1:3000"]
        for o_url in origins_to_add:
            stmt = select(AllowedOrigin).where(
                AllowedOrigin.integration_id == integration.id,
                AllowedOrigin.origin == o_url,
            )
            ao = (await session.execute(stmt)).scalar_one_or_none()
            if not ao:
                ao = AllowedOrigin(
                    id=uuid.uuid4(),
                    integration_id=integration.id,
                    origin=o_url,
                    is_verified=True,
                    source="manual",
                )
                session.add(ao)
                print(f"Added allowed origin: {o_url}")
            else:
                ao.is_verified = True
                print(f"Allowed origin already exists: {o_url}")

        await session.commit()
        print("Database seeding completed successfully!")

if __name__ == "__main__":
    asyncio.run(main())
