# DOOM Engineering Evaluation

Owner-only evaluation console available at /evaluation after deployment.

## Dashboard modules

1. RAG retrieval — hybrid vector + PostgreSQL full-text retrieval, curated source-level hit rate, precision, MRR, corpus and index checks, plus retrieval latency percentiles.
2. MCP tools — registered tool consistency and actual in-process MCP adapter calls for list_docs and search_docs.
3. LangGraph — compiled graph availability and end-to-end graph invocation through the configured LLM provider.
4. API latency — repeated in-process ASGI /health requests with average, p50, p95, p99 and maximum latency.
5. API & database — database connectivity, pgvector, corpus, embedding dimensions, FTS column and indexes.
6. Security — invalid session rejection and unauthenticated access denial for protected evaluation APIs.

## Running

- Sign in as the owner and open /evaluation.
- Run one card or select Run all tests.\n- The live terminal prints module start/completion, each check, report paths and a final summary.\n- Run all uses three workers in parallel to balance speed with production database/provider load.
- Set the count on each card before running.
- Reports are written under evaluation/results/deployed/ when the server filesystem is writable.

## Limits and interpretation

- RAG relevance is a curated expected-source smoke benchmark, not human-judged relevance.
- MCP checks call the registered in-process adapters. They do not measure a remote MCP client handshake or transport latency.
- LangGraph execution calls the configured LLM and consumes provider tokens. The dashboard caps graph runs at three per request.
- Latency results use in-process ASGI requests and exclude internet, DNS, TLS, reverse proxy and external client latency.
- Counts are bounded per module to protect the deployed service.
- External throughput, concurrent virtual users and public-network p95/p99 must be measured separately with k6 from an external load generator.
- The dashboard never reports local historical measurements as deployed results.

## Local checks

Run python -m pytest -q evaluation/test_dashboard.py and the existing test suite before deployment.

## External k6 load test

The dashboard latency card intentionally measures the in-process ASGI stack. For public-network latency, concurrency and throughput, run the separate k6 script from a machine outside the server:

```powershell
k6 run -e BASE_URL=https://doom-1a9d9743.fastapicloud.dev -e VUS=5 -e ITERATIONS=100 evaluation/k6/dashboard-health-load.js
```

k6 reports request duration percentiles, request rate, failed-request rate and iteration throughput. The default thresholds are p95 below 1500 ms, p99 below 3000 ms and failures below 1%; tune them to the service's agreed SLOs before treating them as release gates.


## Real MCP transport test

The dashboard's MCP module measures in-process adapters. To verify the deployed Streamable HTTP protocol itself, run this k6 script from an external machine. It performs initialize, initialized notification and tools/list using an owner session token:

```powershell
k6 run -e BASE_URL=https://doom-1a9d9743.fastapicloud.dev -e DOOM_SESSION="$env:DOOM_SESSION" -e VUS=1 -e ITERATIONS=3 evaluation/k6/mcp-streamable-http.js
```

Set `DOOM_SESSION` in your local PowerShell session first. Never paste the token into source code or commit it. This test checks the real remote MCP transport and owner authentication; it is separate from the in-process dashboard module.
