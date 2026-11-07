FROM node:22-alpine AS build

WORKDIR /app

COPY package*.json ./

RUN npm ci --no-audit --no-fund --fetch-retries=5 --fetch-timeout=120000

COPY . .

ARG VITE_API_URL
ENV VITE_API_URL=${VITE_API_URL}

RUN npm run build

FROM nginx:1.28-alpine

COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html

EXPOSE 80