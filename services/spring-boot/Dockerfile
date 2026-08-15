FROM maven:3.9-eclipse-temurin-25 AS build
WORKDIR /src
COPY pom.xml ./
RUN mvn -B -q dependency:go-offline
COPY src ./src
RUN mvn -B -q -DskipTests package

FROM eclipse-temurin:25-jre-alpine
RUN apk add --no-cache wget
COPY --from=build /src/target/app.jar /app.jar
EXPOSE 8000
CMD ["java", "-jar", "/app.jar"]
