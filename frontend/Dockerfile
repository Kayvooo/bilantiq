# Zwei-Stufen-Image: Vite-Build im Node-Container, Auslieferung durch Caddy.
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

# Laufzeit-Stufe: Caddy dient das SPA statisch aus, terminiert TLS (automatisches
# Let's Encrypt) und proxyt die API auf den backend-Container.
FROM caddy:2-alpine
COPY --from=build /app/dist /srv
# Standard ist die Caddyfile fuer das oeffentliche Internet; docker-compose.home.yml waehlt Caddyfile.home.
ARG CADDYFILE=Caddyfile
COPY ${CADDYFILE} /etc/caddy/Caddyfile
