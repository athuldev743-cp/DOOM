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
