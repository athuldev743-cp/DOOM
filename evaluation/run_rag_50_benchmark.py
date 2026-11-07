from __future__ import annotations

import json
import statistics
import time
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import text
from src.memory import rag
from src.memory.database import engine

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "evaluation" / "results" / "local"
OUT.mkdir(parents=True, exist_ok=True)
TABLE = "doom_document_chunks"

# 50 curated queries: direct, paraphrased, keyword-poor and multi-hop.
GROUPS = [
    ("doom_project_overview.md", [
        "What is DOOM and what backend framework does it use?",
        "Explain the main purpose and architecture of the DOOM assistant.",
        "Which Python backend powers the personal AI assistant?",
        "Describe DOOM's backend and its main responsibilities.",
        "How does the assistant combine its backend services into one system?",
    ]),
    ("doom_mcp_tools_and_security.md", [
        "Which MCP tools are registered and how are side effects protected?",
        "How does DOOM expose its tools through MCP securely?",
        "What prevents unauthorized users from invoking owner-only tools?",
        "Explain the authentication and authorization flow for MCP requests.",
        "How are tool access, owner identity and external actions controlled?",
    ]),
    ("doom_agent_workflow.md", [
        "How does the LangGraph agent route requests and execute tools safely?",
        "Explain the agent's decision, validation and execution workflow.",
        "What happens when the model generates invalid tool arguments?",
        "How does the graph retry a failed tool call?",
        "How are model decisions connected to validated tool execution?",
    ]),
    ("doom_database_memory_and_rag.md", [
        "How does DOOM use PostgreSQL, pgvector, embeddings and semantic retrieval?",
        "Explain how documents become searchable in the RAG system.",
        "Which database stores the vector representations?",
        "How does DOOM retrieve relevant knowledge from stored documents?",
        "How do vector search and keyword search work together?",
    ]),
    ("doom_job_search_and_application_workflow.md", [
        "How does DOOM discover jobs, score job descriptions and track applications?",
        "Explain the workflow from finding a job to tracking an application.",
        "How are job descriptions evaluated against a candidate profile?",
        "What information is retained for each job application?",
        "How does the job workflow connect discovery, CV preparation and tracking?",
    ]),
    ("fitness_ai_coach_project.md", [
        "What is the separate fitness AI coach project and its planned architecture?",
        "Explain the fitness coach's intended backend and agent architecture.",
        "How will the fitness system adapt training to a user's goals and equipment?",
        "Which components are planned for exercise recommendations and nutrition?",
        "How does the fitness project combine user profiles, plans and retrieval?",
    ]),
    ("career_profile_and_cv_goals.md", [
        "What AI engineering roles and CV project metrics is the user targeting?",
        "Which technical roles are being targeted for international applications?",
        "Summarize the candidate's relevant backend and AI engineering experience.",
        "What measurable performance improvements are documented in the CV?",
        "Which projects and technologies support the candidate's AI engineering profile?",
    ]),
    ("doom_testing_and_evaluation.md", [
        "What are DOOM's historical pytest coverage and performance benchmark results?",
        "Which tests measure reliability and system performance?",
        "What historical latency and test results are documented?",
        "How is the backend evaluated for security and reliability?",
        "Which evaluation methods are used to assess the assistant?",
    ]),
    ("doom_mcp_tools_and_security.md", [
        "Find the exact MCP search_docs tool implementation.",
        "Which component exposes document search to MCP clients?",
        "How can a client search the private knowledge base?",
        "Trace the document-search tool from MCP to its backend function.",
        "How are document retrieval requests exposed to the agent?",
    ]),
    ("doom_database_memory_and_rag.md", [
        "Find the exact PostgreSQL vector table doom_document_chunks.",
        "Which table stores the document chunks and embeddings?",
        "Where are the indexed knowledge passages stored?",
        "Identify the database table used by semantic document search.",
        "Which table, embedding model and retrieval method support DOOM's RAG?",
    ]),
]

# Manually classified query types, in the same order as GROUPS.
QUERY_TYPES = [
    # Project overview
    "direct", "paraphrased", "keyword_poor", "direct", "multi_hop",
    # MCP and security
    "direct", "paraphrased", "keyword_poor", "multi_hop", "multi_hop",
    # Agent workflow
    "multi_hop", "paraphrased", "direct", "direct", "multi_hop",
    # Database and RAG
    "technical_identifier", "paraphrased", "keyword_poor", "direct", "multi_hop",
    # Job workflow
    "multi_hop", "paraphrased", "keyword_poor", "direct", "multi_hop",
    # Fitness project
    "direct", "paraphrased", "keyword_poor", "multi_hop", "multi_hop",
    # Career profile
    "direct", "paraphrased", "keyword_poor", "direct", "multi_hop",
    # Testing and evaluation
    "technical_identifier", "paraphrased", "keyword_poor", "direct", "multi_hop",
    # MCP search tool
    "technical_identifier", "direct", "paraphrased", "multi_hop", "paraphrased",
    # PostgreSQL table and retrieval
    "technical_identifier", "direct", "keyword_poor", "direct", "multi_hop",
]

