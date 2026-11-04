# DOOM — Personal AI Assistant

DOOM is a full-stack, tool-using AI agent that automates real personal and career workflows — job search, applications, email, WhatsApp, contacts, reminders, PC automation, and document retrieval — through a single natural-language interface, with voice input/output and zero-downtime LLM availability via a four-provider fallback chain.

**Live app:** https://doom-1a9d9743.fastapicloud.dev

---

## Why this exists

Most "AI assistant" demos wrap a single LLM call with a chat UI. DOOM is built around a different problem: reliably executing real actions — sending an actual WhatsApp message, actually applying to a job, actually reading your inbox — which means the hard part isn't the LLM call, it's the routing, validation, and failure handling around it. This project explores that end of agent design: strict tool-calling discipline, hallucination guardrails, and infrastructure-level reliability (LLM fallback, RAG grounding) rather than just prompt engineering.

---

## Architecture

```
┌──────────────┐     ┌─────────────────────┐     ┌──────────────────┐
│  CLI / Voice  │────►│   Agent Core (ReAct)  │────►│  35-Tool Registry │
│  or Web API   │     │  src/agent/core.py    │     │  src/tools/       │
└──────────────┘     └──────────┬────────────┘     └──────────────────┘
                                 │
                    ┌────────────┼────────────┐
                    ▼            ▼             ▼
             ┌───────────┐ ┌──────────┐ ┌──────────────┐
             │ Multi-LLM │ │ RAG /    │ │ SQLite Memory │
             │ Fallback  │ │ ChromaDB │ │ + Profile     │
             │ Chain     │ │          │ │ Store         │
             └───────────┘ └──────────┘ └──────────────┘
```

- **Agent core**: a ReAct-style loop — the LLM decides whether to call a tool (`TOOL: name` / `ARGS: ...`) or answer directly, tool results get fed back for a final grounded response
- **LLM layer**: cascading fallback across 4 providers, 14 total model attempts, so the assistant stays available even under rate limits or provider outages, with full call tracing via Langfuse (see below)
- **Tool registry**: 35 tools across job search/applications, email, WhatsApp, contacts, reminders, PC automation, document RAG, and daily briefings
- **Memory**: PostgreSQL (SQLAlchemy) for conversation history, user profile, and job data; injected into the system prompt on every turn
- **Voice I/O**: speech-to-text input and text-to-speech output with local audio caching

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

Every discovered job receives a persistent JobApplication record. The owner can prepare a tailored CV and cover letter for an individual listing, download the PDF, edit the cover letter, and approve both documents before taking action.

- data/resumes/master_resume.json is the factual source for CV generation. The job description only changes the ordering and emphasis of existing skills, experience bullets, and projects; it does not create new qualifications or achievements.
- ReportLab generates an ATS-friendly PDF. The PDF bytes are stored on the matching application record in PostgreSQL, so they do not depend on ephemeral server storage.
- Email applications require a separate owner action after approval. The approved cover letter and that application's exact PDF are attached to the Gmail message.
- Platform applications open the original job URL. The owner completes the application on the employer's platform and explicitly confirms submission in DOOM.
- Automatic and bulk application tools are disabled. No application is submitted or emailed directly by the LLM.
- A daily cleanup removes completed application PDFs after 30 days while retaining application history. Active and pending applications are preserved.

## The multi-LLM fallback chain

This is the core reliability mechanism, and it's more aggressive than a simple two-way failover. On every chat call, DOOM attempts, in order:

1. **Gemini** — 5 models tried in sequence (`gemini-2.5-flash` down through `gemini-1.5-flash`)
2. **OpenAI GPT-5 Nano** — single fallback attempt if all Gemini models fail
3. **Groq** — 4 models tried in sequence (`llama-3.3-70b-versatile` down to `gemma2-9b-it`)
4. **OpenRouter** — 4 free-tier models as the final safety net (`nemotron-nano-9b`, `llama-3.3-70b-instruct`, `qwen3-4b`, `lfm-2.5-1.2b`)

