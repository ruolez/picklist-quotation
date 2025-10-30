FROM python:3.11-slim

# Install FreeTDS for MS SQL Server connectivity
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    freetds-dev \
    freetds-bin \
    unixodbc-dev \
    && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Copy requirements first for better caching
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY app/ ./app/

# Create data directory
RUN mkdir -p /app/data

# Expose port (will be dynamically set)
EXPOSE 5000

# Run the application
CMD ["python", "app/main.py"]
