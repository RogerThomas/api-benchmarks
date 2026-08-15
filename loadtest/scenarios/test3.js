// Test 3: GET /catalog — the framework fetches from an authenticated upstream,
// parses the JSON, and returns it. (Public endpoint is unauthenticated; the
// service-to-service call to the upstream carries the API key.)
import http from "k6/http";
import { check } from "k6";
import { options as mkOptions, summarize } from "../lib/common.js";

export const options = mkOptions();

const BASE_URL = __ENV.BASE_URL;

export default function () {
  const res = http.get(`${BASE_URL}/catalog`);
  check(res, {
    "status is 200": (r) => r.status === 200,
    "has product id": (r) => r.json("id") === "prod-1",
    "has vendor": (r) => !!r.json("vendor.name"),
  });
}

export function handleSummary(data) {
  return summarize(data);
}
