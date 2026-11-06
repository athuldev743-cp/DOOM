from __future__ import annotations

import json
import statistics
import time
import sys
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import text
from src.memory import rag
from src.memory.database import engine

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "evaluation" / "results" / "local"
OUT.mkdir(parents=True, exist_ok=True)
TABLE = "doom_document_chunks"

CASES = [
    ("What is DOOM and what backend framework does it use?", "doom_project_overview.md"),
    ("Which MCP tools are registered and how are side effects protected?", "doom_mcp_tools_and_security.md"),
    ("How does the LangGraph agent route requests and execute tools safely?", "doom_agent_workflow.md"),
    ("How does DOOM use PostgreSQL, pgvector, embeddings and semantic retrieval?", "doom_database_memory_and_rag.md"),
    ("How does DOOM discover jobs, score job descriptions and track applications?", "doom_job_search_and_application_workflow.md"),
    ("What is the separate fitness AI coach project and its planned architecture?", "fitness_ai_coach_project.md"),
    ("What AI engineering roles and CV project metrics is the user targeting?", "career_profile_and_cv_goals.md"),
    ("What are DOOM's historical pytest coverage and performance benchmark results?", "doom_testing_and_evaluation.md"),
    ("Find the exact MCP search_docs tool implementation", "doom_mcp_tools_and_security.md"),
    ("Find the exact PostgreSQL vector table doom_document_chunks", "doom_database_memory_and_rag.md"),
    ("Find the exact embedding model BAAI bge small en v1.5", "doom_database_memory_and_rag.md"),
    ("Find the exact owner authentication and session token implementation", "doom_mcp_tools_and_security.md"),
]

def percentile(values, p):
    s = sorted(values)
    return s[max(0, min(len(s) - 1, int(len(s) * p + 0.999999) - 1))]

