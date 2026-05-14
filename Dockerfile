FROM python:3.11-slim

WORKDIR /app

# Install system dependencies for PyMuPDF and other packages
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libffi-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first for layer caching
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY api/ ./api/
COPY ipo_analyzer/ ./ipo_analyzer/
COPY data/ ./data/

# Create storage directories (do not rely on COPY storage/)
RUN mkdir -p storage/uploads storage/results storage/tmp

# Set environment defaults
ENV PYTHONUNBUFFERED=1
ENV STORAGE_BASE_PATH=/app/storage
ENV API_HOST=0.0.0.0
ENV API_PORT=8000

EXPOSE 8000

CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000"]
