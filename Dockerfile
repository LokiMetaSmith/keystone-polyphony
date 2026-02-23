# Use a lightweight Python base image
FROM python:3.12-slim

# Install Node.js (for Hyperswarm sidecar)
RUN apt-get update && apt-get install -y nodejs npm git && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
# Note: hyperswarm-python is NOT used directly; we use the Node sidecar.

# Install Node.js dependencies for the sidecar
COPY src/liminal_bridge/sidecar/package.json ./src/liminal_bridge/sidecar/
RUN cd src/liminal_bridge/sidecar && npm install

# Copy the rest of the application
COPY . .

# Set environment variables
ENV PYTHONPATH=/app/src
ENV PYTHONUNBUFFERED=1

# Default command: Run the MCP server
CMD ["python", "src/liminal_bridge/server.py"]
