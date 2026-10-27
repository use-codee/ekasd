FROM node:26-bookworm-slim AS builder
WORKDIR /build/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/index.html frontend/tsconfig.json frontend/vite.config.ts ./
COPY frontend/src ./src
RUN npm run build

FROM nginxinc/nginx-unprivileged:1.28-alpine AS runtime
COPY frontend/nginx.conf /etc/nginx/nginx.conf
COPY --from=builder /build/frontend/dist /usr/share/nginx/html
USER 101:101
EXPOSE 8080
HEALTHCHECK --interval=10s --timeout=5s --start-period=5s --retries=5 \
    CMD wget -q -O /dev/null http://127.0.0.1:8080/
# The complete config below needs no template/entrypoint rewrites at startup.
ENTRYPOINT ["nginx"]
CMD ["-g", "daemon off;"]
