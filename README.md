# DOOM — Personal AI Assistant

DOOM is a full-stack, tool-using AI agent that automates real personal and career workflows — job search, applications, email, WhatsApp, contacts, reminders, PC automation, and document retrieval — through a single natural-language interface, with voice input/output, reviewed job applications, and multi-provider LLM fallback.

**Live app:** https://doom-1a9d9743.fastapicloud.dev

---

## Why this exists

Most "AI assistant" demos wrap a single LLM call with a chat UI. DOOM is built around a different problem: reliably executing real actions — sending an actual WhatsApp message, actually applying to a job, actually reading your inbox — which means the hard part isn't the LLM call, it's the routing, validation, and failure handling around it. This project explores that end of agent design: strict tool-calling discipline, hallucination guardrails, and infrastructure-level reliability (LLM fallback, RAG grounding) rather than just prompt engineering.

---

## Architecture

```
┌──────────────┐     ┌─────────────────────┐     ┌──────────────────┐
│  CLI / Voice  │────►│  LangGraph Agent     │────►│  26-Tool Registry │
│  or Web API   │     │  src/agent/graph.py   │     │  src/tools/       │
└──────────────┘     └──────────┬────────────┘     └──────────────────┘
                                 │
                    ┌────────────┼────────────┐
                    ▼            ▼             ▼
             ┌───────────┐ ┌──────────────────┐ ┌──────────────┐
             │ Multi-LLM │ │ PostgreSQL RAG   │ │ PostgreSQL   │
             │ Fallback  │ │ pgvector + FTS   │ │ Memory /     │
             │ Chain     │ │ RRF fusion       │ │ Profile      │
             └───────────┘ └──────────────────┘ └──────────────┘
```

- **Agent core**: a LangGraph state machine — the LLM decides whether to answer or call a tool; tool arguments are parsed and validated before execution; malformed or invalid calls enter a bounded retry path; tool results are formatted into the final response
- **LLM layer**: cascading fallback across 4 providers, 14 total model attempts, so the assistant stays available even under rate limits or provider outages, with full call tracing via Langfuse (see below)
- **Tool registry**: 26 active tools across job search, email, WhatsApp, contacts, reminders, PC automation, document RAG, and daily briefings
- **Memory**: PostgreSQL (SQLAlchemy) for conversation history, user profile, and job data; injected into the system prompt on every turn
- **Voice I/O**: speech-to-text input and text-to-speech output with local audio caching

---

## MCP integration

DOOM now exposes its existing internal tool registry through one Model Context Protocol server using the official Python SDK and Streamable HTTP transport.

- **Endpoint:** `/mcp` on the FastAPI application.
- **Coverage:** all 26 tools are registered from `src/tools/registry.py`; the adapter does not duplicate tool business logic.
- **Validation:** Pydantic argument schemas are reused where available. Tools without a Pydantic schema use their Python `run()` signature for required/allowed argument validation.
- **Execution:** synchronous tools run in a worker thread so they do not block the ASGI event loop.
- **Transport:** stateless Streamable HTTP, suitable for hosted deployments that may run multiple workers.
- **Access control:** every MCP request requires the existing DOOM owner session, supplied as the `doom_session` cookie or a Bearer session token. Unauthenticated MCP requests are rejected.
- **Host configuration:** set `MCP_ALLOWED_HOSTS` and `MCP_ALLOWED_ORIGINS` when deploying behind a different hostname or custom domain.

The MCP layer is an adapter around the existing tools. The custom ReAct/LangGraph agent continues to work as before; MCP support does not replace the current chat execution path.

---

## Implementation metrics (configured)

| Area | Current implementation |
|---|---|
| Registered internal tools | 26 |
| MCP exposure | All 26 tools through one owner-authenticated Streamable HTTP server |
| LLM providers | 4: Groq, Gemini, OpenAI, OpenRouter |
| Configured model attempts | 18 across the four providers |
| LLM fallback budget | 45 seconds overall by default |
| Per-model timeout | 8 seconds by default |
| Job discovery markets | 6 markets in rotation; 5 scanned per day |
| Rolling job pool | Maximum 50 matches |
| Application preparation | Maximum 5 pending review documents |
| Generated CV retention | Completed application PDFs are cleared after 30 days |
| RAG chunking | 450 words per chunk with 60-word overlap; top 3 results by default |

