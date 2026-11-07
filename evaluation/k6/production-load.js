import http from "k6/http";
import { check } from "k6";
import { Rate, Trend } from "k6/metrics";

const failures = new Rate("doom_public_failures");
const publicLatency = new Trend("doom_public_latency", true);
const baseUrl = (__ENV.BASE_URL || "https://doom-1a9d9743.fastapicloud.dev").replace(/\/$/, "");
const vus = Math.max(1, Math.min(50, Number(__ENV.VUS || 5)));
const duration = __ENV.DURATION || "1m";

export const options = {
  scenarios: {
    public_health: { executor: "constant-vus", vus, duration, gracefulStop: "10s" }
  },
  thresholds: {
    http_req_failed: ["rate<0.01"],
    http_req_duration: ["p(95)<1500", "p(99)<3000"],
    doom_public_failures: ["rate<0.01"]
  }
};

export default function () {
  const response = http.get(`${baseUrl}/health`, {
    tags: { endpoint: "health", test: "public_network_load" },
    timeout: "15s"
  });
  const ok = check(response, {
    "public /health returns HTTP 200": r => r.status === 200,
    "service reports online": r => {
      try { return r.json("status") === "online"; } catch (_) { return false; }
    }
  });
  failures.add(!ok);
  publicLatency.add(response.timings.duration);
}
