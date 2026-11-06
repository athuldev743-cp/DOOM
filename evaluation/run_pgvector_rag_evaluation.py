"""Read-only functional and retrieval-quality checks for DOOM's pgvector RAG."""

from __future__ import annotations

import json
import statistics
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import text
from fastembed import TextEmbedding
from src.memory.database import engine
from src.memory import rag

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "evaluation" / "results" / "local"
OUT.mkdir(parents=True, exist_ok=True)
TABLE = "doom_document_chunks"
MODEL = "BAAI/bge-small-en-v1.5"

CASES = [
    ("What is DOOM and what backend framework does it use?", "doom_project_overview.md"),
    ("Which MCP tools are registered and how are side effects protected?", "doom_mcp_tools_and_security.md"),
    ("How does the LangGraph agent route requests and execute tools safely?", "doom_agent_workflow.md"),
    ("How does DOOM use PostgreSQL, pgvector, embeddings and semantic retrieval?", "doom_database_memory_and_rag.md"),
    ("How does DOOM discover jobs, score job descriptions and track applications?", "doom_job_search_and_application_workflow.md"),
    ("What is the separate fitness AI coach project and its planned architecture?", "fitness_ai_coach_project.md"),
    ("What AI engineering roles and CV project metrics is the user targeting?", "career_profile_and_cv_goals.md"),
    ("What are DOOM's historical pytest coverage and performance benchmark results?", "doom_testing_and_evaluation.md"),
]

