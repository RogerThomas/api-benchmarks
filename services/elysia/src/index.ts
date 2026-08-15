// Elysia (Bun) benchmark app — tests 1 (info), 2 (movie), 3 (proxy), 4 (/users/me).
import { Elysia, t } from "elysia";
import { jwt } from "@elysiajs/jwt";
import { SQL } from "bun";

const UPSTREAM_URL = process.env.UPSTREAM_URL!;
const UPSTREAM_API_KEY = process.env.UPSTREAM_API_KEY!;

// DB pool capped at 64 to match the other frameworks (Python db_pool_size=64);
// Bun.sql otherwise defaults to ~10, which would starve/skew test 4.
const sql = new SQL({
  url: `postgres://${process.env.DB_USER}:${process.env.DB_PASSWORD}@${process.env.DB_HOST}:${process.env.DB_PORT}/${process.env.DB_NAME}`,
  max: 64,
});

const app = new Elysia()
  // Test 1: GET /info — medium JSON + custom x-response-id header.
  .get("/info", ({ set }) => {
    set.headers["x-response-id"] = crypto.randomUUID();
    return {
      id: "info-1",
      name: "Benchmark Info",
      count: 42,
      ratio: 3.14159,
      active: true,
      tags: ["alpha", "beta", "gamma"],
      createdAt: "2026-01-01T00:00:00Z",
      nested: { level: 2, label: "nested" },
    };
  })
  // Test 2: POST /movies — JWT-authenticated.
  .use(
    jwt({
      name: "jwt",
      secret: process.env.JWT_SECRET!,
      alg: "HS256",
    }),
  )
  .post(
    "/movies",
    async ({ body, headers, jwt, set }) => {
      const auth = headers.authorization ?? "";
      const token = auth.replace(/^Bearer /, "").trim();
      const payload = await jwt.verify(token);
      if (!payload) {
        set.status = 401;
        return { error: "invalid token" };
      }
      set.status = 201;
      return {
        id: crypto.randomUUID(),
        ...body,
        user: { id: payload.sub, name: payload.name },
      };
    },
    {
      body: t.Object({
        title: t.String(),
        year: t.Number(),
        director: t.String(),
        genre: t.String(),
        rating: t.Number(),
      }),
    },
  )
  // Test 3: GET /catalog — proxy an API-key-protected upstream.
  .get("/catalog", async () => {
    const res = await fetch(`${UPSTREAM_URL}/data`, {
      headers: { Authorization: `Bearer ${UPSTREAM_API_KEY}` },
    });
    return await res.json();
  })
  // Test 4: GET /users/me — id from the JWT, rest from Postgres.
  .get("/users/me", async ({ headers, jwt, set }) => {
    const auth = headers.authorization ?? "";
    const token = auth.replace(/^Bearer /, "").trim();
    const payload = await jwt.verify(token);
    if (!payload) {
      set.status = 401;
      return { error: "invalid token" };
    }
    const rows =
      await sql`SELECT id, name, email, address, city, country FROM users WHERE id = ${payload.sub}`;
    if (rows.length === 0) {
      set.status = 404;
      return { error: "user not found" };
    }
    return rows[0];
  })
  .listen(Number(process.env.PORT ?? 8000));

console.log(`elysia listening on ${app.server?.port}`);
