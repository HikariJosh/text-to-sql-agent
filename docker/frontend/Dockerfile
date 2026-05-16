FROM node:20-alpine AS build

WORKDIR /app

COPY fronted/package.json fronted/package-lock.json ./
RUN npm ci

COPY fronted/ .
RUN npm run build

FROM nginx:alpine

COPY --from=build /app/dist /usr/share/nginx/html
COPY docker/frontend/nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]
