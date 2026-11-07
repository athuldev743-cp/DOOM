from unittest.mock import AsyncMock, patch

import pytest

from src.api.routes.production_evaluation import (
    ProductionRunConfig, MODULES, run_rag_concurrency,
)


def test_production_catalog_has_expected_modules():
    assert {item["id"] for item in MODULES} == {
        "rag_concurrency", "langgraph_trace", "failure_recovery", "security"
    }


def test_production_config_is_bounded():
    assert ProductionRunConfig(concurrency=10, requests=40).requests == 40
    with pytest.raises(Exception):
        ProductionRunConfig(concurrency=11)
    with pytest.raises(Exception):
        ProductionRunConfig(requests=41)


def test_production_routes_are_owner_protected():
    from src.api.routes.production_evaluation import router
    from src.api.deps import require_owner

    for route in router.routes:
        assert any(dep.call is require_owner for dep in route.dependant.dependencies)


def test_external_k6_scripts_are_present_and_configurable():
    from pathlib import Path

    load = Path("evaluation/k6/production-load.js").read_text(encoding="utf-8")
    mcp = Path("evaluation/k6/mcp-streamable-http.js").read_text(encoding="utf-8")
    assert "constant-vus" in load
    assert "p(95)" in load and "p(99)" in load
    assert "tools/list" in mcp
    assert "DOOM_SESSION" in mcp


def test_rag_concurrency_uses_bounded_parallelism():
    import inspect
    from src.api.routes.production_evaluation import run_rag_concurrency

    source = inspect.getsource(run_rag_concurrency)
    assert "asyncio.Semaphore(concurrency)" in source
    assert "asyncio.gather" in source
