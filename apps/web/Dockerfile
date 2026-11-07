FROM node:22.23.4-bookworm-slim

WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci
COPY app ./app
COPY lib ./lib
COPY next.config.ts tsconfig.json next-env.d.ts ./

ENV NEXT_PUBLIC_DEMO_FIXTURE=sample
ENV NEXT_PUBLIC_API_BASE_URL=
ARG API_INTERNAL_ORIGIN=http://api:8000
ARG NEXT_PUBLIC_HOSTED_DEMO=false
ENV NEXT_PUBLIC_HOSTED_DEMO=$NEXT_PUBLIC_HOSTED_DEMO

RUN npm run build

ENV NODE_ENV=production
EXPOSE 3000
CMD ["sh", "-c", "exec npx next start --hostname \"${WEB_HOST:-0.0.0.0}\" --port \"${PORT:-3000}\""]
