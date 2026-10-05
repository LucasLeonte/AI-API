# ════════════════════════════════════════════════════════════════════════════════
# Stage 1 — Builder: install dependencies into an isolated virtual environment
# ════════════════════════════════════════════════════════════════════════════════
FROM python:3.11-slim AS builder

WORKDIR /build

# Install build tools
RUN apt-get update && apt-get install -y --no-install-recommends \
        gcc \
        libffi-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy only the requirements first (maximises Docker layer caching)
COPY requirements.txt .

# Create a virtual environment and install into it
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r requirements.txt


# ════════════════════════════════════════════════════════════════════════════════
# Stage 2 — Runtime: lean image with non-root user
# ════════════════════════════════════════════════════════════════════════════════
FROM python:3.11-slim AS runtime

# Security: run as non-root
RUN groupadd --gid 1001 appgroup \
    && useradd --uid 1001 --gid appgroup --no-create-home --shell /sbin/nologin appuser

WORKDIR /app

# Copy the pre-built virtual environment from builder
COPY --from=builder /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Copy application source
COPY app/ ./app/

# Ensure the non-root user owns the working directory
RUN chown -R appuser:appgroup /app

USER appuser

# Expose the application port
EXPOSE 8000

# Health check for container orchestrators (Kubernetes, ECS, Render, etc.)
HEALTHCHECK --interval=30s --timeout=10s --start-period=15s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')" \
    || exit 1

# Start the server with 2 Uvicorn workers
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "2"]
