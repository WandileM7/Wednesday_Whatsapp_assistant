FROM python:3.10-bookworm

WORKDIR /app

# Update system packages and install Node.js for React build
RUN apt-get update && apt-get upgrade -y && \
    apt-get install -y curl libprotobuf-dev protobuf-compiler && \
    curl -fsSL https://deb.nodesource.com/setup_20.x | bash - && \
    apt-get install -y nodejs && \
    apt-get clean && rm -rf /var/lib/apt/lists/*

# Copy and install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Build React dashboard (if frontend exists)
RUN if [ -d "frontend" ] && [ -f "frontend/package.json" ]; then \
    cd frontend && npm install && npm run build; \
    fi

# Expose the port
EXPOSE 5000

# Set environment variables
ENV PYTHONUNBUFFERED=1

# Run the application
CMD ["python", "main.py"]
