# DOOM Database, Memory, and RAG

## Existing database
The project uses SQLAlchemy and a PostgreSQL connection configured through `DATABASE_URL`. The database module is `src/memory/database.py`, which exposes an SQLAlchemy engine and `SessionLocal`.

Existing tables defined in the inspected code include:
- `seen_urls`
- `daily_job_matches`
- `job_applications`
- `platform_sessions`
- `apply_queue`
- `visitors`
- `conversations`
- `messages`
- `user_memory`

Do not repurpose or overwrite these tables for document retrieval.

## pgvector migration
The Neon database was inspected as PostgreSQL 17.11. The `vector` extension was available at version 0.8.0 and was successfully enabled. The Python `pgvector` package version 0.5.1 was installed and added to `requirements.txt`.

The planned document store is a separate `doom_document_chunks` table containing source, chunk index, text content, content hash, and a 384-dimensional embedding. The selected initial embedding model is `BAAI/bge-small-en-v1.5` through FastEmbed. Verify the actual model and dimensions during ingestion.

## Previous RAG implementation
The earlier `src/memory/rag.py` used ChromaDB with `all-MiniLM-L6-v2`, 500-word chunks, and 50-word overlap. ChromaDB and Sentence Transformers were not installed in the inspected local environment, so the old RAG implementation was unavailable locally.

The migration goal is PostgreSQL + pgvector, not running two vector databases.

## Retrieval design
- Chunk Markdown, text, and PDF content.
- Store source and chunk metadata.
- Use cosine-distance retrieval.
- Add an HNSW index if supported by the Neon PostgreSQL deployment.
- Re-ingestion should replace chunks for the same source without duplicating them.
- Keep document retrieval data separate from personal profile/conversation memory.

## Retrieval evaluation
Use a fixed query set with known relevant source/chunk labels. Report Recall@K, Precision@K, MRR, and latency. Synthetic benchmark documents should be isolated from the user's knowledge documents. Do not treat synthetic benchmark scores as real-world user-document quality.
