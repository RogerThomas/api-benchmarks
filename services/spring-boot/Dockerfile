FROM maven:3.9-eclipse-temurin-25 AS build
WORKDIR /src
COPY pom.xml ./
RUN mvn -B -q dependency:go-offline
COPY src ./src
RUN mvn -B -q -DskipTests package

# Distroless java25 is the same Temurin 25 JRE build as eclipse-temurin:25-jre.
# Distroless (pinned by digest): no shell or package manager. A static busybox
# is the only extra binary, for the healthcheck's `wget`.
FROM gcr.io/distroless/java25-debian13@sha256:227c14f972231e8db2ff9bfe0fe5c91fc80b689b35bafdce3f8d6b1204087a30
COPY --from=busybox:1.37-musl@sha256:5cec3fc171c87218698e85a52af7087de727372aae264a787b8112901a5b0092 /bin/busybox /bin/busybox
COPY --from=build /src/target/app.jar /app.jar
EXPOSE 8000
# The image's entrypoint is `java -jar`.
CMD ["/app.jar"]
