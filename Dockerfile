# Use an official Python runtime
FROM python:3.11-slim

# Set environment variables to prevent Python from writing .pyc files and buffering stdout
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Install system dependencies (Poppler for pdf2image)
RUN apt-get update && apt-get install -y --no-install-recommends \
    poppler-utils \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Set the working directory
WORKDIR /app

# Copy requirements and install
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the code
COPY . .

# Metadata only: documents the default listen port (same as ${PORT:-8080} in CMD).
# EXPOSE is not substituted from .env at runtime; actual port is always $PORT in CMD.
EXPOSE 8080

# Command to run the API (PORT from env, e.g. .env / Render; defaults to 8080)
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8080} --log-level info"]