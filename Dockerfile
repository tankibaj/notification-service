FROM python:3.13-slim AS base

WORKDIR /app

# Install uv
RUN pip install --no-cache-dir uv

# Copy dependency files
COPY pyproject.toml ./

# Install dependencies
RUN uv sync --no-dev --no-install-project

# Copy source
COPY src/ ./src/
COPY alembic/ ./alembic/
COPY alembic.ini ./alembic.ini

# Development stage (includes dev deps)
FROM base AS dev
RUN uv sync --no-install-project

EXPOSE 8000
CMD ["uv", "run", "uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]

# Production stage
FROM base AS prod
EXPOSE 8000
CMD ["uv", "run", "uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8000"]