Each attempt is wrapped in its own try/except with a short timeout (15–30s), so a single hung request can't stall the whole chain. In the worst case, the system tries up to 14 different model endpoints before returning a graceful failure message — in practice this means the assistant has stayed responsive through real provider rate-limit and outage events during development.

**Design tradeoff worth noting**: this maximizes uptime but means response latency is unbounded in the worst case (a full walk through 14 failing endpoints). A production version of this would benefit from a circuit breaker or shorter per-tier timeout budget — noted in the roadmap.

---

## RAG pipeline

Document retrieval for grounding responses in Athul's real documents (resume, personal docs):

- **Embedding model**: `all-MiniLM-L6-v2` via SentenceTransformers
- **Vector store**: ChromaDB, persisted locally
- **Ingestion**: PDF text extraction via PyMuPDF (`fitz`), plain text/markdown support, chunked at 500 words with 50-word overlap to preserve context across chunk boundaries
- **Re-ingestion safety**: ingesting a file that's already indexed deletes its old chunks first (matched by source filename) before re-adding, preventing duplicate/stale chunks from accumulating
- **Query**: top-k semantic search (default 3 results) returned with source attribution

---

## Tool-calling discipline

The system prompt encodes a strict protocol rather than relying on the model's native function-calling: exact TOOL: name / ARGS: value output format, explicit rules against hallucinating job listings, and a separation between job discovery and application actions.

After a tool runs, its raw result is fed back to the LLM with explicit formatting instructions — present only what the tool returned, never invent additional results — rather than letting the model freely narrate. Application preparation, document approval, email sending, and platform submission are owner-authenticated API actions outside the LLM tool loop.

---

## Tool categories

| Category | Tools |
|---|---|
| Job search & applications | job_search, find_hr_email, cover_letter, score_jd, track_application, list_applications |
| Email | read_emails, send_email, summarize_inbox |
| WhatsApp | whatsapp_api_send, whatsapp_api_resume, whatsapp_broadcast, whatsapp_contact, whatsapp_resume |
| Contacts & profile | call_contact, add_contact, list_contacts, set_profile, get_profile |
| Documents / RAG | search_docs, ingest_docs, list_docs |
| Productivity | save_reminder, list_reminders, daily_briefing, get_datetime |
| System | automate (PC control), web_search, linkedin_profile |

---

## Tech Stack

| Layer | Technology |
|---|---|
| Agent framework | Custom ReAct-style loop (no LangChain) |
| LLM providers | Gemini, OpenAI, Groq, OpenRouter (cascading fallback) |
| RAG | ChromaDB, SentenceTransformers, PyMuPDF |
| Memory | PostgreSQL (SQLAlchemy) |
| API | FastAPI |
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
- API keys: Gemini, OpenAI, Groq, OpenRouter (at least one required; more = better fallback coverage)
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
CHROMA_PATH=./data/chroma
DOCS_PATH=./data/documents
```

Gmail API access requires a separate `credentials.json` (OAuth client) obtained from Google Cloud Console — **never commit this file or the resulting `token.json`.**

---

## Project Structure

```
src/
├── agent/
│   ├── core.py          # ReAct loop, tool dispatch, response formatting
│   └── llm.py            # Multi-provider fallback chain
├── api/                  # FastAPI app + routes (chat, upload, transcribe, LinkedIn)
├── memory/
│   ├── database.py       # SQLite conversation history
│   ├── manager.py        # Memory read/write orchestration
│   ├── profile.py        # Persistent user profile store
│   ├── extractor.py       # Background fact extraction from conversations
│   └── rag.py              # ChromaDB ingestion + semantic search
├── tools/                 # 35 tool implementations + registry
├── voice/                  # STT/TTS
└── scripts/                 # Scheduled jobs (morning digest, job scanning)
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