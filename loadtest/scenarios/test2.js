// Test 2: JWT-authenticated POST creating a movie, returns it with a uuid `id`
// and the authenticated user object.
import http from "k6/http";
import { check } from "k6";
import { options as mkOptions, makeToken, summarize } from "../lib/common.js";

export const options = mkOptions();

const BASE_URL = __ENV.BASE_URL;
const TOKEN = makeToken();

const body = JSON.stringify({
  title: "Blade Runner 2049",
  year: 2017,
  director: "Denis Villeneuve",
  genre: "Sci-Fi",
  rating: 8.0,
});

const params = {
  headers: {
    "Content-Type": "application/json",
    Authorization: `Bearer ${TOKEN}`,
  },
};

export default function () {
  const res = http.post(`${BASE_URL}/movies`, body, params);
  check(res, {
    "status is 201": (r) => r.status === 201,
    "has id": (r) => !!r.json("id"),
    "has user id": (r) => !!r.json("user.id"),
  });
}

export function handleSummary(data) {
  return summarize(data);
}
