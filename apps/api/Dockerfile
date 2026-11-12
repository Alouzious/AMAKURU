FROM python:3.12-slim

WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV UV_LINK_MODE=copy

COPY --from=ghcr.io/astral-sh/uv:0.9.9 /uv /usr/local/bin/uv

COPY pyproject.toml README.md ./
COPY src ./src
COPY alembic.ini ./
COPY alembic ./alembic

RUN uv sync --python 3.12 --no-dev

ENV PATH="/app/.venv/bin:$PATH"
EXPOSE 8000
CMD ["uvicorn", "amakuru.main:app", "--host", "0.0.0.0", "--port", "8000"]
