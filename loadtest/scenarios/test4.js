// Test 4: GET /users/me — JWT-authenticated; the id comes from the token, the
// rest (email, address, city, …) is read from a Postgres `users` row.
import http from "k6/http";
import { check } from "k6";
import { options as mkOptions, makeToken, summarize } from "../lib/common.js";

export const options = mkOptions();

const BASE_URL = __ENV.BASE_URL;
const TOKEN = makeToken();
const params = { headers: { Authorization: `Bearer ${TOKEN}` } };

export default function () {
  const res = http.get(`${BASE_URL}/users/me`, params);
  check(res, {
    "status is 200": (r) => r.status === 200,
    "id from token": (r) => r.json("id") === "user-123",
    "has city": (r) => !!r.json("city"),
  });
}

export function handleSummary(data) {
  return summarize(data);
}
