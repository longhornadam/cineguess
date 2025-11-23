FROM node:18-alpine
WORKDIR /app

# Install dependencies
COPY package*.json ./
RUN npm ci --omit=dev

# Copy app code
COPY server server
COPY public public
# React src is present but not used in this API-only image; included for completeness
COPY src src

ENV NODE_ENV=production
ENV PORT=8080

CMD ["node", "server/index.js"]