def main() -> int:
    results = []
    checks = []

    def check(name, passed, detail=""):
        checks.append({"name": name, "passed": bool(passed), "detail": str(detail)})
        print(f"{'PASS' if passed else 'FAIL'}  {name}" + (f" — {detail}" if detail else ""))

    try:
        with engine.connect() as conn:
            ext = conn.execute(text(
                "SELECT EXISTS (SELECT 1 FROM pg_extension WHERE extname='vector')"
            )).scalar()
            check("pgvector extension enabled", ext)

            table_exists = conn.execute(text(
                "SELECT to_regclass('public.doom_document_chunks') IS NOT NULL"
            )).scalar()
            check("Dedicated document table exists", table_exists)
            if not table_exists:
                raise RuntimeError("doom_document_chunks table is missing")

            count, dimensions, unique_sources = conn.execute(text(f"""
                SELECT COUNT(*), MIN(vector_dims(embedding)), COUNT(DISTINCT source)
                FROM {TABLE}
            """)).one()
            check("Seeded documents present", count >= 8, f"{count} chunks, {unique_sources} sources")
            check("Embedding dimensions are 384", dimensions == 384, f"observed={dimensions}")

            index_exists = conn.execute(text("""
                SELECT EXISTS (
                    SELECT 1 FROM pg_indexes
                    WHERE schemaname='public'
                      AND indexname='ix_doom_document_chunks_embedding_hnsw'
                )
            """)).scalar()
            check("HNSW index exists", index_exists)

        check("RAG module available", rag.RAG_AVAILABLE)
        listing = rag.list_docs()
        check("list_docs returns indexed sources", "doom_project_overview.md" in listing, listing[:250])

        search_output = rag.search_docs("How does DOOM use LangGraph and MCP?", n_results=3)
        check("search_docs returns retrieved content", "Search error:" not in search_output and len(search_output) > 30, search_output[:180])

        embedder = TextEmbedding(model_name=MODEL)
        reciprocal_ranks = []
        recalls = []
        precisions = []
        latencies = []

        for query, expected_source in CASES:
            query_vector = next(embedder.embed([
                "Represent this sentence for searching relevant passages: " + query
            ]))
            vector_literal = "[" + ",".join(f"{float(v):.8f}" for v in query_vector) + "]"

            started = time.perf_counter()
            with engine.connect() as conn:
                rows = conn.execute(text(f"""
                    SELECT source
                    FROM {TABLE}
                    ORDER BY embedding <=> CAST(:embedding AS vector)
                    LIMIT 5
                """), {"embedding": vector_literal}).scalars().all()
            latencies.append((time.perf_counter() - started) * 1000)

            rank = next((i + 1 for i, source in enumerate(rows) if source == expected_source), None)
            reciprocal_ranks.append(1.0 / rank if rank else 0.0)
            recalls.append(1.0 if rank else 0.0)
            precisions.append(sum(1 for source in rows if source == expected_source) / 5.0)
            results.append({
                "query": query,
                "expected_source": expected_source,
                "retrieved_sources": rows,
                "rank": rank,
                "reciprocal_rank": 1.0 / rank if rank else 0.0,
                "latency_ms": round(latencies[-1], 3),
            })

        metrics = {
            "recall_at_5": statistics.mean(recalls),
            "precision_at_5": statistics.mean(precisions),
            "mrr_at_5": statistics.mean(reciprocal_ranks),
            "mean_retrieval_latency_ms": statistics.mean(latencies),
            "p95_retrieval_latency_ms": sorted(latencies)[max(0, int(len(latencies) * 0.95 + 0.999) - 1)],
            "queries": len(CASES),
            "corpus_chunks": int(count),
            "corpus_sources": int(unique_sources),
            "embedding_model": MODEL,
            "embedding_dimensions": int(dimensions),
            "evaluation_type": "small curated smoke benchmark; not a general quality claim",
        }

        check("Recall@5 >= 0.75", metrics["recall_at_5"] >= 0.75, f"{metrics['recall_at_5']:.3f}")
        check("MRR@5 >= 0.75", metrics["mrr_at_5"] >= 0.75, f"{metrics['mrr_at_5']:.3f}")
        check("All eight benchmark queries executed", len(results) == 8)

        report = {
            "timestamp_utc": datetime.now(timezone.utc).isoformat(),
            "target": "Neon PostgreSQL",
            "checks": checks,
            "metrics": metrics,
            "query_results": results,
        }
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        json_path = OUT / f"rag_pgvector_{stamp}.json"
        md_path = OUT / f"rag_pgvector_{stamp}.md"
        json_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
        lines = [
            "# DOOM pgvector RAG Evaluation",
            "",
            f"- Timestamp (UTC): {report['timestamp_utc']}",
            f"- Target: {report['target']}",
            f"- Corpus: {count} chunks across {unique_sources} sources",
            f"- Embedding: {MODEL} ({dimensions} dimensions)",
            "",
            "## Metrics",
            "",
            "| Metric | Result |",
            "|---|---:|",
            f"| Recall@5 | {metrics['recall_at_5']:.3f} |",
            f"| Precision@5 | {metrics['precision_at_5']:.3f} |",
            f"| MRR@5 | {metrics['mrr_at_5']:.3f} |",
            f"| Mean retrieval latency | {metrics['mean_retrieval_latency_ms']:.2f} ms |",
            f"| p95 retrieval latency | {metrics['p95_retrieval_latency_ms']:.2f} ms |",
            "",
            "## Query results",
            "",
        ]
        for item in results:
            lines.append(f"- **{item['expected_source']}** — rank={item['rank']}, latency={item['latency_ms']:.2f} ms")
        lines += ["", "> Small curated smoke benchmark; results are not a general retrieval-quality claim.", ""]
        md_path.write_text("\n".join(lines), encoding="utf-8")

        passed = sum(1 for item in checks if item["passed"])
        failed = len(checks) - passed
        print(f"\nChecks: {passed} passed, {failed} failed")
        print("Metrics:", json.dumps(metrics, indent=2))
        print(f"Reports: {json_path} | {md_path}")
        return 0 if failed == 0 else 1
    except Exception as exc:
        print(f"FATAL: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2
    finally:
        engine.dispose()

if __name__ == "__main__":
    raise SystemExit(main())