These are implementation settings and capacity limits, not live performance measurements. Actual response latency must be measured from production traces after the FastAPI Cloud deployment is confirmed.

---

## LLM observability (Langfuse)

Every call through the fallback chain is traced — which provider/model actually served the response, per-attempt latency (including failed attempts before a successful fallback), and token usage/cost where the provider returns it. This turned "the fallback chain works" from a claim into something verifiable: a real rate-limit event was captured live during testing, showing Gemini failing with a 429, immediately falling through two more Gemini model variants, and eventually succeeding — with the full cascade timed and visible in the trace.

Self-hosted via Docker Compose for local development, with a Langfuse Cloud option for tracing the production deployment.

---

## Background job discovery pipeline

DOOM separates scheduled job discovery from chat delivery. The GitHub Actions scanner runs once daily and searches recent listings across Germany, the Netherlands, the United Kingdom, the UAE, Singapore, and India. Five markets are scanned per day in rotation to stay within the JSearch monthly API budget.

- Searches AI Automation Engineer, AI Agent Developer, AI Engineer, Python Backend Engineer, Backend Developer, and Full Stack Developer roles.
- Requests jobs posted within the last week and filters obvious senior titles and explicit requirements of two or more years of experience.
- Deduplicates URLs with SeenUrl, scores listings against the stored skill profile, and keeps a capped rolling pool in DailyJobMatch.
- The chat-facing job_search tool reads the highest-scoring 20 matches from PostgreSQL; it does not make live API calls.

Listings can still require local work authorization or relocation sponsorship. DOOM displays the original listing and location/remote metadata; the applicant must verify eligibility with the employer.

---

## Reviewed job application workflow

Every discovered job receives a persistent JobApplication record. The daily scanner pre-generates documents for up to five top-ranked recent jobs, while keeping no more than five applications pending review. The owner can download each PDF, edit the cover letter, and approve both documents before taking action.

- data/resumes/master_resume.json is the factual source for CV generation. The job description only changes the ordering and emphasis of existing skills, experience bullets, and projects; it does not create new qualifications or achievements.
- ReportLab generates an ATS-friendly PDF. The PDF bytes are stored on the matching application record in PostgreSQL, so they do not depend on ephemeral server storage.
- Email applications require a separate owner action after approval. The approved cover letter and that application's exact PDF are attached to the Gmail message.
- Platform applications open the original job URL. The owner completes the application on the employer's platform and explicitly confirms submission in DOOM.
- Automatic and bulk application tools are disabled. No application is submitted or emailed directly by the LLM.
- A daily cleanup removes completed application PDFs after 30 days while retaining application history. Active and pending applications are preserved.

## The multi-LLM fallback chain

DOOM tries providers in the order configured in `src/agent/llm.py`:

1. **Groq** — 6 configured model attempts
2. **Gemini** — 5 configured model attempts
3. **OpenAI** — 3 configured model attempts
4. **OpenRouter** — 4 configured model attempts

That is **18 configured model attempts across 4 providers**. These are fallback candidates, not a claim that every model is always available.

Latency is bounded by the fallback controller in `src/agent/llm_fallback.py`:
- **45-second overall budget** by default (`LLM_TOTAL_TIMEOUT_SECONDS`).
- **8-second per-model timeout** by default (`LLM_ATTEMPT_TIMEOUT_SECONDS`).
- Provider calls run in worker threads, so a synchronous SDK request does not block FastAPI's event loop.
- Langfuse records the serving provider/model, attempted-model count, elapsed time, and timeout-budget exhaustion.

The timeouts are configurable through environment variables. The actual latency depends on provider response times and how quickly a usable model is reached; the configured limits are not measured latency claims.

---

## RAG pipeline

DOOM grounds document answers with a PostgreSQL-backed hybrid retrieval pipeline:

- **Embedding model**: `BAAI/bge-small-en-v1.5` through FastEmbed, producing 384-dimensional vectors
- **Vector store**: PostgreSQL with the pgvector extension
- **Lexical retrieval**: PostgreSQL full-text search using `websearch_to_tsquery` and a generated search vector
- **Fusion**: Reciprocal Rank Fusion (RRF, currently `k = 60`) combines vector and lexical candidate rankings
- **Ingestion**: PDF extraction with PyMuPDF plus TXT/Markdown support; 450-word chunks with 60-word overlap
- **Storage**: source name, chunk index, content, content hash, and embedding are stored in the `doom_document_chunks` table
- **Query**: vector and lexical candidates are fused and the top results are returned with source and chunk attribution

The production retrieval implementation is in `src/memory/rag.py`. The active store is PostgreSQL/pgvector; ChromaDB is not part of the current DOOM RAG path.

---


## Engineering evaluation

The repository includes repeatable local evaluations for retrieval, agent decisions, API health and external MCP/RAG request flows.

### RAG retrieval benchmark

A 50-query curated benchmark compares vector-only, PostgreSQL lexical-only and hybrid retrieval. Queries cover direct questions, keyword-poor wording, multi-hop questions, paraphrases and technical identifiers.

| Metric | Vector-only | Lexical-only | Hybrid (RRF) |
|---|---:|---:|---:|
| Hit@5 | 96% | 20% | 96% |
| MRR@5 | 0.912 | 0.200 | 0.902 |
| Mean SQL execution | 576.5 ms | 293.2 ms | 291.7 ms |
| SQL p95 | 707.2 ms | 393.1 ms | 358.2 ms |

**Interpretation:** Hybrid retrieval matched vector-only Hit@5 on this dataset; vector-only had a slightly higher MRR. Lexical-only retrieval was substantially weaker. These results do not show that RRF improved ranking quality. The benchmark uses curated expected-source labels, not human-judged passage relevance. SQL timings are local sequential-run measurements, not production end-to-end latency.

### Agent decision evaluation

A 20-task real-LLM evaluation exercised tool selection, argument parsing/validation and LangGraph retry routing. It recorded 95% task completion, 90% first-attempt accuracy and 95% final tool-selection accuracy. Mean decision latency was approximately 896 ms, with a 1.49 s p95.

This is a small evaluation sample. Tool execution was safely mocked, so these figures measure decision/orchestration behavior and must not be represented as end-to-end success rates for real external actions.

### API and regression checks

- Local test suite: **50 tests passed** at the time of this evaluation update.
- k6 health-endpoint run: 5 virtual users for 1 minute; 0% failed checks and 391 ms p95. This measures the health endpoint only, not RAG or agent response latency.
- The repository includes separate k6 workloads for MCP initialization and RAG execution. Their scripts are test assets; results must be reported only after the workload is actually run against the target deployment.

Run the local checks with:

```powershell
python -m pytest -q
python -m py_compile evaluation/run_all.py evaluation/run_agent_quality_20.py evaluation/run_agent_quality_v2.py evaluation/run_rag_50_benchmark.py
```


## Tool-calling discipline

The LangGraph agent uses a strict `TOOL:` / `ARGS:` output protocol rather than relying only on native model function-calling. Tool arguments pass through parsing and Pydantic validation before the application executes a tool. Unknown tools, malformed calls, and invalid arguments are routed through a bounded retry path (maximum two retries). Ordinary responses bypass tool execution.

After a tool runs, its raw result is fed back to the LLM with explicit formatting instructions — present only what the tool returned, never invent additional results — rather than letting the model freely narrate. Application preparation, document approval, email sending, and platform submission are owner-authenticated API actions outside the LLM tool loop.

---

## Tool categories

| Category | Registered tools |
|---|---|
| Job search & applications | job_search, find_hr_email, cover_letter, score_jd, track_application, list_applications |
| Email | read_emails, send_email, summarize_inbox |
| WhatsApp | whatsapp_contact, whatsapp_resume |
| Contacts & profile | call_contact, add_contact, list_contacts, set_profile, get_profile |
| Documents / RAG | search_docs, ingest_docs, list_docs |
| Productivity | save_reminder, list_reminders, daily_briefing, get_datetime |
| System & web | automate, web_search |
| Visitor leads | save_lead |


