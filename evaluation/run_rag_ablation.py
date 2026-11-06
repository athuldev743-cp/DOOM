import statistics
from sqlalchemy import text
from src.memory import rag
from src.memory.database import engine

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

def rank_source(rows, expected):
    sources = [r.source for r in rows]
    return next((i + 1 for i, s in enumerate(sources) if s == expected), None)

def metrics(ranks):
    return {
        "hit_rate@5": round(sum(r is not None for r in ranks) / len(ranks), 4),
        "MRR@5": round(statistics.mean([1/r if r else 0 for r in ranks]), 4),
    }

def main():
    embedder = rag._embedder()
    list(embedder.embed(["RAG ablation warmup"]))

    vector_ranks, lexical_ranks, hybrid_ranks = [], [], []

    for query, expected in CASES:
        qv = next(embedder.embed([
            "Represent this sentence for searching relevant passages: " + query
        ]))
        vector = rag._vector_literal(qv)

        with engine.connect() as conn:
            vector_rows = conn.execute(text(f"""
                SELECT source
                FROM {TABLE}
                ORDER BY embedding <=> CAST(:embedding AS vector)
                LIMIT 5
            """), {"embedding": vector}).all()

            lexical_rows = conn.execute(text(f"""
                SELECT source
                FROM {TABLE}
                WHERE search_vector @@ websearch_to_tsquery('english', :query)
                ORDER BY ts_rank_cd(
                    search_vector,
                    websearch_to_tsquery('english', :query)
                ) DESC
                LIMIT 5
            """), {"query": query}).all()

            hybrid_rows = conn.execute(text(f"""
                WITH vector_candidates AS (
                    SELECT id, source,
                           ROW_NUMBER() OVER (
                               ORDER BY embedding <=> CAST(:embedding AS vector)
                           ) AS position_rank
                    FROM {TABLE}
                    ORDER BY embedding <=> CAST(:embedding AS vector)
                    LIMIT 25
                ),
                lexical_candidates AS (
                    SELECT id, source,
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
                    LIMIT 25
                ),
                combined_ranks AS (
                    SELECT id, position_rank FROM vector_candidates
                    UNION ALL
                    SELECT id, position_rank FROM lexical_candidates
                ),
                fused AS (
                    SELECT id, SUM(1.0 / (60.0 + position_rank)) AS score
                    FROM combined_ranks
                    GROUP BY id
                )
                SELECT d.source
                FROM fused f
                JOIN {TABLE} d ON d.id = f.id
                ORDER BY f.score DESC
                LIMIT 5
            """), {"embedding": vector, "query": query}).all()

        vector_ranks.append(rank_source(vector_rows, expected))
        lexical_ranks.append(rank_source(lexical_rows, expected))
        hybrid_ranks.append(rank_source(hybrid_rows, expected))

    print("\n========== RETRIEVAL ABLATION ==========")
    for name, ranks in [
        ("VECTOR ONLY", vector_ranks),
        ("LEXICAL ONLY", lexical_ranks),
        ("HYBRID RRF", hybrid_ranks),
    ]:
        print(f"\n{name}")
        print(metrics(ranks))
        print("Ranks:", ranks)

    print("\n========== PER-QUERY COMPARISON ==========")
    for i, (query, expected) in enumerate(CASES):
        print(f"\n{query}")
        print(f"Expected: {expected}")
        print(
            f"Vector={vector_ranks[i]} | "
            f"Lexical={lexical_ranks[i]} | "
            f"Hybrid={hybrid_ranks[i]}"
        )

if __name__ == "__main__":
    try:
        main()
    finally:
        engine.dispose()
