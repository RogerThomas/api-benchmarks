FROM maven:3.9-eclipse-temurin-25 AS build
WORKDIR /src
COPY pom.xml ./
RUN mvn -B -q dependency:go-offline
COPY src ./src
RUN mvn -B -q -DskipTests package

# Distroless java25 is the same Temurin 25 JRE build as eclipse-temurin:25-jre.
# Distroless (pinned by digest): no shell or package manager. A static busybox
# is the only extra binary, for the healthcheck's `wget`.
FROM gcr.io/distroless/java25-debian13@sha256:9edcd1e8d3ee33c296ec4a2318500c5b0824f953e27007c36dfbb50b7205d7da
COPY --from=busybox:1.37-musl@sha256:5cec3fc171c87218698e85a52af7087de727372aae264a787b8112901a5b0092 /bin/busybox /bin/busybox
COPY --from=build /src/target/app.jar /app.jar
EXPOSE 8000
# The image's entrypoint is `java -jar`.
CMD ["/app.jar"]
