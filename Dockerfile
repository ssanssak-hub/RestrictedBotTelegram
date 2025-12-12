# Use Python 3.9 slim image
FROM python:3.9-slim

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app

# Set work directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    g++ \
    libffi-dev \
    libssl-dev \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first for better caching
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Copy project
COPY . .

# Create necessary directories
RUN mkdir -p data/files data/cache data/logs sessions config backups

# Set permissions
RUN chmod +x scripts/*.sh

# Create non-root user
RUN useradd -m -u 1000 -s /bin/bash appuser && \
    chown -R appuser:appuser /app
USER appuser

# Expose port
EXPOSE 8080

# Health check
HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8080/health || exit 1

# Run the application
CMD ["python", "main.py"]

FROM python:3.11-slim

WORKDIR /app

# نصب سیستم‌های لازم
RUN apt-get update && apt-get install -y \
    gcc \
    g++ \
    && rm -rf /var/lib/apt/lists/*

# کپی فایل‌ها
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# ایجاد پوشه‌های لازم
RUN mkdir -p data downloads uploads backups cache templates static logs

CMD ["python", "telegram_bot_complete.py"]
