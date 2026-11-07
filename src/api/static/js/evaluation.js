const grid = document.getElementById("test-grid");
const notice = document.getElementById("notice");
const runAllButton = document.getElementById("run-all");
const terminal = document.getElementById("terminal-output");
const terminalMeta = document.getElementById("terminal-meta");
const results = new Map();
let catalog = [];
let suiteRunning = false;

const icons = { rag: "⌕", mcp: "⌘", langgraph: "◇", latency: "◷", database: "▤", security: "⬡" };
const escapeHtml = (value) => String(value ?? "").replace(/[&<>"']/g, ch => ({ "&":"&amp;", "<":"&lt;", ">":"&gt;", '"':"&quot;", "'":"&#39;" }[ch]));
const fmt = (value) => typeof value === "number" ? (Number.isInteger(value) ? value.toLocaleString() : value.toLocaleString(undefined, { maximumFractionDigits: 2 })) : escapeHtml(value);
const metricLabel = (key) => key.replaceAll("_", " ").replace(/\b\w/g, c => c.toUpperCase());
const clock = () => new Date().toLocaleTimeString();
let logLines = [];

function log(message, type = "info") {
  const line = `[${clock()}] ${message}`;
  logLines.push({ line, type });
  if (logLines.length > 350) logLines = logLines.slice(-350);
  terminal.textContent = logLines.map(item => item.line).join("\n");
  terminal.scrollTop = terminal.scrollHeight;
}
function setProgress(done, total, label = "RUNNING") {
  terminalMeta.textContent = `${label} · ${done}/${total} MODULES COMPLETE`;
}
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
    <div class="config"><label for="count-${item.id}">Request count <small>${escapeHtml(item.unit)}</small></label><input id="count-${item.id}" type="number" min="1" max="${item.max_count}" value="${item.default_count}" ${running || suiteRunning ? "disabled" : ""}></div>
    <button class="run-one ${running ? "busy" : ""}" data-run="${item.id}" ${running || suiteRunning ? "disabled" : ""}>${running ? '<span class="spinner"></span> Running…' : "Run test →"}</button>
    ${result && !running ? `<div class="result-block"><div class="result-summary"><b>${result.checks_passed ?? 0} passed</b><span>${result.checks_failed ?? 0} failed</span><small>${fmt(result.duration_ms)} ms</small></div>${result.error ? `<div class="error">${escapeHtml(result.error)}</div>` : ""}<div class="metrics">${metricMarkup(result.metrics)}</div>${checkMarkup(result.checks)}${result.metrics?.response_previews ? `<details><summary>LangGraph responses</summary><pre>${escapeHtml(result.metrics.response_previews.join("\n\n"))}</pre></details>` : ""}${result.report_file ? `<small class="report-path">Saved: ${escapeHtml(result.report_file)}</small>` : ""}</div>` : ""}
  </article>`;
}
function render() {
  grid.innerHTML = catalog.map(renderCard).join("");
  grid.querySelectorAll("[data-run]").forEach(button => button.addEventListener("click", () => runOne(button.dataset.run)));
  updateSummary();
}
function updateSummary() {
  const values = [...results.values()];
  document.getElementById("total-tests").textContent = catalog.length;
  document.getElementById("passed-tests").textContent = values.filter(x => x.status === "passed").length;
  document.getElementById("failed-tests").textContent = values.filter(x => ["failed", "error"].includes(x.status)).length;
  const durations = values.filter(x => x.status !== "running").map(x => x.duration_ms || 0);
  const latest = durations.reduce((sum, value) => sum + value, 0);
  document.getElementById("last-duration").textContent = latest ? `${fmt(latest)} ms` : "—";
}
async function executeModule(id, requestCount) {
  const item = catalog.find(x => x.id === id);
  const started = performance.now();
  results.set(id, { status: "running", checks_passed: 0, checks_failed: 0 });
  render();
  log(`▶ ${item.title.toUpperCase()} — STARTED (count: ${requestCount})`, "start");
  try {
    const response = await fetch(`/evaluation/api/run/${encodeURIComponent(id)}`, {
      method: "POST", credentials: "same-origin", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ request_count: requestCount })
    });
    const data = await response.json();
    if (!response.ok) throw new Error(data.detail || `HTTP ${response.status}`);
    results.set(id, data);
    const mark = data.status === "passed" ? "PASS" : "FAIL";
    log(`${data.status === "passed" ? "✓" : "✗"} ${item.title.toUpperCase()} — ${mark} · ${data.checks_passed} passed · ${data.checks_failed} failed · ${fmt(data.duration_ms)} ms`, data.status);
    (data.checks || []).forEach(check => log(`   ${check.status === "passed" ? "✓" : "✗"} ${check.name}${check.detail ? " — " + check.detail : ""}`, check.status));
    if (data.error) log(`   ERROR: ${data.error}`, "error");
    if (data.report_file) log(`   REPORT: ${data.report_file}`);
    return data;
  } catch (error) {
    const data = { test_id: id, title: item.title, status: "error", duration_ms: Math.round(performance.now() - started), error: error.message, checks_passed: 0, checks_failed: 1, metrics: {} };
    results.set(id, data);
    log(`✗ ${item.title.toUpperCase()} — ERROR · ${error.message}`, "error");
    return data;
  } finally {
    render();
  }
}
async function runOne(id) {
  if (suiteRunning || productionRunning || results.get(id)?.status === "running") return;
  const item = catalog.find(x => x.id === id);
  if (!item) return;
  const input = document.getElementById(`count-${id}`);
  const count = Math.max(1, Math.min(item.max_count, Number(input?.value || item.default_count)));
  notice.textContent = `${item.title}: running…`;
  notice.className = "notice active";
  const data = await executeModule(id, count);
  notice.textContent = `${item.title}: ${data.status.toUpperCase()} · ${data.checks_passed} passed · ${data.checks_failed} failed`;
  notice.className = `notice ${data.status === "passed" ? "success" : "warning"}`;
}
runAllButton.addEventListener("click", async () => {
  if (suiteRunning || productionRunning || !catalog.length) return;
  suiteRunning = true;
  results.clear();
  logLines = [];
  terminal.textContent = "";
  runAllButton.disabled = true;
  runAllButton.textContent = "Running suite…";
  const counts = Object.fromEntries(catalog.map(item => {
    const input = document.getElementById(`count-${item.id}`);
    return [item.id, Math.max(1, Math.min(item.max_count, Number(input?.value || item.default_count)))];
  }));
  const concurrency = Math.min(3, catalog.length);
  let next = 0, completed = 0;
  setProgress(0, catalog.length);
  log("DOOM ENGINEERING EVALUATION", "heading");
  log(`Target: LIVE DEPLOYED BACKEND · Parallel workers: ${concurrency}`);
  log("------------------------------------------------------------");
  catalog.forEach(item => log(`QUEUED  ${item.title}`));
  render();
  const worker = async () => {
    while (true) {
      const index = next++;
      if (index >= catalog.length) return;
      const item = catalog[index];
      await executeModule(item.id, counts[item.id]);
      completed++;
      setProgress(completed, catalog.length);
    }
  };
  await Promise.all(Array.from({ length: concurrency }, worker));
  if (productionCatalog.length) {
    productionRunning = true;
    const totalModules = catalog.length + productionCatalog.length;
    let productionNext = 0, productionCompleted = 0;
    log("------------------------------------------------------------");
    log("PRODUCTION PERFORMANCE & RELIABILITY", "heading");
    productionCatalog.forEach(item => log(`QUEUED  ${item.title}`));
    const productionWorker = async () => {
      while (true) {
        const index = productionNext++;
        if (index >= productionCatalog.length) return;
        await executeProductionModule(productionCatalog[index].id);
        productionCompleted++;
        setProgress(catalog.length + productionCompleted, totalModules, "ALL TESTS");
      }
    };
    await Promise.all(Array.from({ length: Math.min(2, productionCatalog.length) }, productionWorker));
    productionRunning = false;
  }
  const values = [
    ...catalog.map(item => results.get(item.id)),
    ...productionCatalog.map(item => results.get("production:" + item.id))
  ].filter(Boolean);
  const passed = values.filter(x => x.status === "passed").length;
  const failed = values.filter(x => ["failed", "error"].includes(x.status)).length;
  const checksPassed = values.reduce((sum, x) => sum + (x.checks_passed || 0), 0);
  const checksFailed = values.reduce((sum, x) => sum + (x.checks_failed || 0), 0);
  const elapsed = values.reduce((sum, x) => sum + (x.duration_ms || 0), 0);
  log("------------------------------------------------------------");
  log("FINAL SUMMARY", "heading");
  catalog.forEach(item => {
    const value = results.get(item.id);
    log(`${value?.status === "passed" ? "PASS" : "FAIL "}  ${item.title} · ${value?.checks_passed || 0}/${(value?.checks_passed || 0) + (value?.checks_failed || 0)} checks · ${fmt(value?.duration_ms || 0)} ms`);
  });
  productionCatalog.forEach(item => {
    const value = results.get("production:" + item.id);
    log(`${value?.status === "passed" ? "PASS" : "FAIL "}  ${item.title} · ${value?.checks_passed || 0}/${(value?.checks_passed || 0) + (value?.checks_failed || 0)} checks · ${fmt(value?.duration_ms || 0)} ms`);
  });
  log(`TOTAL: ${passed}/${values.length} modules passed · ${failed} failed · ${checksPassed} checks passed · ${checksFailed} checks failed`);
  log(`SUM OF MODULE TIMES: ${fmt(elapsed)} ms (modules ran concurrently)`);
  setProgress(catalog.length + productionCatalog.length, catalog.length + productionCatalog.length, failed ? "COMPLETED WITH FAILURES" : "ALL PASSED");
  notice.textContent = failed ? `Evaluation complete · ${failed} module(s) need attention.` : "Evaluation complete · all modules passed.";
  notice.className = `notice ${failed ? "warning" : "success"}`;
  suiteRunning = false;
  runAllButton.disabled = false;
  runAllButton.textContent = "↻ Run all tests";
  render();
});
async function init() {
  try {
    const response = await fetch("/evaluation/api/catalog", { credentials: "same-origin", cache: "no-store" });
    if (response.status === 403 || response.status === 401) { location.href = "/"; return; }
    if (!response.ok) throw new Error(`Catalog request failed: HTTP ${response.status}`);
    const data = await response.json();
    catalog = data.tests || [];
    render();
    log("DOOM evaluation console ready.");
    log(`${catalog.length} modules loaded. Select a module or run all tests.`);
    notice.textContent = "Ready. Run one module or start the full suite.";
    notice.className = "notice";
  } catch (error) {
    notice.textContent = error.message;
    notice.className = "notice warning";
    log(`ERROR: ${error.message}`, "error");
  }
}
init();


// Production evaluation suite: separate from the six fast baseline modules.
let productionCatalog = [];
let productionRunning = false;
const productionGrid = document.getElementById("production-grid");
const productionRunAll = document.getElementById("run-production-all");
const safeNumber = (id, fallback, min, max) => Math.max(min, Math.min(max, Number(document.getElementById(id)?.value || fallback)));
function productionConfig() {
  return {
    concurrency: safeNumber("production-concurrency", 3, 1, 10),
    requests: safeNumber("production-requests", 12, 1, 40),
    runs: safeNumber("production-runs", 1, 1, 2)
  };
}
function renderProductionCards() {
  if (!productionGrid) return;
  productionGrid.innerHTML = productionCatalog.map(item => {
    const result = results.get("production:" + item.id);
    const state = result?.status || "idle";
    const details = result ? `<div class="result-block"><div class="result-summary"><b>${result.checks_passed || 0} passed</b><span>${result.checks_failed || 0} failed</span><small>${fmt(result.duration_ms)} ms</small></div>${result.error ? `<div class="error">${escapeHtml(result.error)}</div>` : ""}<div class="metrics">${metricMarkup(result.metrics)}</div>${checkMarkup(result.checks)}</div>` : "";
    return `<article class="test-card"><div class="card-head"><div class="test-icon">⌁</div><div class="card-title"><h3>${escapeHtml(item.title)}</h3><span>PRODUCTION TEST</span></div><span class="status-pill ${state}">${state.toUpperCase()}</span></div><p class="description">${escapeHtml(item.description)}</p><button class="run-one" data-production-run="${escapeHtml(item.id)}" ${productionRunning ? "disabled" : ""}>Run test →</button>${details}</article>`;
  }).join("");
  productionGrid.querySelectorAll("[data-production-run]").forEach(button => button.addEventListener("click", () => runProductionOne(button.dataset.productionRun)));
}
async function executeProductionModule(id) {
  const item = productionCatalog.find(entry => entry.id === id);
  if (!item) return null;
  const started = performance.now();
  const config = productionConfig();
  log(`▶ PRODUCTION / ${item.title.toUpperCase()} — STARTED`);
  try {
    const response = await fetch(`/evaluation/production/run/${encodeURIComponent(id)}`, {
      method: "POST", credentials: "same-origin",
      headers: { "Content-Type": "application/json" }, body: JSON.stringify(config)
    });
    const data = await response.json();
    if (!response.ok) throw new Error(data.detail || `HTTP ${response.status}`);
    results.set("production:" + id, data);
    log(`${data.status === "passed" ? "✓" : "✗"} ${item.title.toUpperCase()} — ${data.status.toUpperCase()} · ${data.checks_passed} passed · ${data.checks_failed} failed · ${fmt(data.duration_ms)} ms`, data.status);
    (data.checks || []).forEach(check => log(`   ${check.status === "passed" ? "✓" : "✗"} ${check.name}${check.detail ? " — " + check.detail : ""}`, check.status));
    Object.entries(data.metrics || {}).forEach(([key, value]) => {
      if (key === "node_timings") value.forEach(node => log(`   NODE ${node.node}: ${node.calls} calls · avg ${node.avg_ms} ms · p95 ${node.p95_ms} ms`));
      else if (typeof value !== "object") log(`   ${metricLabel(key)}: ${fmt(value)}`);
    });
    if (data.error) log(`   ERROR: ${data.error}`, "error");
    return data;
  } catch (error) {
    const data = { test_id: id, status: "error", duration_ms: Math.round(performance.now() - started), checks_passed: 0, checks_failed: 1, error: error.message, checks: [], metrics: {} };
    results.set("production:" + id, data);
    log(`✗ ${item.title.toUpperCase()} — ERROR · ${error.message}`, "error");
    return data;
  } finally {
    renderProductionCards();
  }
}
async function runProductionOne(id) {
  if (productionRunning || suiteRunning) return;
  productionRunning = true;
  productionRunAll.disabled = true;
  renderProductionCards();
  await executeProductionModule(id);
  productionRunning = false;
  productionRunAll.disabled = false;
  renderProductionCards();
}
if (productionRunAll) productionRunAll.addEventListener("click", async () => {
  if (productionRunning || suiteRunning || !productionCatalog.length) return;
  productionRunning = true;
  suiteRunning = true;
  runAllButton.disabled = true;
  productionRunAll.disabled = true;
  logLines = [];
  terminal.textContent = "";
  log("DOOM PRODUCTION PERFORMANCE & RELIABILITY", "heading");
  const concurrency = Math.min(2, productionCatalog.length);
  log(`Target: LIVE DEPLOYED BACKEND · Parallel workers: ${concurrency}`);
  productionCatalog.forEach(item => log(`QUEUED  ${item.title}`));
  let next = 0, completed = 0;
  const worker = async () => {
    while (true) {
      const index = next++;
      if (index >= productionCatalog.length) return;
      await executeProductionModule(productionCatalog[index].id);
      completed++;
      setProgress(completed, productionCatalog.length, "PRODUCTION");
    }
  };
  await Promise.all(Array.from({ length: concurrency }, worker));
  const values = productionCatalog.map(item => results.get("production:" + item.id)).filter(Boolean);
  const passed = values.filter(value => value.status === "passed").length;
  log("------------------------------------------------------------");
  log(`PRODUCTION SUMMARY: ${passed}/${productionCatalog.length} passed · ${productionCatalog.length - passed} failed`, "heading");
  setProgress(productionCatalog.length, productionCatalog.length, passed === productionCatalog.length ? "ALL PASSED" : "COMPLETED WITH FAILURES");
  productionRunning = false;
  suiteRunning = false;
  runAllButton.disabled = false;
  productionRunAll.disabled = false;
  renderProductionCards();
});
async function initProduction() {
  if (!productionGrid) return;
  try {
    const response = await fetch("/evaluation/production/catalog", { credentials: "same-origin", cache: "no-store" });
    if (!response.ok) throw new Error(`Production catalog HTTP ${response.status}`);
    const data = await response.json();
    productionCatalog = data.tests || [];
    renderProductionCards();
    log(`${productionCatalog.length} production modules loaded. External k6 tests are configured below.`);
  } catch (error) {
    productionGrid.innerHTML = `<div class="notice warning">${escapeHtml(error.message)}</div>`;
  }
}
function updateK6Commands() {
  const vus = safeNumber("k6-vus", 5, 1, 50);
  const duration = document.getElementById("k6-duration")?.value || "1m";
  const token = document.getElementById("k6-token")?.value || "";
  document.getElementById("k6-load-command").textContent = `k6 run -e BASE_URL=https://doom-1a9d9743.fastapicloud.dev -e VUS=${vus} -e DURATION=${duration} evaluation/k6/production-load.js`;
  document.getElementById("k6-mcp-command").textContent = token
    ? `$env:DOOM_SESSION = "${token}"; k6 run -e BASE_URL=https://doom-1a9d9743.fastapicloud.dev -e DOOM_SESSION="$env:DOOM_SESSION" -e VUS=1 -e ITERATIONS=3 evaluation/k6/mcp-streamable-http.js`
    : "Set your owner session token in the field above to generate this command.";
}
["k6-vus", "k6-duration", "k6-token"].forEach(id => document.getElementById(id)?.addEventListener("input", updateK6Commands));
document.getElementById("copy-k6-load")?.addEventListener("click", async () => {
  updateK6Commands();
  await navigator.clipboard.writeText(document.getElementById("k6-load-command").textContent);
  log("Copied public k6 command. Run it in PowerShell on your PC.");
});
document.getElementById("copy-k6-mcp")?.addEventListener("click", async () => {
  updateK6Commands();
  const command = document.getElementById("k6-mcp-command").textContent;
  if (command.startsWith("Set your")) { log("Enter the owner session token locally before copying the MCP command.", "warning"); return; }
  await navigator.clipboard.writeText(command);
  log("Copied MCP command. The token is only copied to your local clipboard; never share it.");
});
updateK6Commands();
initProduction();
