import asyncio
import json
import os
import re
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "evaluation" / "results" / "latest"

sys.path.insert(0, str(ROOT))
os.environ["PYTHONPATH"] = str(ROOT) + os.pathsep + os.environ.get("PYTHONPATH", "")

RESULTS.mkdir(parents=True, exist_ok=True)


def run_async(coro):
    return asyncio.run(coro)


def determine_status(data):
    if not isinstance(data, dict):
        return "PARTIAL"

    status = str(data.get("status", "")).lower()
    if status in ("pass", "passed", "success"):
        return "PASS"
    if status in ("fail", "failed", "error"):
        return "FAIL"

    checks = data.get("checks")

    if isinstance(checks, list) and checks:
        statuses = [
            str(check.get("status", "")).lower()
            for check in checks
            if isinstance(check, dict)
        ]

        if any(s in ("failed", "fail", "error") for s in statuses):
            return "FAIL"

        if statuses and all(s in ("passed", "pass", "success") for s in statuses):
            return "PASS"

        return "PARTIAL"

    if data.get("passed") is True:
        return "PASS"
    if data.get("passed") is False:
        return "FAIL"

    return "PARTIAL"

def save_category(name, status, data, duration):
    result = {
        "category": name,
        "status": status,
        "duration_seconds": round(duration, 2),
        "data": data,
    }

    path = RESULTS / f"{name}.json"
    path.write_text(json.dumps(result, indent=2, default=str), encoding="utf-8")
    return result


def run_category(name, function):
    print(f"\n{'=' * 65}")
    print(f"  {name.upper()}")
    print("=" * 65)

    started = time.perf_counter()

    try:
        data = function()
        status = determine_status(data)
    except Exception as exc:
        data = {"error": str(exc), "exception": type(exc).__name__}
        status = "FAIL"

    duration = time.perf_counter() - started
    result = save_category(name, status, data, duration)

    print(f"Status: {status}")
    print(f"Duration: {duration:.2f}s")

    if status == "FAIL":
        print(json.dumps(data, indent=2, default=str)[:3000])

    return result


def run_agent_quality():
    command = [
        sys.executable,
        "-m",
        "pytest",
        "-q",
        "tests/test_functional_reliability.py",
        "-k",
        "executes_through_graph",
        "--tb=short",
    ]

    completed = subprocess.run(
        command,
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=180,
    )

    output = (completed.stdout + "\n" + completed.stderr).strip()
    match = re.search(r"(\d+) passed", output)

    passed = int(match.group(1)) if match else 0
    failed_match = re.search(r"(\d+) failed", output)
    failed = int(failed_match.group(1)) if failed_match else 0

    return {
        "status": "PASS" if completed.returncode == 0 and passed > 0 else "FAIL",
        "passed_scenarios": passed,
        "failed_scenarios": failed,
        "scope": "Deterministic LangGraph integration tests with mocked dependencies",
        "real_external_actions": False,
        "output": output[-5000:],
    }


def main():
    print("\nDOOM — UNIFIED ENGINEERING EVALUATION")
    print("Local evaluation | Sequential execution | No k6 load test")
    print(f"Started: {datetime.now(timezone.utc).isoformat()}")

    from src.api.routes import evaluation as evaluation_routes
    from src.api.routes import production_evaluation as production_routes

    results = []

    # 1. Retrieval quality
    results.append(
        run_category(
            "retrieval",
            lambda: evaluation_routes._run_rag(repetitions=1),
        )
    )

    # 2. Performance: lightweight in-process RAG concurrency test
    results.append(
        run_category(
            "performance",
            lambda: run_async(
                production_routes.run_rag_concurrency(
                    concurrency=2,
                    requests=6,
                )
            ),
        )
    )

    # 3. Reliability: synthetic fault injection and fallback recovery
    results.append(
        run_category(
            "reliability",
            lambda: run_async(production_routes.run_failure_checks()),
        )
    )

    # 4. Agent quality: safe mocked graph execution scenarios
    results.append(
        run_category(
            "agent_quality",
            run_agent_quality,
        )
    )

    # 5. Security: authentication and authorization checks
    results.append(
        run_category(
            "security",
            lambda: run_async(production_routes.run_security_checks()),
        )
    )

    statuses = [item["status"] for item in results]
    overall = (
        "PASS" if all(s == "PASS" for s in statuses)
        else "FAIL" if "FAIL" in statuses
        else "PARTIAL"
    )

    report = {
        "project": "DOOM AI",
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "environment": "local evaluation runner",
        "overall_status": overall,
        "categories": results,
    }

    json_path = RESULTS / "summary.json"
    json_path.write_text(
        json.dumps(report, indent=2, default=str),
        encoding="utf-8",
    )

    lines = [
        "# DOOM Engineering Evaluation",
        "",
        f"- **Overall status:** {overall}",
        f"- **Timestamp (UTC):** {report['timestamp_utc']}",
        "- **Execution:** Sequential",
        "- **Environment:** Local runner",
        "- **Production load test:** Not executed",
        "",
        "| Category | Status | Duration |",
        "|---|---|---:|",
    ]

    for item in results:
        lines.append(
            f"| {item['category']} | {item['status']} "
            f"| {item['duration_seconds']}s |"
        )

    lines.extend([
        "",
        "## Detailed results",
        "",
    ])

    for item in results:
        lines.extend([
            f"### {item['category']}",
            "",
            "```json",
            json.dumps(item["data"], indent=2, default=str),
            "```",
            "",
        ])

    md_path = RESULTS / "summary.md"
    md_path.write_text("\n".join(lines), encoding="utf-8")

    print("\n" + "=" * 65)
    print("FINAL EVALUATION")
    print("=" * 65)

    for item in results:
        print(f"{item['category']:<20} {item['status']}")

    print(f"\nOVERALL: {overall}")
    print(f"JSON report: {json_path}")
    print(f"Markdown report: {md_path}")

    return 0 if overall == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