---

## Tech Stack

| Layer | Technology |
|---|---|
| Agent framework | LangGraph state graph with validation, bounded retries, tool execution and response nodes |
| LLM providers | Gemini, OpenAI, Groq, OpenRouter (cascading fallback) |
| RAG | PostgreSQL, pgvector, PostgreSQL full-text search, RRF, FastEmbed, PyMuPDF |
| Memory | PostgreSQL (SQLAlchemy) |
| API / MCP transport | FastAPI, official MCP Python SDK v2, Streamable HTTP |
| Observability | Langfuse (self-hosted via Docker + cloud) |
| Voice | Speech-to-text + text-to-speech with local mp3 caching |
| CLI | Rich (styled terminal interface) |
| Automation | GitHub Actions (daily international job scanning, morning digest) |
| CV generation | ReportLab, PostgreSQL application records |
| Deployment | FastAPI Cloud |

---

## Getting Started

### Prerequisites
- Python 3.11+
- API keys: Groq, Gemini, OpenAI, OpenRouter (at least one required; more = better fallback coverage)
- Google OAuth credentials for Gmail API (if using email tools)

### Setup

```bash
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env  # fill in your API keys — see Configuration below
python main.py
```

### Configuration

Create `.env` with:

```
GEMINI_API_KEY=your_gemini_key
OPENAI_API_KEY=your_openai_key
GROQ_API_KEY=your_groq_key
OPENROUTER_API_KEY=your_openrouter_key
LLM_TOTAL_TIMEOUT_SECONDS=45
LLM_ATTEMPT_TIMEOUT_SECONDS=8
MCP_ALLOWED_HOSTS=doom-1a9d9743.fastapicloud.dev,doom-1a9d9743.fastapicloud.dev:*
MCP_ALLOWED_ORIGINS=https://doom-1a9d9743.fastapicloud.dev
CORS_ALLOWED_ORIGINS=https://doom-1a9d9743.fastapicloud.dev
DOCS_UPLOAD_MAX_BYTES=10485760
DOCS_PATH=./data/documents
```

Gmail API access requires a separate `credentials.json` (OAuth client) obtained from Google Cloud Console — **never commit this file or the resulting `token.json`.**

---

## Project Structure

```
src/
├── agent/
│   ├── graph.py           # LangGraph decision, validation, retry and execution flow
│   ├── llm.py             # Multi-provider LLM selection
│   └── llm_fallback.py    # Provider fallback and timeout controller
├── api/                   # FastAPI app and routes
├── memory/
│   ├── database.py        # PostgreSQL / SQLAlchemy engine
│   ├── manager.py         # Conversation memory orchestration
│   ├── profile.py         # Persistent user profile
│   └── rag.py             # FastEmbed + pgvector + PostgreSQL FTS + RRF
├── tools/                 # Tool registry, schemas and MCP adapter
├── voice/                 # Speech input/output
└── scripts/               # Scheduled jobs and background workflows

evaluation/
├── k6/                    # External MCP and RAG load-test workloads
├── run_agent_quality_v2.py
├── run_rag_50_benchmark.py
└── run_all.py             # Unified evaluation runner
```

---

## Roadmap

- [ ] Circuit breaker / shorter timeout budget on the LLM fallback chain to bound worst-case latency
- [ ] Structured eval suite for tool-selection accuracy (does the agent pick the right tool for ambiguous phrasing?)
- [x] Observability (Langfuse) for LLM call tracing across the fallback chain — which provider actually served each response, latency per tier
- [x] Fixed job-search performance and correctness (dead code, broken conditional, missing persistence — see Background job discovery pipeline)
- [ ] WhatsApp-based application delivery (send resume + cover message directly to HR contacts)
- [ ] Concurrent fetching for the background scanner itself (currently sequential per query, same pattern already fixed once in the delivery path)

---

## License

Personal project — not currently licensed for reuse.
