"""
Seed DOOM's initial private knowledge base into Neon PostgreSQL + pgvector.

Run from the DOOM project root:
    $env:PYTHONPATH=(Get-Location).Path
    python evaluation/seed_doom_knowledge.py

This creates curated Markdown files under data/documents/doom_knowledge/
and indexes their chunks in the dedicated doom_document_chunks table.

It does not read or modify existing user-memory tables.
"""

from __future__ import annotations

import hashlib
import os
import re
import sys
from pathlib import Path
from typing import Iterable

from dotenv import load_dotenv
from fastembed import TextEmbedding
from sqlalchemy import text

ROOT = Path(__file__).resolve().parents[1]
DOCS_DIR = ROOT / "data" / "documents" / "doom_knowledge"
TABLE = "doom_document_chunks"
MODEL_NAME = "BAAI/bge-small-en-v1.5"
EMBEDDING_DIM = 384
CHUNK_WORDS = 450
CHUNK_OVERLAP = 60
BATCH_SIZE = 32

DOCUMENTS: dict[str, str] = {
    "doom_project_overview.md": r"""
# DOOM AI — Project Overview

## Purpose
DOOM is a personal AI assistant project with a Python/FastAPI backend, agent workflows, MCP tools, persistent memory, and integrations for productivity and job-search workflows.

## Backend and architecture
- Backend framework: FastAPI.
- Main backend application: `src/api/app.py`.
- Agent implementation: `src/agent/core.py`.
- LangGraph workflow: `src/agent/graph.py`.
- MCP tool registry: `src/tools/registry.py`.
- MCP server adapter: `src/tools/mcp_server.py`.
- Memory and database code: `src/memory/`.
- API routers: `src/api/routes/`.

The project has used a Streamable HTTP MCP endpoint at `/mcp`. The previously checked deployment health response reported 26 registered MCP tools and owner-only authentication. Treat deployment status and counts as time-sensitive and re-check before making current claims.

## Current MCP registry
The last inspected registry contained 26 tools:
`web_search`, `get_datetime`, `save_reminder`, `list_reminders`, `automate`,
`search_docs`, `ingest_docs`, `list_docs`, `call_contact`, `whatsapp_contact`,
`add_contact`, `list_contacts`, `set_profile`, `get_profile`, `whatsapp_resume`,
`read_emails`, `send_email`, `summarize_inbox`, `job_search`, `score_jd`,
`cover_letter`, `track_application`, `list_applications`, `daily_briefing`,
`find_hr_email`, and `save_lead`.

A previous resume/project description referred to 35 tools across the broader assistant. That is not the same measurement as the 26 tools in the inspected MCP registry. Do not conflate these counts.

## LLM providers
The project has used a multi-provider fallback chain involving Gemini, OpenAI, Groq, and OpenRouter. Provider availability, order, configuration, and success rates must be verified against the current code and runtime before being represented as current production behavior.

## Project status and claims
This document records architecture and project context shared during development. It is not a substitute for inspecting the current source code. Distinguish implemented, tested, deployed, and planned features in all technical descriptions.
""",
    "doom_mcp_tools_and_security.md": r"""
# DOOM MCP Tools, Contracts, and Security

## MCP server
The MCP server adapter is implemented in `src/tools/mcp_server.py`. The last inspected configuration used Streamable HTTP at `/mcp`, protocol version `2025-03-26`, and owner-only authentication. The last registry inspection found 26 registered tools.

## Tool groups
- Search and time: `web_search`, `get_datetime`.
- Reminders and automation: `save_reminder`, `list_reminders`, `automate`.
- Document retrieval: `search_docs`, `ingest_docs`, `list_docs`.
- Contacts and messaging: `call_contact`, `whatsapp_contact`, `add_contact`, `list_contacts`, `whatsapp_resume`.
- Profile: `set_profile`, `get_profile`.
- Email: `read_emails`, `send_email`, `summarize_inbox`.
- Job workflow: `job_search`, `score_jd`, `cover_letter`, `track_application`, `list_applications`, `find_hr_email`.
- Reporting and leads: `daily_briefing`, `save_lead`.

## MCP adapter behavior
The adapter derives tool signatures from Pydantic argument schemas or run-method signatures. It validates argument fields and required parameters, invokes synchronous tool functions through `asyncio.to_thread`, serializes tool results, and converts execution errors into concise tool errors.

## Side-effect boundaries
Some tools can cause external or persistent side effects. Examples include sending email, WhatsApp messaging, calling contacts, saving reminders, running automation, adding contacts, changing profile data, ingesting documents, tracking applications, and saving leads.

Never use destructive or externally visible tools as casual health checks. Test side-effecting tools with mocks, isolated test data, or explicit human approval. Prefer read-only tools for safe smoke tests.

## Security tests previously present
The inspected test suite included checks for command authentication, upload authentication, path traversal, unsupported and oversized uploads, sensitive-route authentication, public health access, CORS behavior, trusted identity, visitor isolation, and WhatsApp payload validation.

## Security reporting
Report the number of checks actually executed, pass/fail counts, and findings by severity. A passing test suite does not prove the absence of vulnerabilities. Do not claim a security certification or complete security audit without evidence.
""",
    "doom_agent_workflow.md": r"""
# DOOM Agent and LangGraph Workflow

## Main components
- Agent core: `src/agent/core.py`.
- LangGraph workflow: `src/agent/graph.py`.
- Tool registry: `src/tools/registry.py`.
- MCP adapter: `src/tools/mcp_server.py`.

LangGraph is already integrated in the project. The workflow is intended to coordinate user requests, routing, tool selection, and execution.

## Engineering approach
A useful design separates model reasoning from privileged application actions:
1. Parse and validate the request.
2. Select an allowed action or tool.
3. Validate tool arguments against a schema.
4. Apply authorization and policy checks.
5. Execute the tool in the application layer.
6. Normalize the result and return it to the user.
7. Record traces and evaluation outcomes where configured.

Prefer deterministic or hybrid routing for high-impact actions. Do not allow an LLM's free-form output to bypass application-layer validation or authorization.

## Evaluation dimensions
- Intent/routing accuracy.
- Tool-selection accuracy.
- Tool-argument validity.
- Multi-step task completion rate.
- Correct handling of missing information.
- Safe refusal or confirmation for side-effecting actions.
- Provider fallback success rate.
- End-to-end latency and token usage.

Keep deterministic test results separate from LLM-as-judge scores. Record the test set, expected outcome, model/provider, and evaluation date.
""",
    "doom_database_memory_and_rag.md": r"""
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
""",
    "doom_job_search_and_application_workflow.md": r"""
# DOOM Job Search and Application Workflow

## Intended workflow
The job-search automation concept is human-reviewed:
1. Discover jobs.
2. Rank and score job descriptions against the user's target profile.
3. Present a shortlist for review.
4. Prepare a tailored CV and cover letter for an approved job.
5. Prepare an email where appropriate.
6. Let the user complete submission on LinkedIn, Wellfound, Indeed, or an employer portal.
7. Track the application status after the user confirms submission.
8. Keep generated application documents organized.

The system should not silently submit applications or send emails without explicit approval.

## Related tools
The inspected MCP registry includes `job_search`, `score_jd`, `cover_letter`, `track_application`, `list_applications`, and `find_hr_email`, along with email and lead tools.

## Job sources and OAuth
LinkedIn OAuth is not required for public job discovery. Public search sources may include job listings that identify LinkedIn as their source, without requiring LinkedIn account OAuth. Do not remove LinkedIn source metadata merely because LinkedIn OAuth was removed.

## Data and evaluation
Useful measures include:
- Relevant jobs among the top 5 or top 20.
- Job-description scoring agreement with a human-reviewed set.
- CV/cover-letter generation completeness.
- Application state consistency.
- Duplicate job detection.
- Human approval and submission confirmation rates.

Do not claim automated application submission unless that capability is implemented, tested, and intentionally enabled.
""",
    "fitness_ai_coach_project.md": r"""
# Local Fitness AI Coach — Separate Ongoing Project

## Project purpose
A separate AI fitness-coach application is being developed to generate adaptive training plans based on a user's profile, goals, available equipment, training experience, and relevant constraints.

This is a separate project from DOOM. It was not included in the user's current CV at the time this knowledge document was created. Do not describe it as a completed or CV-listed project unless the user updates that status.

## Known technical direction
- Python and FastAPI backend.
- MongoDB for user plans, workouts, and reminders.
- Neon PostgreSQL with pgvector for nutrition/training knowledge retrieval.
- LangGraph orchestration.
- MCP for tool interfaces.
- A possible A2A design for communication between specialist agents, including a nutrition agent.
- Hybrid retrieval combining semantic search and lexical/BM25 retrieval, with Reciprocal Rank Fusion and optional cross-encoder reranking.

## Product direction
The coach is intended to adapt to different training contexts, such as general fitness, athletes, bodybuilding, CrossFit, and users with special constraints. It should support different experience levels and multiple sessions where appropriate.

The system should validate plans and exercise selection rather than blindly accepting model-generated workouts. Avoid recommending movements that conflict with stated constraints.

## Development status
The project has an existing backend repository and test history. A prior test run reported 714 passing tests, but that is a historical result and must be re-run before being presented as the current test count.

Nutrition-agent integration and the final RAG architecture were still being developed. Clearly label planned functionality as planned.
""",
    "career_profile_and_cv_goals.md": r"""
# Career Profile and CV Goals

## Target roles
The user's current target roles are AI Automation Engineer and AI Agent Developer. Adjacent roles include AI Integration Engineer, LLM Application Engineer, and Python/FastAPI backend roles with AI integration.

The user is targeting early-career opportunities and is exploring international roles as well as opportunities in India.

## CV positioning
The current resume direction emphasizes AI and backend engineering, LLM systems, agentic workflows, and full-stack Python delivery.

The user's portfolio and GitHub are intended to support project-based evidence. Resume claims should remain truthful, concise, and defensible in technical interviews.

## Technical skills discussed
Python, FastAPI, asyncio, SQL, PostgreSQL, MongoDB, SQLite, ChromaDB (previous RAG implementation), pgvector (current migration), Sentence Transformers (previous implementation), LangGraph, MCP, REST APIs, OAuth integrations, and payment integrations.

The current pgvector migration uses FastEmbed as the proposed local embedding runtime. Do not list a technology as production experience solely because it is being evaluated or planned.

## Project and metric claims
Previously discussed resume claims include:
- 66% API latency reduction, from approximately 2700 ms to 920 ms.
- Processing or working with a dataset of more than one million records.
- A broader assistant tool count of 35.
- A multi-provider LLM fallback chain involving Gemini, OpenAI, Groq, and OpenRouter.

These are user-reported resume/project figures, not independently revalidated by this knowledge-base seed script. Reproduce them in a CV only if the user can explain the measurement method and provide supporting evidence.

The last inspected DOOM MCP registry contained 26 tools. This is a narrower count than the broader 35-tool claim.

## Interview preparation preferences
The user prefers simple, understandable English; concise explanations; practical examples; and interview-ready answers. For code defects, prioritize a direct fix with a brief explanation. Interview practice should focus on the core idea, why it matters, where it is used, and a practical example.
""",
    "doom_testing_and_evaluation.md": r"""
# DOOM Testing, Reliability, and Evaluation

## Historical baseline
A prior local test run reported 31 tests passing. A later coverage run also reported 31 passing tests and 41% overall statement coverage across 3,397 statements. These are historical snapshots, not guaranteed current results.

The coverage report showed stronger coverage in the MCP server adapter and schemas, with lower coverage in some API routes, RAG, job, email, and automation modules.

## Historical performance measurements
Earlier preliminary measurements included:
- Health endpoint, 5 virtual users for 60 seconds: 100% success, approximately 390.88 ms p95 in one run.
- MCP `get_profile`, 10 calls: approximately 489.97 ms average in one run.
- Mixed concurrency, 5 workers and 100 requests: 100/100 successful; approximately 1,136 ms p95 in one run.

These are preliminary historical measurements. They are not a comprehensive load test, and they must not be represented as current performance without repeating the test against a named target and recording the environment.

## Evaluation runner
An initial runner exists at `evaluation/run.ps1`. It runs compile checks, pytest, `git diff --check`, and checks the MCP registry count, then saves JSON, CSV, and Markdown reports.

The deployed target option was previously only a report label and did not actually call the deployed API. Do not use that option to claim deployed testing until the runner is corrected.

## Recommended evaluation categories
- Code health: compileall, pytest, coverage, dependency checks, diff checks.
- API reliability: endpoint status, validation errors, authentication, concurrency, timeouts.
- MCP reliability: registration, schema validation, safe read-only tool execution, authorization.
- Security: auth boundaries, malformed requests, upload validation, path traversal, secret leakage.
- Performance: throughput, p50/p90/p95/p99, error rate, and maximum stable load.
- Agent quality: routing, tool choice, argument validity, task completion, and safe handling of side effects.
- RAG quality: Recall@K, Precision@K, MRR, and retrieval latency.

Always report test scope, target, timestamp, environment, and limitations. Never turn a test count or coverage percentage into a blanket quality or security claim.
""",
}

