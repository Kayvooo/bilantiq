# Getrennte Builds fuer Frontend und Caddy, danach ein kleines Laufzeitimage.
# Build-Kontext ist das Repo-Wurzelverzeichnis (siehe docker-compose.prod.yml), damit
# neben frontend/ auch die Caddyfile erreichbar ist.

FROM node:22-alpine AS build
WORKDIR /app
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
# VITE_API_BASE_URL wird zur Build-Zeit in das Bundle eingebacken (Vite ersetzt
# import.meta.env.* statisch). Muss auf die oeffentliche API-Domain zeigen.
ARG VITE_API_BASE_URL
ENV VITE_API_BASE_URL=$VITE_API_BASE_URL
RUN npm run build

# Upstream-Caddy 2.11.7 mit den reparierten Go-/x/net-Versionen bauen.
# Der Einstiegspunkt entspricht dem von Caddy dokumentierten Standard-Build ohne Zusatzplugins.
FROM golang:1.27.3-alpine3.23 AS caddy-build
ENV CGO_ENABLED=0 GOTOOLCHAIN=local
WORKDIR /src
COPY frontend/caddy/main.go ./
RUN go mod init bilantiq.local/caddy \
    && go get github.com/caddyserver/caddy/v2@v2.11.7 golang.org/x/net@v0.60.0 \
    && go mod tidy \
    && go build -trimpath -o /out/caddy .

# Laufzeit-Stufe: Caddy dient das SPA statisch aus, terminiert TLS (automatisches
# Let's Encrypt) und proxyt die API auf den backend-Container.
FROM caddy:2.11.7-alpine
COPY --from=caddy-build /out/caddy /usr/bin/caddy
RUN setcap cap_net_bind_service=+ep /usr/bin/caddy
COPY --from=build /app/dist /srv
# Standard ist die Caddyfile fuer das oeffentliche Internet; docker-compose.home.yml waehlt Caddyfile.home.
ARG CADDYFILE=Caddyfile
COPY ${CADDYFILE} /etc/caddy/Caddyfile
