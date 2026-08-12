import http from "k6/http";
import { check, sleep } from "k6";

const BASE = __ENV.TARGET || "http://localhost:8000";

export const options = {
  vus: Number(__ENV.VUS || 10),
  duration: __ENV.DURATION || "30s",
  thresholds: {
    http_req_failed: ["rate<0.05"],
    http_req_duration: ["p(95)<800"],
  },
};

const PATHS = (__ENV.PATHS || "/health").split(",");

export default function () {
  for (const path of PATHS) {
    const res = http.get(`${BASE}${path}`);
    check(res, { "status is 2xx": (r) => r.status >= 200 && r.status < 400 });
  }
  sleep(1);
}