def chunk_text(content: str, chunk_words: int = CHUNK_WORDS, overlap: int = CHUNK_OVERLAP) -> list[str]:
    words = re.findall(r"\S+", content)
    if not words:
        return []
    if chunk_words <= overlap:
        raise ValueError("chunk_words must be greater than overlap")
    step = chunk_words - overlap
    return [" ".join(words[i:i + chunk_words]) for i in range(0, len(words), step)]

def vector_literal(values: Iterable[float]) -> str:
    return "[" + ",".join(f"{float(v):.8f}" for v in values) + "]"

def main() -> int:
    load_dotenv(ROOT / ".env")
    if not os.getenv("DATABASE_URL"):
        print("ERROR: DATABASE_URL is not configured.", file=sys.stderr)
        return 2

    DOCS_DIR.mkdir(parents=True, exist_ok=True)
    print(f"Creating {len(DOCUMENTS)} curated knowledge documents...")
    for filename, content in DOCUMENTS.items():
        path = DOCS_DIR / filename
        path.write_text(content.strip() + "\n", encoding="utf-8")
        print(f"  created: {path.relative_to(ROOT)}")

    try:
        from src.memory.database import engine
    except Exception as exc:
        print(f"ERROR: Could not import the DOOM database engine: {exc}", file=sys.stderr)
        return 2

    print(f"\nLoading embedding model: {MODEL_NAME}")
    embedder = TextEmbedding(model_name=MODEL_NAME)

    all_chunks: list[tuple[str, int, str, str]] = []
    for filename, content in DOCUMENTS.items():
        for index, chunk in enumerate(chunk_text(content)):
            digest = hashlib.sha256(chunk.encode("utf-8")).hexdigest()
            all_chunks.append((filename, index, chunk, digest))

    print(f"Prepared {len(all_chunks)} chunks from {len(DOCUMENTS)} documents.")

    try:
        with engine.begin() as conn:
            extension_exists = conn.execute(
                text("SELECT EXISTS (SELECT 1 FROM pg_extension WHERE extname = 'vector')")
            ).scalar()
            if not extension_exists:
                raise RuntimeError("pgvector extension is not enabled in this database.")

            conn.execute(text(f"""
                CREATE TABLE IF NOT EXISTS {TABLE} (
                    id BIGSERIAL PRIMARY KEY,
                    source TEXT NOT NULL,
                    chunk_index INTEGER NOT NULL,
                    content TEXT NOT NULL,
                    content_hash CHAR(64) NOT NULL,
                    embedding VECTOR({EMBEDDING_DIM}) NOT NULL,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    UNIQUE (source, chunk_index)
                )
            """))

            # Rebuild only these curated seed sources. Other sources remain untouched.
            for filename in DOCUMENTS:
                conn.execute(
                    text(f"DELETE FROM {TABLE} WHERE source = :source"),
                    {"source": filename},
                )

            texts = [item[2] for item in all_chunks]
            vectors = list(embedder.embed(texts))
            if len(vectors) != len(all_chunks):
                raise RuntimeError("Embedding count does not match chunk count.")

            insert_sql = text(f"""
                INSERT INTO {TABLE}
                    (source, chunk_index, content, content_hash, embedding)
                VALUES
                    (:source, :chunk_index, :content, :content_hash, CAST(:embedding AS vector))
            """)

            for start in range(0, len(all_chunks), BATCH_SIZE):
                batch = all_chunks[start:start + BATCH_SIZE]
                params = []
                for offset, (source, chunk_index, content, digest) in enumerate(batch):
                    vector = vector_literal(vectors[start + offset])
                    if len(vectors[start + offset]) != EMBEDDING_DIM:
                        raise RuntimeError(
                            f"Expected {EMBEDDING_DIM} dimensions; got {len(vectors[start + offset])}."
                        )
                    params.append({
                        "source": source,
                        "chunk_index": chunk_index,
                        "content": content,
                        "content_hash": digest,
                        "embedding": vector,
                    })
                conn.execute(insert_sql, params)

            conn.execute(text(f"""
                CREATE INDEX IF NOT EXISTS ix_{TABLE}_embedding_hnsw
                ON {TABLE} USING hnsw (embedding vector_cosine_ops)
            """))

            total = conn.execute(text(f"SELECT COUNT(*) FROM {TABLE}")).scalar()
            seeded = conn.execute(
                text(f"SELECT COUNT(*) FROM {TABLE} WHERE source = ANY(:sources)"),
                {"sources": list(DOCUMENTS.keys())},
            ).scalar()
            print("\nNeon ingestion successful.")
            print(f"  Total rows in {TABLE}: {total}")
            print(f"  Rows from this seed run: {seeded}")
            print(f"  Sources seeded: {len(DOCUMENTS)}")
            print(f"  Embedding dimensions: {EMBEDDING_DIM}")
            print(f"  Embedding model: {MODEL_NAME}")
    except Exception as exc:
        print(f"\nERROR during database ingestion: {type(exc).__name__}: {exc}", file=sys.stderr)
        print("The database transaction was rolled back. Generated Markdown files remain available.", file=sys.stderr)
        return 1
    finally:
        engine.dispose()

    print(f"\nMarkdown documents: {DOCS_DIR}")
    print("Existing user-memory tables were not modified.")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
