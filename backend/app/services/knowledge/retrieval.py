from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.knowledge import DocumentStatus, KnowledgeBase, KnowledgeChunk, KnowledgeDocument
from app.schemas.knowledge import (
    KnowledgeQueryRequest,
    KnowledgeQueryResponse,
    KnowledgeQueryResultItem,
)
from app.services.knowledge.embeddings import (
    EmbeddingProviderError,
    cosine_similarity,
    get_embedding_provider,
)


async def query_knowledge_base(
    db: AsyncSession,
    kb: KnowledgeBase,
    request: KnowledgeQueryRequest,
) -> KnowledgeQueryResponse:
    """
    Semantic retrieval against the project's knowledge base.
    Restricted strictly to READY documents within this specific KnowledgeBase (FR-109: tenancy
    is a filter, not a ranking hint), and embedded with the base's own stored model.
    """
    # 1. Embed query with the same model the chunks were embedded with
    embedder = get_embedding_provider(kb.embedding_model, kb.embedding_dimension)
    query_emb = await embedder.embed_text(request.query)

    # 2. Fetch all chunks from READY documents in this knowledge base
    stmt = (
        select(KnowledgeChunk, KnowledgeDocument)
        .join(KnowledgeDocument, KnowledgeDocument.id == KnowledgeChunk.document_id)
        .where(
            KnowledgeDocument.knowledge_base_id == kb.id,
            KnowledgeDocument.status == DocumentStatus.READY,
        )
    )
    result = await db.execute(stmt)
    rows = result.all()

    # 3. Compute cosine similarities
    scored_items: list[tuple[float, KnowledgeChunk, KnowledgeDocument]] = []
    for chunk, doc in rows:
        chunk_emb: list[float] = chunk.embedding
        if len(chunk_emb) != len(query_emb):
            # A chunk embedded by a different model is unusable. Fail closed rather than score it
            # 0 and let the 0.0 default threshold pass every chunk.
            raise EmbeddingProviderError(
                "Chunk embedding dimension does not match the query; the knowledge base's "
                "embedding model is inconsistent with its chunks."
            )
        score = cosine_similarity(query_emb, chunk_emb)
        if score >= request.score_threshold:
            scored_items.append((score, chunk, doc))

    # 4. Sort descending by score
    scored_items.sort(key=lambda x: x[0], reverse=True)

    # 5. Take top_k
    top_items = scored_items[: request.top_k]

    results: list[KnowledgeQueryResultItem] = [
        KnowledgeQueryResultItem(
            chunk_id=chunk.id,
            document_id=doc.id,
            document_filename=doc.filename,
            chunk_index=chunk.chunk_index,
            page_number=chunk.page_number,
            source_location=chunk.source_location,
            text=chunk.text,
            score=round(score, 4),
        )
        for score, chunk, doc in top_items
    ]

    return KnowledgeQueryResponse(
        query=request.query,
        total_matches=len(scored_items),
        results=results,
    )
