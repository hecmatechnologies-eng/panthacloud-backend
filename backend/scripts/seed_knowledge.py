import asyncio
import sys
import uuid
import hashlib

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

from app.core.database import get_session_factory
from sqlalchemy import select
from app.models.organization import Organization
from app.models.project import Project
from app.models.knowledge import KnowledgeBase, KnowledgeDocument, KnowledgeChunk, DocumentStatus
from app.services.knowledge.embeddings import get_embedding_provider

OVERVIEW_TEXT = """# Panthacloud Platform Overview

Panthacloud is an autonomous AI integration engineer that connects to web application repositories and automates the integration, deployment, and operation of intelligent AI assistants on customer websites.

## Core Capabilities
- Autonomous Repository Analysis: Inspects web repositories, detects frontend frameworks (such as Next.js App Router, React, and generic HTML), and identifies the safest layout integration points (such as src/app/layout.tsx).
- Grounded AI Assistant: Answers customer inquiries accurately using on-site documents and business knowledge with explicit citations.
- Safety & Sandboxing: Validates changes against protected paths and creates PRs rather than directly modifying production branches without review.
- High-Performance Streaming: Delivers real-time token streaming via Server-Sent Events (SSE) into a shadow DOM isolated widget that never leaks CSS or cookies.
- Pricing & Economics: Go-live setup at UGX 40,000, answering plan at UGX 80,000/mo, and action plan at UGX 100,000/mo.
"""

async def main():
    session_factory = get_session_factory()
    async with session_factory() as session:
        # 1. Project
        stmt = select(Project).where(Project.slug == "panthacloud-frontend")
        project = (await session.execute(stmt)).scalar_one_or_none()
        if not project:
            print("Project panthacloud-frontend not found!")
            return

        # 2. KnowledgeBase
        stmt = select(KnowledgeBase).where(KnowledgeBase.project_id == project.id)
        kb = (await session.execute(stmt)).scalar_one_or_none()
        if not kb:
            kb = KnowledgeBase(
                id=uuid.uuid4(),
                project_id=project.id,
                name="Panthacloud Documentation",
                description="Core overview and documentation for Panthacloud",
                embedding_model="gemini-embedding-001",
                embedding_dimension=768,
            )
            session.add(kb)
            await session.flush()
            print(f"Created KnowledgeBase {kb.id}")
        else:
            kb.embedding_model = "gemini-embedding-001"
            kb.embedding_dimension = 768
            await session.flush()
            print(f"Using KnowledgeBase {kb.id}")

        # 3. Existing doc check
        stmt = select(KnowledgeDocument).where(
            KnowledgeDocument.knowledge_base_id == kb.id,
            KnowledgeDocument.filename == "panthacloud_overview.md"
        )
        doc = (await session.execute(stmt)).scalar_one_or_none()
        if not doc:
            doc_id = uuid.uuid4()
            file_hash = hashlib.sha256(OVERVIEW_TEXT.encode("utf-8")).hexdigest()
            doc = KnowledgeDocument(
                id=doc_id,
                knowledge_base_id=kb.id,
                filename="panthacloud_overview.md",
                file_hash=file_hash,
                file_size_bytes=len(OVERVIEW_TEXT.encode("utf-8")),
                content_type="text/markdown",
                status=DocumentStatus.READY,
                storage_key=f"knowledge/{project.id}/{doc_id}/panthacloud_overview.md",
            )
            session.add(doc)
            await session.flush()
            print(f"Created KnowledgeDocument {doc.id}")

            # 4. Generate Chunk and Embedding
            provider = get_embedding_provider("gemini-embedding-001", 768)
            vector = await provider.embed_text(OVERVIEW_TEXT)
            chunk = KnowledgeChunk(
                id=uuid.uuid4(),
                document_id=doc.id,
                chunk_index=0,
                text=OVERVIEW_TEXT,
                token_count=len(OVERVIEW_TEXT.split()),
                embedding=vector,
                embedding_model="gemini-embedding-001",
                metadata_={"section": "overview", "source": "panthacloud_overview.md"},
            )
            session.add(chunk)
            await session.flush()
            print("Created KnowledgeChunk with Gemini vector embeddings!")

        await session.commit()
        print("Knowledge base seeded successfully!")

if __name__ == "__main__":
    asyncio.run(main())
