# Multi-stage build for MCP OpenAPI Generator
# Stage 1: Build dependencies
FROM python:3.11-slim AS builder

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    git \
    && rm -rf /var/lib/apt/lists/*

# Install UV for fast package management
RUN pip install --no-cache-dir uv

# Copy project files
COPY pyproject.toml README.md ./
COPY src/ ./src/

# Install package in editable mode
RUN uv pip install --system -e .

# Stage 2: Runtime with generators
FROM python:3.11-slim AS runtime

WORKDIR /app

# Install system dependencies including OpenAPI generators
RUN apt-get update && apt-get install -y --no-install-recommends \
    openjdk-17-jre-headless \
    curl \
    git \
    npm \
    && rm -rf /var/lib/apt/lists/*

# Install openapi-generator-cli and swagger-codegen via npm
RUN npm install -g @openapitools/openapi-generator-cli swagger-codegen

# Install validation tools
RUN npm install -g @stoplight/spectral-cli vacuum

# Copy Python package from builder
COPY --from=builder /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

# Copy source code
COPY src/ ./src/

# Create non-root user
RUN useradd --create-home --shell /bin/bash mcp
USER mcp

# Set working directory
WORKDIR /home/mcp

# Default command
ENTRYPOINT ["python", "-m", "mcp_openapi_generator.server"]