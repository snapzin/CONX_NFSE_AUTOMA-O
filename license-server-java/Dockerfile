FROM maven:3.9-eclipse-temurin-21-alpine AS build
WORKDIR /app
COPY pom.xml .
RUN mvn dependency:go-offline -q
COPY src ./src
RUN mvn package -DskipTests -q

FROM eclipse-temurin:21-jre-alpine
WORKDIR /app
COPY --from=build /app/target/license-server-1.0.0.jar app.jar
VOLUME /app/data
ENV SPRING_DATASOURCE_URL=jdbc:h2:file:/app/data/licenses;AUTO_SERVER=TRUE
EXPOSE 8080
ENTRYPOINT ["java", "-jar", "app.jar"]
