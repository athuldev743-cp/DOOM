from __future__ import annotations

import asyncio
import json
import time
from datetime import datetime, timezone
from pathlib import Path

from src.agent import graph
from src.tools.registry import get_tool as real_get_tool

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "evaluation" / "results" / "local"
OUT.mkdir(parents=True, exist_ok=True)

TASKS = [
    ("web_search", "Search the web for a Python FastAPI tutorial."),
    ("get_datetime", "Get the current date and time."),
    ("save_reminder", "Save a reminder for tomorrow."),
    ("list_reminders", "List saved reminders."),
    ("automate", "Run an automation workflow."),
    ("search_docs", "Search the private knowledge base."),
    ("ingest_docs", "Index a document into the knowledge base."),
    ("list_docs", "List indexed documents."),
    ("call_contact", "Prepare a call to a saved contact."),
    ("whatsapp_contact", "Prepare a WhatsApp message for a contact."),
    ("add_contact", "Add a contact to the address book."),
    ("list_contacts", "List saved contacts."),
    ("set_profile", "Update a profile field."),
    ("get_profile", "Retrieve the user profile."),
    ("whatsapp_resume", "Prepare a resume for a contact."),
    ("read_emails", "Read recent emails."),
    ("send_email", "Prepare an email for sending."),
    ("summarize_inbox", "Summarize the email inbox."),
    ("job_search", "Search for relevant job listings."),
    ("score_jd", "Score a job description against a CV."),
]

class SafeEvaluationTool:
    args_schema = None

    def __init__(self, name):
        self.name = name
        self.executions = 0

    def parse_args(self, raw):
        return json.loads(raw)

    def run(self, **kwargs):
        self.executions += 1
        return f"SAFE_EVALUATION_SUCCESS:{self.name}"

async def run_one(name, prompt):
    fake_tool = SafeEvaluationTool(name)
    calls = {"count": 0}

    def fake_get_tool(requested_name):
        return fake_tool if requested_name == name else None

    async def fake_chat(messages):
        calls["count"] += 1
        if calls["count"] == 1:
            args = json.dumps({"task": prompt})
            return f"TOOL: {name}\nARGS: {args}"
        return "Task completed successfully."

    original_get_tool = graph.get_tool
    original_chat = graph.chat

    graph.get_tool = fake_get_tool
    graph.chat = fake_chat

    started = time.perf_counter()
    try:
        response = await graph.run_graph([
            {"role": "system", "content": "Evaluation-only safe agent."},
            {"role": "user", "content": prompt},
        ])
        elapsed_ms = (time.perf_counter() - started) * 1000

        passed = (
            fake_tool.executions == 1
            and calls["count"] == 2
            and response == "Task completed successfully."
        )

        return {
            "task": prompt,
            "expected_tool": name,
            "selected_tool": name if fake_tool.executions else None,
            "tool_execution_count": fake_tool.executions,
            "model_calls": calls["count"],
            "completed": passed,
            "latency_ms": round(elapsed_ms, 2),
            "response": response,
        }
    finally:
        graph.get_tool = original_get_tool
        graph.chat = original_chat

async def main():
    results = []

    # Confirm the expected tools exist in the real registry.
    registry_checks = {
        name: real_get_tool(name) is not None
        for name, _ in TASKS
    }

    for name, prompt in TASKS:
        result = await run_one(name, prompt)
        result["registered_in_real_tool_registry"] = registry_checks[name]
        results.append(result)
        print(
            f"{'PASS' if result['completed'] else 'FAIL'} "
            f"{name}: {result['latency_ms']} ms"
        )

    completed = sum(r["completed"] for r in results)
    registered = sum(registry_checks.values())
    latencies = [r["latency_ms"] for r in results]

    report = {
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "benchmark": "20-task LangGraph orchestration benchmark",
        "task_count": len(TASKS),
        "completed_tasks": completed,
        "completion_rate": round(completed / len(TASKS), 4),
        "registered_tools": registered,
        "tool_registry_coverage": round(registered / len(TASKS), 4),
        "average_latency_ms": round(sum(latencies) / len(latencies), 2),
        "max_latency_ms": round(max(latencies), 2),
        "evaluation_scope": [
            "Actual LangGraph state machine",
            "Tool decision parsing",
            "Argument parsing and validation path",
            "Mocked tool execution",
            "Response formatting path",
        ],
        "limitations": [
            "Model decisions are injected and deterministic.",
            "This does not measure real LLM tool-selection accuracy.",
            "Tools are mocked; no external side effects are performed.",
        ],
        "tasks": results,
    }

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = OUT / f"agent_quality_20_tasks_{stamp}.json"
    path.write_text(json.dumps(report, indent=2), encoding="utf-8")

    print("\n========== AGENT QUALITY RESULTS ==========")
    print(json.dumps({
        "tasks": len(TASKS),
        "completed": completed,
        "completion_rate": report["completion_rate"],
        "registered_tools": registered,
        "tool_registry_coverage": report["tool_registry_coverage"],
        "average_latency_ms": report["average_latency_ms"],
        "report": str(path),
    }, indent=2))

    if completed != len(TASKS) or registered != len(TASKS):
        raise SystemExit(1)

if __name__ == "__main__":
    asyncio.run(main())
