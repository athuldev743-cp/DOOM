
import http from "k6/http";
import { check } from "k6";
import { Rate, Trend } from "k6/metrics";

const failures = new Rate("doom_rag_mcp_failures");
const initFailures = new Rate("doom_mcp_init_failures");
const toolLatency = new Trend("doom_rag_tool_latency", true);

const baseUrl = (__ENV.BASE_URL || "https://doom-1a9d9743.fastapicloud.dev").replace(/\/$/, "");
const token = __ENV.DOOM_SESSION || "";

export const options = {
  vus: Math.max(1, Number(__ENV.VUS || 1)),
  iterations: Math.max(1, Number(__ENV.ITERATIONS || 3)),
  thresholds: {
    http_req_failed: ["rate<0.01"],
    doom_rag_mcp_failures: ["rate<0.01"],
    doom_mcp_init_failures: ["rate<0.01"]
  }
};

function headers(version, sessionId) {
  const h = {
    "Content-Type": "application/json",
    "Accept": "application/json, text/event-stream",
    "Authorization": `Bearer ${token}`,
    "Origin": baseUrl,
    "MCP-Protocol-Version": version
  };

  if (sessionId) h["Mcp-Session-Id"] = sessionId;
  return h;
}

function parse(response) {
  try {
    return response.json();
  } catch (_) {
    return null;
  }
}

function diagnose(label, response) {
  console.error(
    `[${label}] status=${response.status}` +
    ` duration_ms=${response.timings.duration}` +
    ` error=${response.error || "none"}` +
    ` error_code=${response.error_code || "none"}` +
    ` body=${String(response.body || "").slice(0, 1000)}`
  );
}

export default function () {
  if (!token) {
    failures.add(true);
    initFailures.add(true);
    console.error("[CONFIG_FAILURE] DOOM_SESSION environment variable is missing.");
    return;
  }

  const init = http.post(`${baseUrl}/mcp`, JSON.stringify({
    jsonrpc: "2.0",
    id: 1,
    method: "initialize",
    params: {
      protocolVersion: "2025-03-26",
      capabilities: {},
      clientInfo: { name: "doom-rag-k6", version: "1.0.0" }
    }
  }), {
    headers: {
      "Content-Type": "application/json",
      "Accept": "application/json, text/event-stream",
      "Authorization": `Bearer ${token}`,
      "Origin": baseUrl
    }
  });

  const initBody = parse(init);
  const version = initBody?.result?.protocolVersion || "2025-03-26";
  const sessionId = init.headers["Mcp-Session-Id"] || init.headers["mcp-session-id"];

  const initOk = check(init, {
    "MCP initialize HTTP 200": r => r.status === 200,
    "MCP protocol negotiated": () => Boolean(initBody?.result?.protocolVersion)
  });

  initFailures.add(!initOk);

  if (!initOk) {
    failures.add(true);
    diagnose("MCP_INIT_FAILURE", init);
    return;
  }

  const h = headers(version, sessionId);

  const notification = http.post(`${baseUrl}/mcp`, JSON.stringify({
    jsonrpc: "2.0",
    method: "notifications/initialized"
  }), { headers: h });

  const notificationOk = check(notification, {
    "MCP initialized notification accepted": r => r.status === 200 || r.status === 202
  });

  if (!notificationOk) {
    diagnose("MCP_NOTIFICATION_FAILURE", notification);
  }

  const started = Date.now();

  const response = http.post(`${baseUrl}/mcp`, JSON.stringify({
    jsonrpc: "2.0",
    id: 3,
    method: "tools/call",
    params: {
      name: "search_docs",
      arguments: {
        query: "What is DOOM's LangGraph workflow and how does it execute tools?"
      }
    }
  }), {
    headers: h,
    tags: { test: "mcp_search_docs" }
  });

  toolLatency.add(Date.now() - started);

  const body = parse(response);
  const result = body?.result;
  const content = result?.content || [];

  const hasContent = content.some(item =>
    item.type === "text" && typeof item.text === "string" && item.text.length > 0
  );

  const callOk = check(response, {
    "search_docs returns HTTP 200": r => r.status === 200,
    "search_docs returns JSON-RPC result": () => Boolean(result),
    "search_docs has no MCP tool error": () => result?.isError !== true,
    "search_docs returns non-empty content": () => hasContent
  });

  if (!callOk) {
    diagnose("MCP_RAG_TOOL_FAILURE", response);
  }

  const ok = notificationOk && callOk;
  failures.add(!ok);
}
