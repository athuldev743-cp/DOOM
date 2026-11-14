# DOOM — Personal AI Assistant

DOOM is a full-stack personal AI assistant built around a tool-using agent. It combines a LangGraph-controlled decision workflow, validated application tools, a multi-provider LLM fallback chain, PostgreSQL-backed memory and document retrieval, and a FastAPI web application.

**Live application:** https://doom-1a9d9743.fastapicloud.dev  
**Repository:** https://github.com/athuldev743-cp/DOOM

---

## What DOOM does

DOOM provides one natural-language interface for personal productivity and career workflows:

- **Job discovery:** reads a persisted pool of ranked job matches produced by the scheduled scanner.
- **Application preparation:** prepares job-specific CV PDFs and cover letters for owner review.
- **Email:** reads, summarizes, and sends email through the Gmail API.
- **WhatsApp and contacts:** prepares contact-based WhatsApp actions and resume/portfolio sharing; contact lookup and phone-call actions are exposed to the client.
- **Personal memory:** stores conversation history, profile information, contacts, reminders, and job/application records in PostgreSQL.
- **Document Q&A:** ingests PDF, TXT, and Markdown documents and retrieves relevant passages using hybrid search.
- **PC and web actions:** opens supported applications and websites, performs supported search/YouTube actions, and exposes desktop automation commands.
- **Voice:** accepts audio transcription requests through Groq Whisper and generates speech with Edge TTS.
- **Daily briefing:** generates a scheduled daily briefing.

The actual actions available depend on the configured credentials, client capabilities, and deployment environment.

## Architecture

The diagram below describes the implemented request and tool-execution path. MCP is a separate adapter over the same internal tool registry; it does not replace the LangGraph chat workflow.

```mermaid
flowchart TD
    U[Web UI / API Client] --> API[FastAPI Application]
    API --> AUTH[Session and Owner Checks]
    AUTH --> CORE[Agent Core]
    CORE --> MEM[Conversation Memory and User Profile]
    CORE --> GRAPH[LangGraph StateGraph]

    GRAPH --> DECIDE[LLM Decision Node]
    DECIDE -->|Normal response| RESP[Response Formatting]
    DECIDE -->|TOOL and ARGS| VALIDATE[Parse and Validate Arguments]
    VALIDATE -->|Invalid| RETRY[Bounded Retry]
    RETRY --> DECIDE
    VALIDATE -->|Valid| EXEC[Application Tool Execution]
    EXEC --> REG[26-Tool Registry]
    REG --> RESULT[Tool Result]
    RESULT --> RESP
    RESP --> API

    DECIDE --> LLM[LLM Fallback Controller]
    LLM --> GROQ[Groq]
    LLM --> GEMINI[Gemini]
    LLM --> OPENAI[OpenAI]
    LLM --> ROUTER[OpenRouter]
    LLM --> TRACE[Langfuse Tracing]

    REG --> RAG[Document Retrieval Tool]
    RAG --> EMBED[FastEmbed]
    EMBED --> PG[(PostgreSQL + pgvector)]
    RAG --> FTS[PostgreSQL Full-Text Search]
    FTS --> PG

    REG --> INTEGRATIONS[Gmail / WhatsApp Client Actions / Web Search / PC Actions]
    API --> MCP[MCP Streamable HTTP Adapter]
    MCP --> REG
    API --> DB[(PostgreSQL)]
    API --> VOICE[Groq Whisper / Edge TTS]
```

### Agent execution flow

The agent is implemented in `src/agent/graph.py` with LangGraph's `StateGraph`.

1. The decision node sends the relevant conversation context to the LLM.
2. The LLM either returns a normal answer or emits the application's `TOOL:` / `ARGS:` protocol.
3. Tool arguments are parsed and validated before execution. Pydantic schemas are used where defined.
4. Invalid or malformed tool calls enter a bounded retry path (maximum two retries).
5. Only a validated, registered tool is executed by the application.
6. The tool result is passed back through the response-formatting flow.

This separation keeps tool execution in the application layer. The LLM selects and supplies arguments; it does not directly execute Python functions or bypass validation.

### MCP integration

DOOM also exposes its existing tool registry through the official Python MCP SDK.

- **Endpoint:** `/mcp`
- **Transport:** Streamable HTTP, stateless HTTP configuration
- **Coverage:** the same 26 tools registered in `src/tools/registry.py`
- **Validation:** reuses Pydantic schemas where available; otherwise validates arguments against the tool's Python `run()` signature
- **Execution:** synchronous tool functions run in a worker thread
- **Access control:** owner session required, supplied through the `doom_session` cookie or a Bearer session token
- **Transport security:** allowed hosts and origins are configurable through environment variables

The MCP adapter reuses the existing tool implementations; it does not maintain a second copy of tool business logic.

## Implemented capabilities

### Tool registry

The application currently registers **26 tools**.

