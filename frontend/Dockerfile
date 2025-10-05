FROM node:20-alpine

WORKDIR /app

# Copy package files first for better caching
COPY package.json package-lock.json* ./

# Install dependencies
RUN npm install --verbose

# Copy configuration files
COPY tsconfig.json ./
COPY vite.config.ts ./
COPY vite.config.dev.ts ./
COPY vite-env.d.ts ./
COPY index.html ./

# Copy source files (excluding compiled .js files via .dockerignore)
COPY src ./src

# Create empty cert directory for development compatibility
RUN mkdir -p cert

# Set NODE_ENV to production for build
ENV NODE_ENV=production

# CRITICAL: Set build-time environment variables for Vite
ARG VITE_API_URL
ARG VITE_HMAC_SECRET_KEY  
ARG VITE_GIFT_BOT_USERNAME
ENV VITE_API_URL=$VITE_API_URL
ENV VITE_HMAC_SECRET_KEY=$VITE_HMAC_SECRET_KEY
ENV VITE_GIFT_BOT_USERNAME=$VITE_GIFT_BOT_USERNAME

# Build for production
RUN npm run build

# Install serve to serve static files
RUN npm install -g serve

EXPOSE 5173

# Serve the built application
CMD ["serve", "-s", "dist", "-l", "5173"]