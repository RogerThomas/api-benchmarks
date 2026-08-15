FROM golang:1.26-alpine AS build
WORKDIR /src
COPY go.mod main.go ./
# Resolve deps and generate go.sum at build time (no committed sum needed).
RUN go mod tidy
RUN CGO_ENABLED=0 go build -o /bin/server .

FROM alpine:3.20
RUN apk add --no-cache wget
COPY --from=build /bin/server /bin/server
EXPOSE 8000
CMD ["/bin/server"]
