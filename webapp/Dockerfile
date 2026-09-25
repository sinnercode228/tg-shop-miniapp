# Build context: repository root (the web app bundles /shared/*.json).
FROM node:22-alpine AS build
WORKDIR /app/webapp
COPY webapp/package.json webapp/package-lock.json ./
RUN npm ci
COPY shared /app/shared
COPY webapp ./
ARG VITE_API_MODE=http
ARG VITE_API_URL=
ENV VITE_API_MODE=$VITE_API_MODE VITE_API_URL=$VITE_API_URL VITE_BASE=/
RUN npm run build

FROM nginx:1.27-alpine
COPY webapp/nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/webapp/dist /usr/share/nginx/html
EXPOSE 80