| Area | Tools |
|---|---|
| Job search and tracking | `job_search`, `find_hr_email`, `score_jd`, `cover_letter`, `track_application`, `list_applications` |
| Email | `read_emails`, `send_email`, `summarize_inbox` |
| WhatsApp and contacts | `whatsapp_contact`, `whatsapp_resume`, `call_contact`, `add_contact`, `list_contacts` |
| User profile | `set_profile`, `get_profile` |
| Documents and RAG | `search_docs`, `ingest_docs`, `list_docs` |
| Productivity | `save_reminder`, `list_reminders`, `daily_briefing`, `get_datetime` |
| System and web | `automate`, `web_search` |
| Visitor leads | `save_lead` |

### Job discovery and reviewed applications

The job discovery pipeline is separated from the interactive chat request:

- A scheduled GitHub Actions workflow scans job listings across Germany, the Netherlands, the United Kingdom, the UAE, Singapore, and India in rotation.
- The scanner stores and deduplicates listings in PostgreSQL, scores them against the stored profile, and maintains a capped rolling pool.
- The chat-facing `job_search` tool reads stored matches; it does not make a new live job-search API request for every chat message.
- Job-specific application records track preparation, approval, email, and submission states.
- CV content is generated from `data/resumes/master_resume.json`. The job description changes ordering and emphasis of existing information; it must not create new qualifications or achievements.
- ReportLab generates the CV PDF. The PDF content is stored with its application record in PostgreSQL.
- The owner reviews and approves application documents. Email sending and platform submission are separate owner actions.
- Platform applications open the original listing so the owner can complete the application and confirm its status.
- Completed application PDFs are subject to the configured retention cleanup; application history is retained.

Automatic bulk application is not the intended chat workflow. Do not interpret a prepared document or opened job listing as a submitted application.

### Memory and database

PostgreSQL is used for persistent application data, including:

- Conversation history and user profile information
- Contacts and reminders
- Seen job URLs and daily job matches
- Job application state and stored CV PDF content
- Visitor lead records
- Document chunks and their vector embeddings

SQLAlchemy provides the database engine, models, sessions, and connection pooling. The RAG implementation uses the PostgreSQL `doom_document_chunks` table.

### RAG pipeline

The current DOOM document retrieval implementation uses **PostgreSQL + pgvector**, not ChromaDB.

| Component | Implementation |
|---|---|
| Embedding model | `BAAI/bge-small-en-v1.5` |
| Embedding runtime | FastEmbed |
| Vector dimensions | 384 |
| Vector storage | PostgreSQL with pgvector |
| Lexical retrieval | PostgreSQL full-text search |
| Ranking fusion | Reciprocal Rank Fusion (RRF), `k = 60` |
| Document formats | PDF, TXT, Markdown |
| PDF extraction | PyMuPDF |
| Chunking | 450 words with 60-word overlap |
| Default retrieval | Top 3 fused results |

The retrieval query combines vector candidates with lexical candidates, fuses their ranks using RRF, and returns source-attributed chunks. The implementation is in `src/memory/rag.py`.

### LLM providers and fallback

The configured provider order in `src/agent/llm.py` is:

1. **Groq** — 3 configured model candidates
2. **Gemini** — 5 configured model candidates
3. **OpenAI** — 3 configured model candidates
4. **OpenRouter** — 4 configured model candidates

That is **15 configured model candidates across four providers** in the current source. These are fallback candidates, not a guarantee that every model is available at all times.

The fallback controller in `src/agent/llm_fallback.py`:

- Uses a configurable overall timeout (45 seconds by default).
- Uses a configurable per-model timeout (8 seconds by default).
- Runs synchronous provider SDK calls in worker threads.
- Records successful provider/model selection, attempted model count, elapsed time, and timeout-budget status through Langfuse.

### Observability and evaluation

Langfuse is integrated into the LLM fallback path to trace provider/model attempts and generation results.

The repository's evaluation assets include retrieval benchmarking, agent decision evaluation, API checks, and k6 workloads. Previously recorded benchmark figures should be treated as test-run results for their stated datasets and environments—not as guaranteed production performance.

Useful local commands:

```bash
python -m pytest -q
python -m py_compile evaluation/run_all.py evaluation/run_agent_quality_20.py evaluation/run_agent_quality_v2.py evaluation/run_rag_50_benchmark.py
```

Run the relevant evaluation or k6 workload before publishing a new performance number. Health-endpoint load results do not represent end-to-end agent or RAG latency.

## API surface

The FastAPI application is created in `src/api/app.py` and started through the root `main.py`.

| Method | Endpoint | Purpose |
|---|---|---|
| GET / HEAD | `/health` | Backend and MCP health information |
| POST | `/chat` | Chat request |
| POST | `/chat-stream` | Server-sent event chat response |
| POST | `/tts` | Generate speech from text |
| POST | `/transcribe` | Transcribe audio using Groq Whisper |
| GET | `/briefing` | Owner-authenticated daily briefing |
| POST | `/mcp` and MCP transport paths | MCP Streamable HTTP endpoint |

The web application and static assets are served by the FastAPI application.

## Technology stack

Only technologies present in the current project dependencies or implementation are listed here.

