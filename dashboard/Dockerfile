# Serves the Next.js static export (next.config.ts sets output: "export", so
# `next build` emits plain HTML/CSS/JS into dashboard/out/ — there is no
# .next/standalone and no server.js; the previous image copied both and could
# never start). nginx is the right runtime for a pure static bundle.
#
# Requires a build arg:
#   docker build --build-arg NEXT_PUBLIC_ATLAS_URL=https://api.example.com .
FROM node:22-alpine AS builder

WORKDIR /app

COPY package*.json ./
RUN npm ci

COPY . .

# NEXT_PUBLIC_ATLAS_URL is inlined at build time; fail the build rather than ship
# a bundle pointing at 127.0.0.1.
ARG NEXT_PUBLIC_ATLAS_URL
ENV NEXT_PUBLIC_ATLAS_URL=$NEXT_PUBLIC_ATLAS_URL
RUN test -n "$NEXT_PUBLIC_ATLAS_URL" || (echo "NEXT_PUBLIC_ATLAS_URL build arg is required" && exit 1)

RUN npm run build && test -f out/index.html

# The bundled CSP ships connect-src 'self'; splice in the API origin so the
# containerised build can actually reach the backend. nginx has no envsubst at
# runtime, so it is baked in here alongside NEXT_PUBLIC_ATLAS_URL in the JS.
RUN API_ORIGIN="$(node -e 'console.log(new URL(process.env.NEXT_PUBLIC_ATLAS_URL).origin)')" \
    && sed -i "s#connect-src 'self'#connect-src 'self' ${API_ORIGIN}#" nginx.conf \
    && grep -q "${API_ORIGIN}" nginx.conf


FROM nginxinc/nginx-unprivileged:1.27-alpine AS runner

COPY --from=builder /app/nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=builder /app/out /usr/share/nginx/html

EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=3s --start-period=5s \
  CMD wget -qO- http://127.0.0.1:8080/ >/dev/null || exit 1
