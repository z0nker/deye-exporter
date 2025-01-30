FROM python:3.11-slim

WORKDIR /app

# Install build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    python3-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first to leverage Docker cache
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the application
COPY . .

# Create non-root user for security
RUN useradd -m -r exporter && \
    chown -R exporter:exporter /app

USER exporter

# Expose the metrics port
EXPOSE 9877

# Run the exporter
CMD ["python", "exporter.py"]