| Layer | Technologies |
|---|---|
| Language | Python |
| API server | FastAPI, Uvicorn |
| Agent orchestration | LangGraph |
| Validation and schemas | Pydantic |
| Model providers | Groq, Google Gemini, OpenAI, OpenRouter |
| Provider SDKs | Groq SDK, OpenAI Python SDK |
| MCP | Official Python MCP SDK, Streamable HTTP |
| Observability | Langfuse |
| Database | PostgreSQL |
| ORM and database access | SQLAlchemy, psycopg / psycopg2 |
| Vector retrieval | pgvector, FastEmbed |
| Lexical retrieval | PostgreSQL Full-Text Search |
| Document processing | PyMuPDF |
| PDF generation | ReportLab |
| Email integration | Gmail API, Google Auth |
| Voice input | Groq Whisper transcription endpoint |
| Voice output | Edge TTS |
| Scheduling | Project's background scheduler and GitHub Actions workflow |
| Desktop automation | Python subprocess, webbrowser, PyAutoGUI dependency |
| Web search | DuckDuckGo search packages and Requests / HTTPX |
| Frontend | HTML, CSS, JavaScript served by FastAPI |
| Testing and load testing | pytest, k6 |
| Deployment | FastAPI Cloud |

## Project layout

Key implementation files and directories:

```text
DOOM/
├── main.py
├── requirements.txt
├── README.md
├── src/
│   ├── agent/
│   │   ├── core.py
│   │   ├── graph.py
│   │   ├── llm.py
│   │   ├── llm_fallback.py
│   │   └── llm_providers/
│   ├── api/
│   │   ├── app.py
│   │   ├── index.html
│   │   ├── routes/
│   │   └── static/
│   ├── memory/
│   │   ├── database.py
│   │   ├── manager.py
│   │   ├── profile.py
│   │   └── rag.py
│   ├── tools/
│   │   ├── registry.py
│   │   ├── mcp_server.py
│   │   ├── schemas.py
│   │   ├── jobs_tool.py
│   │   ├── email_tool.py
│   │   ├── contacts_tool.py
│   │   ├── rag_tool.py
│   │   ├── automation.py
│   │   └── resume_builder.py
│   └── voice/
├── data/
│   └── resumes/
│       └── master_resume.json
└── evaluation/
    └── k6/
```

This is a map of the main application modules, not an exhaustive listing of runtime data, static assets, or every evaluation file.

## Getting started

### Requirements

- Python 3.11 or newer
- PostgreSQL database
- At least one configured LLM provider API key
- Google OAuth credentials/token if Gmail tools are required
- Optional integration credentials for the features you enable

### Install

```bash
git clone https://github.com/athuldev743-cp/DOOM.git
cd DOOM

python -m venv .venv

# Windows PowerShell
.venv\Scripts\Activate.ps1

# macOS / Linux
# source .venv/bin/activate

python -m pip install --upgrade pip
pip install -r requirements.txt
```

Create a local `.env` file and configure the environment variables needed by your deployment. Do not commit API keys, OAuth tokens, database credentials, or private user data.

### Environment configuration

The exact variables depend on which integrations are enabled. Common configuration includes:

```dotenv
DATABASE_URL=postgresql://USER:PASSWORD@HOST:5432/DATABASE

GROQ_API_KEY=
GEMINI_API_KEY=
OPENAI_API_KEY=
OPENROUTER_API_KEY=

LLM_TOTAL_TIMEOUT_SECONDS=45
LLM_ATTEMPT_TIMEOUT_SECONDS=8

LANGFUSE_PUBLIC_KEY=
LANGFUSE_SECRET_KEY=
LANGFUSE_HOST=http://localhost:3000

MCP_ALLOWED_HOSTS=localhost,127.0.0.1
MCP_ALLOWED_ORIGINS=http://localhost,http://127.0.0.1
CORS_ALLOWED_ORIGINS=http://localhost,http://localhost:8000

DOCS_PATH=./data/documents
DOCS_UPLOAD_MAX_BYTES=10485760
```

For hosted deployment, set the MCP host/origin and CORS values to the actual deployment hostname and trusted origins. The example values above are for local development; they are not production security settings.

Gmail access uses Google OAuth credentials or a configured token. Keep credential files and token JSON out of source control.

### Run locally

```bash
python main.py
```

The application entry point imports the FastAPI instance from `src.api.app`. Configure your local server command and port according to your environment.

## Security notes

- Keep provider API keys, database URLs, OAuth credentials, and session secrets in environment variables or the deployment's secret manager.
- Do not expose the MCP endpoint publicly without its owner-session authentication and correct host/origin restrictions.
- Treat tool arguments and external service responses as untrusted input; validation must remain enabled.
- Review CVs, cover letters, emails, and platform submissions before taking external actions.
- Never commit personal documents, generated application PDFs, tokens, or private database exports.

## Current implementation notes

- The chat agent uses a custom `TOOL:` / `ARGS:` protocol managed by LangGraph; it is not simply a direct LangChain wrapper.
- Tool execution is performed by the application after registry lookup and argument validation.
- MCP and chat share the same tool registry.
- PostgreSQL/pgvector is the active RAG store. ChromaDB is not used by the current DOOM RAG implementation.
- Configured model counts and timeout values describe source configuration, not provider uptime or measured response latency.

## License

Personal project. No open-source license is currently specified.
