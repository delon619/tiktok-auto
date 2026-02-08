# Dockerfile for TikTok Auto Upload System
FROM python:3.11-slim

# Install dependencies for Playwright + extra fonts untuk anti-fingerprint
RUN apt-get update && apt-get install -y \
    wget \
    gnupg \
    ca-certificates \
    fonts-liberation \
    fonts-noto-color-emoji \
    fonts-freefont-ttf \
    fontconfig \
    libasound2 \
    libatk-bridge2.0-0 \
    libatk1.0-0 \
    libatspi2.0-0 \
    libcups2 \
    libdbus-1-3 \
    libdrm2 \
    libgbm1 \
    libgtk-3-0 \
    libnspr4 \
    libnss3 \
    libxcomposite1 \
    libxdamage1 \
    libxfixes3 \
    libxkbcommon0 \
    libxrandr2 \
    libxshmfence1 \
    libgl1-mesa-dri \
    libgl1-mesa-glx \
    libegl1-mesa \
    xdg-utils \
    libu2f-udev \
    libvulkan1 \
    && fc-cache -f -v \
    && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Copy requirements first for caching
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Install Playwright browsers with system deps
RUN playwright install --with-deps chromium

# Copy application code
COPY . .

# Create directories for persistent data
RUN mkdir -p /app/videos /app/cookies /app/logs /app/data

# Environment variables
ENV PYTHONUNBUFFERED=1
ENV HEADLESS_UPLOAD=true
ENV TIMEZONE=Asia/Jakarta

# Run the application
CMD ["python", "main.py"]
