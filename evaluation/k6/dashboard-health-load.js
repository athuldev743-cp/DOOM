import http from "k6/http";
import { check } from "k6";
import { Rate, Trend } from "k6/metrics";

const failures = new Rate("doom_health_failures");
const healthLatency = new Trend("doom_health_latency", true);
const vus = Math.max(1, Number(__ENV.VUS || 5));
const iterations = Math.max(1, Number(__ENV.ITERATIONS || 100));
const baseUrl = (__ENV.BASE_URL || "https://doom-1a9d9743.fastapicloud.dev").replace(/\/$/, "");

export const options = {
  scenarios: {
    health_load: {
      executor: "shared-iterations",
      vus,
      iterations,
      maxDuration: __ENV.MAX_DURATION || "3m"
    }
  },
  thresholds: {
    http_req_failed: ["rate<0.01"],
    http_req_duration: ["p(95)<1500", "p(99)<3000"],
    doom_health_failures: ["rate<0.01"]
  }
};

export default function () {
  const response = http.get(`${baseUrl}/health`, {
    tags: { endpoint: "health", test: "evaluation_dashboard" }
  });
  const ok = check(response, {
    "health returns HTTP 200": (r) => r.status === 200,
    "health response reports online": (r) => {
      try { return r.json("status") === "online"; } catch (_) { return false; }
    }
  });
  failures.add(!ok);
  healthLatency.add(response.timings.duration);
}
