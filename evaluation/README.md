# DOOM Engineering Evaluation

Automated evaluation framework for the DOOM AI backend.

## Evaluation modules

1. Security: authentication, authorization, input validation and upload security.
2. Reliability: API and MCP tool execution, failure handling and concurrency.
3. Performance: throughput, latency percentiles, load and stress testing using k6.
4. Agent evaluation: routing accuracy, tool selection, task completion and RAG quality.
5. Reporting: consolidated JSON, CSV and Markdown evaluation reports.

## Results

- results/local: measurements from the local backend.
- results/deployed: measurements from the deployed backend.

## Methodology

Keep local and deployed measurements separate. Record test configuration, date,
request count, success rate, errors, average latency, p50, p90, p95 and p99.
Never report unmeasured or mocked results as real-world benchmark results.

## Status

Scaffold created. Evaluation scripts will be implemented and validated individually.
