FROM node:22-alpine AS builder
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci
COPY . .
ARG BACKEND_URL=http://backend:8000
ENV BACKEND_URL=${BACKEND_URL}
RUN npm run build

FROM node:22-alpine
WORKDIR /app
COPY --from=builder /app/.next ./.next
COPY --from=builder /app/node_modules ./node_modules
COPY --from=builder /app/package.json ./
COPY --from=builder /app/public ./public
COPY --from=builder /app/next.config.js ./
EXPOSE 3000
CMD ["npx", "next", "start", "-p", "3000"]
