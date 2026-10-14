FROM node:20-slim

WORKDIR /app
COPY package*.json ./
RUN npm ci
COPY . .
RUN npm run build
CMD ["npm", "run", "start", "--", "-H", "0.0.0.0", "-p", "3000"]
