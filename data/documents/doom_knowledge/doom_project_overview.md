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
