FROM python:3.12-slim

WORKDIR /app

# System deps
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq-dev gcc && rm -rf /var/lib/apt/lists/*

# Python deps — copy pyproject.toml and src together so -e install works
COPY pyproject.toml .
COPY src/ src/
RUN pip install --no-cache-dir -e ".[dev]" && pip install psycopg2-binary

# Config & migrations
COPY alembic/ alembic/
COPY alembic.ini .
COPY infra/ infra/

EXPOSE 8000

CMD ["uvicorn", "butler.main:app", "--host", "0.0.0.0", "--port", "8000"]
