const grid = document.getElementById("test-grid");
const notice = document.getElementById("notice");
const runAllButton = document.getElementById("run-all");
const results = new Map();
let catalog = [];

const icons = { rag: "⌕", mcp: "⌘", langgraph: "◇", latency: "◷", database: "▤", security: "⬡" };
const escapeHtml = (value) => String(value ?? "").replace(/[&<>"']/g, ch => ({ "&":"&amp;", "<":"&lt;", ">":"&gt;", '"':"&quot;", "'":"&#39;" }[ch]));
const fmt = (value) => typeof value === "number" ? (Number.isInteger(value) ? value.toLocaleString() : value.toLocaleString(undefined, { maximumFractionDigits: 2 })) : escapeHtml(value);
const metricLabel = (key) => key.replaceAll("_", " ").replace(/\b\w/g, c => c.toUpperCase());

function metricMarkup(metrics = {}) {
  const entries = Object.entries(metrics).filter(([key, value]) => !["response_previews", "scope", "quality_note", "retrieval_mode"].includes(key) && (typeof value === "number" || typeof value === "boolean" || typeof value === "string"));
  return entries.map(([key, value]) => `<div class="metric"><span>${escapeHtml(metricLabel(key))}</span><strong>${typeof value === "boolean" ? (value ? "Yes" : "No") : fmt(value)}</strong></div>`).join("");
}
function checkMarkup(checks = []) {
  if (!checks.length) return "";
  return `<div class="checks">${checks.map(item => `<div class="check"><span class="check-icon ${item.status === "passed" ? "ok" : "bad"}">${item.status === "passed" ? "✓" : "!"}</span><div><b>${escapeHtml(item.name)}</b><small>${escapeHtml(item.detail || "")}</small></div></div>`).join("")}</div>`;
}
function renderCard(item) {
  const result = results.get(item.id);
  const state = result?.status || "idle";
  const running = state === "running";
  const statusText = state === "idle" ? "NOT RUN" : state.toUpperCase();
  return `<article class="test-card" id="card-${item.id}">
    <div class="card-head"><div class="test-icon">${icons[item.id] || "•"}</div><div class="card-title"><h3>${escapeHtml(item.title)}</h3><span>${escapeHtml(item.id.toUpperCase())}</span></div><span class="status-pill ${state}">${statusText}</span></div>
    <p class="description">${escapeHtml(item.description)}</p>
    <div class="config"><label for="count-${item.id}">Request count <small>${escapeHtml(item.unit)}</small></label><input id="count-${item.id}" type="number" min="1" max="${item.max_count}" value="${item.default_count}" ${running ? "disabled" : ""}></div>
    <button class="run-one ${running ? "busy" : ""}" data-run="${item.id}" ${running ? "disabled" : ""}>${running ? '<span class="spinner"></span> Running…' : "Run test →"}</button>
    ${result && !running ? `<div class="result-block"><div class="result-summary"><b>${result.checks_passed ?? 0} passed</b><span>${result.checks_failed ?? 0} failed</span><small>${fmt(result.duration_ms)} ms</small></div>${result.error ? `<div class="error">${escapeHtml(result.error)}</div>` : ""}<div class="metrics">${metricMarkup(result.metrics)}</div>${checkMarkup(result.checks)}${result.metrics?.response_previews ? `<details><summary>LangGraph responses</summary><pre>${escapeHtml(result.metrics.response_previews.join("\n\n"))}</pre></details>` : ""}${result.report_file ? `<small class="report-path">Saved: ${escapeHtml(result.report_file)}</small>` : ""}</div>` : ""}
  </article>`;
}
function render() {
  grid.innerHTML = catalog.map(renderCard).join("");
  grid.querySelectorAll("[data-run]").forEach(button => button.addEventListener("click", () => runOne(button.dataset.run)));
  updateSummary();
}
function updateSummary() {
  const values = [...results.values()].filter(x => x.status !== "running");
  document.getElementById("total-tests").textContent = catalog.length;
  document.getElementById("passed-tests").textContent = values.filter(x => x.status === "passed").length;
  document.getElementById("failed-tests").textContent = values.filter(x => ["failed", "error"].includes(x.status)).length;
  const latest = values.length ? Math.max(...values.map(x => x.duration_ms || 0)) : 0;
  document.getElementById("last-duration").textContent = latest ? `${fmt(latest)} ms` : "—";
}
async function runOne(id) {
  const item = catalog.find(x => x.id === id);
  if (!item || results.get(id)?.status === "running") return;
  const input = document.getElementById(`count-${id}`);
  const request_count = Math.max(1, Math.min(item.max_count, Number(input?.value || item.default_count)));
  results.set(id, { status: "running", checks_passed: 0, checks_failed: 0 });
  notice.textContent = `${item.title}: running ${request_count} ${item.unit}…`;
  notice.className = "notice active";
  render();
  try {
    const response = await fetch(`/evaluation/api/run/${encodeURIComponent(id)}`, {
      method: "POST", credentials: "same-origin", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ request_count })
    });
    const data = await response.json();
    if (!response.ok) throw new Error(data.detail || `HTTP ${response.status}`);
    results.set(id, data);
    notice.textContent = `${item.title}: ${data.status.toUpperCase()} · ${data.checks_passed} passed · ${data.checks_failed} failed`;
    notice.className = `notice ${data.status === "passed" ? "success" : "warning"}`;
  } catch (error) {
    results.set(id, { status: "error", error: error.message, checks_passed: 0, checks_failed: 1, metrics: {} });
    notice.textContent = `${item.title}: ${error.message}`;
    notice.className = "notice warning";
  }
  render();
}
runAllButton.addEventListener("click", async () => {
  runAllButton.disabled = true;
  runAllButton.textContent = "Running suite…";
  for (const item of catalog) await runOne(item.id);
  runAllButton.disabled = false;
  runAllButton.textContent = "↻ Run all tests";
  const failed = [...results.values()].filter(x => ["failed", "error"].includes(x.status)).length;
  notice.textContent = failed ? `Evaluation complete · ${failed} module(s) need attention.` : "Evaluation complete · all modules passed.";
  notice.className = `notice ${failed ? "warning" : "success"}`;
});
async function init() {
  try {
    const response = await fetch("/evaluation/api/catalog", { credentials: "same-origin", cache: "no-store" });
    if (response.status === 403 || response.status === 401) { location.href = "/"; return; }
    if (!response.ok) throw new Error(`Catalog request failed: HTTP ${response.status}`);
    const data = await response.json();
    catalog = data.tests || [];
    render();
    notice.textContent = "Ready. Choose a module or run the full evaluation suite.";
    notice.className = "notice";
  } catch (error) {
    notice.textContent = error.message;
    notice.className = "notice warning";
  }
}
init();
