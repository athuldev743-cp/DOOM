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
