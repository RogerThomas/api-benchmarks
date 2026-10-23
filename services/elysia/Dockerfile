FROM oven/bun:1.4.4 AS build
WORKDIR /app
COPY package.json bun.lock ./
RUN bun install --frozen-lockfile --production

# Distroless: the same Bun build and glibc runtime, minus the OS packages.
FROM oven/bun:1.4.4-distroless
WORKDIR /app
COPY --from=build /app/node_modules ./node_modules
COPY package.json ./
COPY src ./src
EXPOSE 8000
# The image's entrypoint is `bun` itself.
CMD ["run", "src/index.ts"]
