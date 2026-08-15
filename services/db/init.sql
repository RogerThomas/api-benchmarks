-- Schema + seed for test 4 (GET /users/me). Loaded by Postgres on first start
-- (mounted into /docker-entrypoint-initdb.d/). The seeded id matches the JWT
-- `sub` minted by the k6 load test (loadtest/lib/common.js).
CREATE TABLE IF NOT EXISTS users (
    id      text PRIMARY KEY,
    name    text NOT NULL,
    email   text NOT NULL,
    address text NOT NULL,
    city    text NOT NULL,
    country text NOT NULL
);

INSERT INTO users (id, name, email, address, city, country)
VALUES ('user-123', 'Ada Lovelace', 'ada@example.com', '12 Mayfair Place', 'London', 'United Kingdom')
ON CONFLICT (id) DO NOTHING;
