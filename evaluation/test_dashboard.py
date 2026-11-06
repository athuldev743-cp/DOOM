from pydantic import ValidationError
import pytest

from src.api.deps import require_owner
from src.api.routes.evaluation import CATALOG, RunConfig, router


def test_dashboard_catalog_contains_all_required_modules():
    ids = {item["id"] for item in CATALOG}
    assert ids == {"rag", "mcp", "langgraph", "latency", "database", "security"}


def test_request_count_is_bounded():
    assert RunConfig(request_count=1).request_count == 1
    assert RunConfig(request_count=100).request_count == 100
    with pytest.raises(ValidationError):
        RunConfig(request_count=0)
    with pytest.raises(ValidationError):
        RunConfig(request_count=101)


def test_evaluation_routes_are_registered_and_owner_protected():
    routes = {(tuple(sorted(route.methods or [])), route.path) for route in router.routes}
    assert (("GET",), "/evaluation") in routes
    assert (("GET",), "/evaluation/api/catalog") in routes
    assert (("POST",), "/evaluation/api/run/{test_id}") in routes
    for route in router.routes:
        assert any(dependency.call is require_owner for dependency in route.dependant.dependencies)
