FROM python:3.12-slim

RUN apt-get update && apt-get install -y \
    git curl build-essential && \
    rm -rf /var/lib/apt/lists/*

# Install Node.js (required for Claude Agent SDK / Mode S)
RUN curl -fsSL https://deb.nodesource.com/setup_22.x | bash - && \
    apt-get install -y nodejs && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python dependencies first (cache-friendly)
COPY pyproject.toml ./
RUN pip install --no-cache-dir -e . 2>/dev/null || true

# Copy full source
COPY core/ core/
COPY cli/ cli/
COPY server/ server/
COPY templates/ templates/
COPY main.py ./

# Re-install with full source
RUN pip install --no-cache-dir -e . && \
    pip install --no-cache-dir datasets

COPY swe/ swe/

ENV ANIMAWORKS_DATA_DIR=/root/.animaworks
ENV PYTHONUNBUFFERED=1

ENTRYPOINT ["python3", "swe/runner.py"]
