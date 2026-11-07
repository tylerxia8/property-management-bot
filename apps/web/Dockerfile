FROM node:22.23.4-bookworm-slim

WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci
COPY app ./app
COPY lib ./lib
COPY next.config.ts tsconfig.json next-env.d.ts ./

ENV NEXT_PUBLIC_DEMO_FIXTURE=sample
ENV NEXT_PUBLIC_API_BASE_URL=

RUN npm run build

ENV NODE_ENV=production
EXPOSE 3000
CMD ["npx", "next", "start", "--hostname", "0.0.0.0", "--port", "3000"]
