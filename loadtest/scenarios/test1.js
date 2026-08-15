// Test 1: simple GET returning a medium JSON + a custom x-response-id header.
import http from "k6/http";
import { check } from "k6";
import { options as mkOptions, summarize } from "../lib/common.js";

export const options = mkOptions();

const BASE_URL = __ENV.BASE_URL;

export default function () {
  const res = http.get(`${BASE_URL}/info`);
  check(res, {
    "status is 200": (r) => r.status === 200,
    "has x-response-id": (r) => !!r.headers["X-Response-Id"],
  });
}

export function handleSummary(data) {
  return summarize(data);
}