def main():
    checks, results = [], []

    def check(name, passed, detail=""):
        checks.append({"name": name, "passed": bool(passed), "detail": str(detail)})
        print(f"{'PASS' if passed else 'FAIL'}  {name} {detail}")

    if not rag.RAG_AVAILABLE:
        raise RuntimeError("RAG is unavailable")

    with engine.connect() as conn:
        count, sources, dims = conn.execute(text(f"""
            SELECT COUNT(*), COUNT(DISTINCT source),
                   MIN(vector_dims(embedding))
            FROM {TABLE}
        """)).one()

        fts_column = conn.execute(text("""
            SELECT EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name = :table
                  AND column_name = 'search_vector'
                  AND is_generated = 'ALWAYS'
            )
        """), {"table": TABLE}).scalar()

        gin_index = conn.execute(text("""
            SELECT EXISTS (
                SELECT 1 FROM pg_indexes
                WHERE schemaname = 'public'
                  AND indexname = 'ix_doom_document_chunks_search_vector_gin'
            )
        """)).scalar()

        hnsw_index = conn.execute(text("""
            SELECT EXISTS (
                SELECT 1 FROM pg_indexes
                WHERE schemaname = 'public'
                  AND indexname = 'ix_doom_document_chunks_embedding_hnsw'
            )
        """)).scalar()

        lexical_test = conn.execute(text(f"""
            SELECT COUNT(*) FROM {TABLE}
            WHERE search_vector @@ websearch_to_tsquery(
                'english', 'doom_document_chunks'
            )
        """)).scalar()

    check("RAG module available", rag.RAG_AVAILABLE)
    check("Corpus present", count >= 8, f"{count} chunks / {sources} sources")
    check("384-dimensional embeddings", dims == 384, f"observed={dims}")
    check("Generated FTS column exists", fts_column)
    check("GIN lexical index exists", gin_index)
    check("HNSW vector index exists", hnsw_index)
    check("Lexical exact-term search returns matches", lexical_test > 0, f"matches={lexical_test}")
    check("Empty query handled safely", "Please provide" in rag.search_docs("   "))

    embedder = rag._embedder()
    list(embedder.embed(["DOOM hybrid RAG benchmark warmup"]))

    all_embedding, all_total = [], []
    hits, precisions, reciprocal_ranks = [], [], []

    print("\nWarm-up complete. Running 3 hybrid repetitions per query...")

    for query, expected in CASES:
        repetitions = []

        for run in range(3):
            started = time.perf_counter()

            output = rag.search_docs(query, n_results=5)

            elapsed = (time.perf_counter() - started) * 1000
            all_total.append(elapsed)

            retrieved = []
            for line in output.splitlines():
                if line.startswith("[") and " | chunk " in line:
                    retrieved.append(line.split(" | chunk ", 1)[0][1:])

            if output.startswith("Search error:"):
                raise RuntimeError(f"Search failed for {query}: {output}")

            rank = next(
                (i + 1 for i, source in enumerate(retrieved) if source == expected),
                None
            )

            repetitions.append(retrieved)
            hits.append(1 if rank else 0)
            precisions.append(sum(s == expected for s in retrieved) / 5)
            reciprocal_ranks.append(1 / rank if rank else 0)

            if run == 2:
                results.append({
                    "query": query,
                    "expected_source": expected,
                    "retrieved_sources": retrieved,
                    "rank": rank,
                    "end_to_end_ms": round(elapsed, 2)
                })

        stable = repetitions[0] == repetitions[1] == repetitions[2]
        check("Repeated hybrid retrieval stable: " + query[:48], stable)

    unknown = rag.search_docs(
        "qzxv nonexistent identifier 918273 xyz",
        n_results=5
    )
    check("Unknown query handled without exception",
          not unknown.startswith("Search error:"))

    metrics = {
        "queries": len(CASES),
        "repetitions_per_query": 3,
        "measured_searches": len(all_total),
        "corpus_chunks": int(count),
        "corpus_sources": int(sources),
        "source_hit_rate_at_5": round(statistics.mean(hits), 4),
        "source_precision_at_5": round(statistics.mean(precisions), 4),
        "source_mrr_at_5": round(statistics.mean(reciprocal_ranks), 4),
        "end_to_end_latency_avg_ms": round(statistics.mean(all_total), 2),
        "end_to_end_p50_ms": round(percentile(all_total, .50), 2),
        "end_to_end_p95_ms": round(percentile(all_total, .95), 2),
        "end_to_end_p99_ms": round(percentile(all_total, .99), 2),
        "end_to_end_max_ms": round(max(all_total), 2),
        "evaluation_type": "curated source-level smoke benchmark; not human-judged relevance",
        "retrieval_mode": "hybrid vector + PostgreSQL FTS + RRF",
        "latency_scope": "embedding + vector SQL + lexical SQL + RRF + result formatting"
    }

    check("Source hit rate at 5 >= 0.75",
          metrics["source_hit_rate_at_5"] >= .75,
          metrics["source_hit_rate_at_5"])

    report = {
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "target": "Neon PostgreSQL",
        "checks": checks,
        "metrics": metrics,
        "query_results": results
    }

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    jp = OUT / f"rag_hybrid_evaluation_{stamp}.json"
    mp = OUT / f"rag_hybrid_evaluation_{stamp}.md"

    jp.write_text(json.dumps(report, indent=2), encoding="utf-8")

    lines = [
        "# DOOM Hybrid RAG Evaluation",
        "",
        f"- Timestamp UTC: {report['timestamp_utc']}",
        f"- Corpus: {count} chunks / {sources} sources",
        "",
        "## Metrics",
        "",
        "| Metric | Value |",
        "|---|---:|"
    ]

    lines += [f"| {k} | {v} |" for k, v in metrics.items()]
    lines += ["", "## Checks", ""]
    lines += [
        f"- {'PASS' if c['passed'] else 'FAIL'} {c['name']} — {c['detail']}"
        for c in checks
    ]
    lines += ["", "## Query results", ""]
    lines += [
        f"- {r['expected_source']}: rank={r['rank']}, latency={r['end_to_end_ms']} ms"
        for r in results
    ]

    mp.write_text("\n".join(lines) + "\n", encoding="utf-8")

    passed = sum(c["passed"] for c in checks)

    print("\n========== HYBRID RAG EVALUATION ==========")
    print(json.dumps(metrics, indent=2))
    print(f"\nChecks: {passed}/{len(checks)} passed")
    print(f"Reports: {jp} | {mp}")

    return 0 if passed == len(checks) else 1

if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"FATAL: {type(exc).__name__}: {exc}", file=sys.stderr)
        raise SystemExit(2)
    finally:
        engine.dispose()
