FROM golang:1.27-alpine AS build
WORKDIR /src
COPY go.mod go.sum ./
RUN go mod download
COPY main.go ./
RUN CGO_ENABLED=0 go build -o /bin/server .

# Distroless (pinned by digest): no shell or package manager. A static busybox
# is the only extra binary, for the healthcheck's `wget`.
FROM gcr.io/distroless/static-debian13@sha256:034df5c1737e8241f6ed6423a12e720ee0f6d6f088609ee172f98f6f2166ef5d
COPY --from=busybox:1.37-musl@sha256:5cec3fc171c87218698e85a52af7087de727372aae264a787b8112901a5b0092 /bin/busybox /bin/busybox
COPY --from=build /bin/server /bin/server
EXPOSE 8000
CMD ["/bin/server"]
