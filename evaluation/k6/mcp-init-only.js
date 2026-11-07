import http from "k6/http";
import { check } from "k6";
import { Rate, Trend } from "k6/metrics";

const initFailures = new Rate("doom_mcp_init_failures");
const initLatency = new Trend("doom_mcp_init_latency", true);

const baseUrl = (__ENV.BASE_URL || "https://doom-1a9d9743.fastapicloud.dev").replace(/\/$/, "");
const token = __ENV.DOOM_SESSION || "";

export const options = {
  vus: Math.max(1, Number(__ENV.VUS || 1)),
  iterations: Math.max(1, Number(__ENV.ITERATIONS || 3)),
  thresholds: {
    http_req_failed: ["rate<0.01"],
    doom_mcp_init_failures: ["rate<0.01"],
    doom_mcp_init_latency: ["p(95)<5000"]
  }
};

function parse(response) {
  try {
    return response.json();
  } catch (_) {
    return null;
  }
}

export default function () {
  if (!token) {
    initFailures.add(true);
    console.error("[CONFIG_FAILURE] DOOM_SESSION environment variable is missing.");
    return;
  }

  const response = http.post(
    `${baseUrl}/mcp`,
    JSON.stringify({
      jsonrpc: "2.0",
      id: 1,
      method: "initialize",
      params: {
        protocolVersion: "2025-03-26",
        capabilities: {},
        clientInfo: {
          name: "doom-mcp-init-load-test",
          version: "1.0.0"
        }
      }
    }),
    {
      headers: {
        "Content-Type": "application/json",
        "Accept": "application/json, text/event-stream",
        "Authorization": `Bearer ${token}`,
        "Origin": baseUrl
      },
      tags: { test: "mcp_initialize_only" },
      timeout: "65s"
    }
  );

  initLatency.add(response.timings.duration);

  const body = parse(response);

  const ok = check(response, {
    "MCP initialize HTTP 200": r => r.status === 200,
    "MCP protocol negotiated": () => Boolean(body?.result?.protocolVersion)
  });

  initFailures.add(!ok);

  if (!ok) {
    console.error(
      `[MCP_INIT_FAILURE] status=${response.status}` +
      ` duration_ms=${response.timings.duration}` +
      ` error=${response.error || "none"}` +
      ` error_code=${response.error_code || "none"}` +
      ` body=${String(response.body || "").slice(0, 1000)}`
    );
  }
}
