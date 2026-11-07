import http from "k6/http";
import { check, fail } from "k6";
import { Rate, Trend } from "k6/metrics";

const failures = new Rate("doom_mcp_failures");
const handshakeLatency = new Trend("doom_mcp_handshake_latency", true);
const baseUrl = (__ENV.BASE_URL || "https://doom-1a9d9743.fastapicloud.dev").replace(/\/$/, "");
const token = __ENV.DOOM_SESSION || "";

export const options = {
  vus: Math.max(1, Number(__ENV.VUS || 1)),
  iterations: Math.max(1, Number(__ENV.ITERATIONS || 3)),
  thresholds: {
    http_req_failed: ["rate<0.01"],
    doom_mcp_failures: ["rate<0.01"],
    doom_mcp_handshake_latency: ["p(95)<3000"]
  }
};

function headers(protocolVersion) {
  const value = {
    "Content-Type": "application/json",
    "Accept": "application/json, text/event-stream",
    "Authorization": `Bearer ${token}`,
    "Origin": baseUrl
  };
  if (protocolVersion) value["MCP-Protocol-Version"] = protocolVersion;
  return value;
}

export default function () {
  if (!token) fail("Set DOOM_SESSION to a valid owner session token. Do not commit or share it.");

  const started = Date.now();
  const initialize = http.post(`${baseUrl}/mcp`, JSON.stringify({
    jsonrpc: "2.0",
    id: 1,
    method: "initialize",
    params: {
      protocolVersion: "2025-03-26",
      capabilities: {},
      clientInfo: { name: "doom-evaluation-k6", version: "1.0.0" }
    }
  }), { headers: headers(), tags: { test: "mcp_initialize" } });

  let initialized = false;
  let protocolVersion = "2025-03-26";
  try {
    const body = initialize.json();
    initialized = initialize.status === 200 && body?.jsonrpc === "2.0" && body?.result?.protocolVersion;
    if (initialized) protocolVersion = body.result.protocolVersion;
  } catch (_) {}

  const initOk = check(initialize, {
    "MCP initialize returns HTTP 200": r => r.status === 200,
    "MCP initialize returns negotiated protocol": () => Boolean(initialized)
  });
  if (!initOk) {
    failures.add(true);
    handshakeLatency.add(Date.now() - started);
    return;
  }

  const notification = http.post(`${baseUrl}/mcp`, JSON.stringify({
    jsonrpc: "2.0",
    method: "notifications/initialized"
  }), { headers: headers(protocolVersion), tags: { test: "mcp_initialized" } });
  const notificationOk = check(notification, {
    "MCP initialized notification accepted": r => r.status === 200 || r.status === 202
  });

  const tools = http.post(`${baseUrl}/mcp`, JSON.stringify({
    jsonrpc: "2.0",
    id: 2,
    method: "tools/list",
    params: {}
  }), { headers: headers(protocolVersion), tags: { test: "mcp_tools_list" } });

  let toolNames = [];
  try {
    const body = tools.json();
    toolNames = (body?.result?.tools || []).map(tool => tool.name);
  } catch (_) {}

  const toolsOk = check(tools, {
    "MCP tools/list returns HTTP 200": r => r.status === 200,
    "MCP tools/list includes RAG tools": () => ["search_docs", "list_docs", "ingest_docs"].every(name => toolNames.includes(name))
  });
  const ok = initOk && notificationOk && toolsOk;
  failures.add(!ok);
  handshakeLatency.add(Date.now() - started);
}
