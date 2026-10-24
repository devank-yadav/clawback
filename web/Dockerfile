# Clawback web (Next.js). Deployment file only, added for the Vultr deploy; the app source stays Rishi's.
FROM node:22-slim AS build
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci
COPY . .
# Browser calls to the API go through Caddy at /api on the same domain.
ARG NEXT_PUBLIC_API_BASE=/api
# live follows the API's event stream; build with --build-arg NEXT_PUBLIC_DATA_SOURCE=fixture to replay web/fixtures.
ARG NEXT_PUBLIC_DATA_SOURCE=live
ENV NEXT_PUBLIC_API_BASE=$NEXT_PUBLIC_API_BASE NEXT_PUBLIC_DATA_SOURCE=$NEXT_PUBLIC_DATA_SOURCE NEXT_TELEMETRY_DISABLED=1
RUN npm run build

FROM node:22-slim
WORKDIR /app
ENV NODE_ENV=production NEXT_TELEMETRY_DISABLED=1
COPY --from=build /app ./
EXPOSE 3000
CMD ["npm", "start", "--", "-H", "0.0.0.0", "-p", "3000"]
