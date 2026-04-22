FROM node:18-alpine

WORKDIR /app

COPY frontend/package.json frontend/package-lock.json* ./
RUN npm install

COPY frontend/ .

# Build production bundle
RUN npm run build

EXPOSE 3000

CMD ["npx", "-y", "serve", "-s", "build", "-l", "3000"]