CASES = [
    (query, source, query_type)
    for (source, queries), group_types in zip(
        GROUPS, [QUERY_TYPES[i:i + 5] for i in range(0, 50, 5)]
    )
    for query, query_type in zip(queries, group_types)
]
assert len(CASES) == 50

def percentile(values, p):
    values = sorted(values)
    return values[max(0, min(len(values) - 1,
        int(len(values) * p + 0.999999) - 1))]

def quality(ranks, precision_scores):
    return {
        "queries": len(ranks),
        "hit_rate_at_5": round(sum(r is not None for r in ranks) / len(ranks), 4),
        "MRR_at_5": round(statistics.mean([1 / r if r else 0 for r in ranks]), 4),
        "precision_at_5": round(statistics.mean(precision_scores), 4),
    }

def latency(values):
    return {
        "avg_ms": round(statistics.mean(values), 2),
        "p50_ms": round(percentile(values, .50), 2),
        "p95_ms": round(percentile(values, .95), 2),
        "p99_ms": round(percentile(values, .99), 2),
        "max_ms": round(max(values), 2),
    }

def rank_source(rows, expected):
    return next(
        (i + 1 for i, row in enumerate(rows) if row.source == expected),
        None,
    )

def main():
    if not rag.RAG_AVAILABLE:
        raise RuntimeError("RAG is unavailable")

    embedder = rag._embedder()
    list(embedder.embed(["DOOM 50 query benchmark warmup"]))

    sql = {
        "vector": f"""
            SELECT source
            FROM {TABLE}
            ORDER BY embedding <=> CAST(:embedding AS vector)
            LIMIT 5
        """,
        "lexical": f"""
            SELECT source
            FROM {TABLE}
            WHERE search_vector @@ websearch_to_tsquery('english', :query)
            ORDER BY ts_rank_cd(
                search_vector,
                websearch_to_tsquery('english', :query)
            ) DESC
            LIMIT 5
        """,
        "hybrid": f"""
            WITH vector_candidates AS (
                SELECT id,
                    ROW_NUMBER() OVER (
                        ORDER BY embedding <=> CAST(:embedding AS vector)
                    ) AS position_rank
                FROM {TABLE}
                ORDER BY embedding <=> CAST(:embedding AS vector)
                LIMIT 20
            ),
            lexical_candidates AS (
                SELECT id,
                    ROW_NUMBER() OVER (
                        ORDER BY ts_rank_cd(
                            search_vector,
                            websearch_to_tsquery('english', :query)
                        ) DESC
                    ) AS position_rank
                FROM {TABLE}
                WHERE search_vector @@ websearch_to_tsquery('english', :query)
                ORDER BY ts_rank_cd(
                    search_vector,
                    websearch_to_tsquery('english', :query)
                ) DESC
                LIMIT 20
            ),
            combined AS (
                SELECT id, position_rank FROM vector_candidates
                UNION ALL
                SELECT id, position_rank FROM lexical_candidates
            ),
            fused AS (
                SELECT id, SUM(1.0 / (60.0 + position_rank)) AS score
                FROM combined
                GROUP BY id
            )
            SELECT d.source
            FROM fused f
            JOIN {TABLE} d ON d.id = f.id
            ORDER BY f.score DESC
            LIMIT 5
        """,
    }

    ranks = {name: [] for name in sql}
    precision_scores = {name: [] for name in sql}
    sql_times = {name: [] for name in sql}
    embedding_times, connection_times = [], []
    results = []

    print("Running 50 queries across vector, lexical and hybrid retrieval...")

    for index, (query, expected, query_type) in enumerate(CASES, 1):
        started = time.perf_counter()

        t = time.perf_counter()
        vector_values = next(embedder.embed([
            "Represent this sentence for searching relevant passages: " + query
        ]))
        vector = rag._vector_literal(vector_values)
        embedding_ms = (time.perf_counter() - t) * 1000
        embedding_times.append(embedding_ms)

        t = time.perf_counter()
        with engine.connect() as conn:
            connection_ms = (time.perf_counter() - t) * 1000
            connection_times.append(connection_ms)

            row_results = {}
            for mode in ("vector", "lexical", "hybrid"):
                t = time.perf_counter()
                row_results[mode] = conn.execute(
                    text(sql[mode]),
                    {"embedding": vector, "query": query},
                ).all()
                sql_ms = (time.perf_counter() - t) * 1000
                sql_times[mode].append(sql_ms)

        query_result = {
            "query": query,
            "expected_source": expected,
            "query_type": query_type,
        }
        for mode in sql:
            rank = rank_source(row_results[mode], expected)
            ranks[mode].append(rank)
            relevant_count = sum(1 for row in row_results[mode] if row.source == expected)
            precision_scores[mode].append(relevant_count / 5)
            query_result[mode + "_rank"] = rank
        query_result["embedding_ms"] = round(embedding_ms, 2)
        query_result["db_connection_ms"] = round(connection_ms, 2)
        results.append(query_result)

        if index % 10 == 0:
            print(f"Completed {index}/50")

        # Keep the total measured duration for sanity checking.
        query_result["total_benchmark_ms"] = round(
            (time.perf_counter() - started) * 1000, 2
        )

    category_metrics = {}
    for query_type in sorted(set(QUERY_TYPES)):
        category_metrics[query_type] = {}
        for mode in sql:
            category_ranks = [
                ranks[mode][i]
                for i, case in enumerate(CASES)
                if case[2] == query_type
            ]
            category_precision = [
                precision_scores[mode][i]
                for i, case in enumerate(CASES)
                if case[2] == query_type
            ]
            category_metrics[query_type][mode] = quality(
                category_ranks, category_precision
            )

    modes = {}
    for mode in sql:
        e2e = [
            embedding_times[i] + connection_times[i] + sql_times[mode][i]
            for i in range(len(CASES))
        ]
        modes[mode] = {
            **quality(ranks[mode], precision_scores[mode]),
            "sql_latency": latency(sql_times[mode]),
            "estimated_end_to_end_latency": latency(e2e),
        }

    report = {
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "target": "PostgreSQL + pgvector",
        "query_count": len(CASES),
        "query_types": {
            category: QUERY_TYPES.count(category)
            for category in sorted(set(QUERY_TYPES))
        },
        "latency_breakdown": {
            "embedding": latency(embedding_times),
            "db_connection_acquisition": latency(connection_times),
            "vector_sql": latency(sql_times["vector"]),
            "lexical_sql": latency(sql_times["lexical"]),
            "hybrid_sql_including_rrf_fusion": latency(sql_times["hybrid"]),
        },
        "retrieval_modes": modes,
        "category_metrics": category_metrics,
        "candidate_limit": 20,
        "rrf_k": 60,
        "notes": [
            "Source-level relevance benchmark, not human-judged passage relevance.",
            "Hit@5 and MRR@5 use the expected source filename.",
            "Precision@5 is relevant chunks from the expected source divided by five returned slots.",
            "Hybrid SQL timing includes PostgreSQL RRF fusion and result ordering.",
            "Estimated end-to-end latency is embedding + connection acquisition + that mode's SQL.",
            "LLM generation is not part of this retrieval-only benchmark.",
            "Hybrid candidate limit is 20, aligned with production default n_results=3.",
        ],
        "query_results": results,
    }

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    json_path = OUT / f"rag_50_query_benchmark_{stamp}.json"
    md_path = OUT / f"rag_50_query_benchmark_{stamp}.md"

    json_path.write_text(json.dumps(report, indent=2), encoding="utf-8")

    lines = [
        "# DOOM 50-query RAG benchmark",
        "",
        f"- Timestamp: {report['timestamp_utc']}",
        "- Queries: 50",
        "",
        "## Retrieval quality",
        "",
        "| Mode | Hit@5 | MRR@5 | Precision@5 |",
        "|---|---:|---:|---:|",
    ]
    for mode, data in modes.items():
        lines.append(
            f"| {mode} | {data['hit_rate_at_5']} | {data['MRR_at_5']} "
            f"| {data['precision_at_5']} |"
        )

    lines += [
        "",
        "## Category-wise retrieval quality",
        "",
        "| Category | Mode | Queries | Hit@5 | MRR@5 | Precision@5 |",
        "|---|---|---:|---:|---:|---:|",
    ]
    for category, category_data in category_metrics.items():
        for mode, data in category_data.items():
            lines.append(
                f"| {category} | {mode} | {data['queries']} "
                f"| {data['hit_rate_at_5']} | {data['MRR_at_5']} "
                f"| {data['precision_at_5']} |"
            )

    lines += [
        "",
        "## Latency breakdown (ms)",
        "",
        "| Stage | Average | p50 | p95 | p99 |",
        "|---|---:|---:|---:|---:|",
    ]
    for stage, data in report["latency_breakdown"].items():
        lines.append(
            f"| {stage} | {data['avg_ms']} | {data['p50_ms']} "
            f"| {data['p95_ms']} | {data['p99_ms']} |"
        )

    lines += ["", "## Notes", ""] + [f"- {n}" for n in report["notes"]]
    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    print("\n========== 50-QUERY RAG RESULTS ==========")
    print(json.dumps({
        "query_count": 50,
        "retrieval_modes": modes,
        "latency_breakdown": report["latency_breakdown"],
    }, indent=2))
    print(f"\nJSON: {json_path}")
    print(f"Markdown: {md_path}")

if __name__ == "__main__":
    try:
        main()
    finally:
        engine.dispose()
