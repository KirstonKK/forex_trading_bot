# Use Python 3.9 slim image (Linux-based, works on all systems)
FROM python:3.9-slim

# Set environment variables
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    g++ \
    sqlite3 \
    git \
    && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Copy requirements first (for better caching)
COPY requirements.txt .

# Install Python dependencies
RUN pip install --upgrade pip && \
    pip install -r requirements.txt

# Copy entire bot code
COPY . .

# Create necessary directories
RUN mkdir -p data logs backtests/results

# Expose ports for potential monitoring/API
EXPOSE 8000 5001

# Set default command to run backtests
# Can be overridden by user
CMD ["python3", "backtests/scripts/run_quick_backtest.py"]
