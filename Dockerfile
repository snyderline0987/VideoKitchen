FROM node:22-slim

# Install system dependencies
RUN apt-get update && apt-get install -y \
    python3 \
    python3-pip \
    python3-venv \
    ffmpeg \
    libopencv-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy backend package files
COPY backend/package*.json ./backend/
RUN cd backend && npm install

# Copy backend code
COPY backend/ ./backend/

# Copy scripts
COPY scripts/ ./scripts/
COPY recipes/ ./recipes/
COPY requirements.txt ./

# Install Python dependencies
RUN python3 -m pip install --break-system-packages --no-cache-dir -r requirements.txt || true

# Create directories
RUN mkdir -p projects data

# Initialize database
RUN cd backend && node scripts/init-db.js && node scripts/seed-recipes.js

EXPOSE 3001

WORKDIR /app/backend
CMD ["node", "server.js"]
