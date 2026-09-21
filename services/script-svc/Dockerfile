# 国内网络：基础镜像走加速源，可用 --build-arg BASE_REGISTRY=docker.io 覆盖
ARG BASE_REGISTRY=docker.m.daocloud.io
FROM ${BASE_REGISTRY}/maven:3.9-eclipse-temurin-17 AS build
WORKDIR /build
COPY docker-settings.xml /root/.m2/settings.xml
COPY . .
RUN mvn -q -s /root/.m2/settings.xml -pl script-svc -am package -DskipTests

FROM ${BASE_REGISTRY}/eclipse-temurin:17-jre
WORKDIR /app
COPY --from=build /build/script-svc/target/*.jar app.jar
EXPOSE 8083
ENTRYPOINT ["java", "-jar", "/app/app.jar"]
