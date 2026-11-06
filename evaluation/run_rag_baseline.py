from __future__ import annotations
import json, statistics, time, sys
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
    return s[max(0, min(len(s)-1, int((len(s)*p + 0.999999))-1))]
def main():
    checks, results = [], []
    def check(name, passed, detail=""):
        checks.append({"name": name, "passed": bool(passed), "detail": str(detail)})
        print(f"{'PASS' if passed else 'FAIL'}  {name} {detail}")
    if not rag.RAG_AVAILABLE:
        raise RuntimeError("RAG is unavailable")
    with engine.connect() as conn:
        ext = conn.execute(text("SELECT EXISTS (SELECT 1 FROM pg_extension WHERE extname='vector')")).scalar()
        table = conn.execute(text("SELECT to_regclass('public.doom_document_chunks') IS NOT NULL")).scalar()
        count, dims, sources = conn.execute(text(f"SELECT COUNT(*), MIN(vector_dims(embedding)), COUNT(DISTINCT source) FROM {TABLE}")).one()
        duplicates = conn.execute(text(f"SELECT COUNT(*) FROM (SELECT source, chunk_index FROM {TABLE} GROUP BY source, chunk_index HAVING COUNT(*) > 1) d")).scalar()
        hnsw = conn.execute(text("SELECT EXISTS (SELECT 1 FROM pg_indexes WHERE schemaname='public' AND indexname='ix_doom_document_chunks_embedding_hnsw')")).scalar()
    check("pgvector extension enabled", ext)
    check("Dedicated RAG table exists", table)
    check("Indexed corpus present", count >= 8, f"{count} chunks / {sources} sources")
    check("384-dimensional embeddings", dims == 384, f"observed={dims}")
    check("HNSW index exists", hnsw)
    check("No duplicate source/chunk records", duplicates == 0, f"duplicates={duplicates}")
    check("RAG module available", rag.RAG_AVAILABLE)
    check("Empty query handled safely", "Please provide" in rag.search_docs("   "))
    # Initialize model and warm up before collecting latency.
    embedder = rag._embedder()
    list(embedder.embed(["DOOM RAG benchmark warmup"]))
    print("\nWarm-up complete. Running 3 measured repetitions per query...")
    all_embedding, all_db, all_e2e = [], [], []
    reciprocal_ranks, hits, precisions = [], [], []
    for query, expected in CASES:
        repetitions = []
        for run in range(3):
            t0 = time.perf_counter()
            qv = next(embedder.embed(["Represent this sentence for searching relevant passages: " + query]))
            t1 = time.perf_counter()
            vector = rag._vector_literal(qv)
            with engine.connect() as conn:
                rows = conn.execute(text(f"""
                    SELECT source, chunk_index
                    FROM {TABLE}
                    ORDER BY embedding <=> CAST(:embedding AS vector)
                    LIMIT 5
                """), {"embedding": vector}).all()
            t2 = time.perf_counter()
            emb_ms, db_ms, e2e_ms = (t1-t0)*1000, (t2-t1)*1000, (t2-t0)*1000
            all_embedding.append(emb_ms); all_db.append(db_ms); all_e2e.append(e2e_ms)
            ranked = [r.source for r in rows]
            rank = next((i+1 for i,s in enumerate(ranked) if s == expected), None)
            repetitions.append(ranked)
            reciprocal_ranks.append(1/rank if rank else 0)
            hits.append(1 if rank else 0)
            precisions.append(sum(1 for s in ranked if s == expected)/5)
            if run == 2:
                results.append({"query": query, "expected_source": expected, "retrieved_sources": ranked, "rank": rank, "embedding_ms": round(emb_ms,2), "database_ms": round(db_ms,2), "end_to_end_ms": round(e2e_ms,2)})
        stable = repetitions[0] == repetitions[1] == repetitions[2]
        check("Repeated retrieval stable: " + query[:55], stable)
    unknown = rag.search_docs("qzxv nonexistent identifier 918273 xyz", n_results=5)
    check("Unknown query handled without exception", not unknown.startswith("Search error:"), unknown[:100])
    metrics = {
        "queries": len(CASES), "repetitions_per_query": 3, "measured_searches": len(all_e2e),
        "corpus_chunks": int(count), "corpus_sources": int(sources),
        "source_hit_rate_at_5": round(statistics.mean(hits),4),
        "source_precision_at_5": round(statistics.mean(precisions),4),
        "source_mrr_at_5": round(statistics.mean(reciprocal_ranks),4),
        "embedding_latency_avg_ms": round(statistics.mean(all_embedding),2),
        "database_latency_avg_ms": round(statistics.mean(all_db),2),
        "end_to_end_latency_avg_ms": round(statistics.mean(all_e2e),2),
        "end_to_end_p50_ms": round(percentile(all_e2e,.50),2),
        "end_to_end_p95_ms": round(percentile(all_e2e,.95),2),
        "end_to_end_p99_ms": round(percentile(all_e2e,.99),2),
        "end_to_end_max_ms": round(max(all_e2e),2),
        "evaluation_type": "curated source-level smoke benchmark; not human-judged relevance",
        "retrieval_mode": "vector-only baseline"
    }
    check("Source hit rate at 5 >= 0.75", metrics["source_hit_rate_at_5"] >= .75, str(metrics["source_hit_rate_at_5"]))
    report = {"timestamp_utc": datetime.now(timezone.utc).isoformat(), "target":"Neon PostgreSQL", "checks":checks, "metrics":metrics, "query_results":results}
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    jp, mp = OUT/f"rag_vector_baseline_{stamp}.json", OUT/f"rag_vector_baseline_{stamp}.md"
    jp.write_text(json.dumps(report, indent=2), encoding="utf-8")
    lines = ["# DOOM Vector-only RAG Baseline", "", f"- Timestamp UTC: {report['timestamp_utc']}", f"- Corpus: {count} chunks / {sources} sources", "", "## Metrics", "", "| Metric | Value |", "|---|---:|"]
    lines += [f"| {k} | {v} |" for k,v in metrics.items()]
    lines += ["", "## Checks", ""] + [f"- {'PASS' if c['passed'] else 'FAIL'} {c['name']} — {c['detail']}" for c in checks]
    lines += ["", "## Query results", ""] + [f"- {r['expected_source']}: rank={r['rank']}, embedding={r['embedding_ms']} ms, DB={r['database_ms']} ms, end-to-end={r['end_to_end_ms']} ms" for r in results]
    mp.write_text("\n".join(lines)+"\n", encoding="utf-8")
    passed = sum(c["passed"] for c in checks)
    print("\n========== VECTOR-ONLY BASELINE ==========")
    print(json.dumps(metrics, indent=2))
    print(f"\nChecks: {passed}/{len(checks)} passed")
    print(f"Reports: {jp} | {mp}")
    return 0 if passed == len(checks) else 1
if __name__ == "__main__":
    try: raise SystemExit(main())
    except Exception as e:
        print(f"FATAL: {type(e).__name__}: {e}", file=sys.stderr)
        raise SystemExit(2)
    finally: engine.dispose()
