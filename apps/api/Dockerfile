FROM python:3.12.3-slim-bookworm

WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

RUN apt-get update \
    && apt-get install -y --no-install-recommends libpq5 \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.lock pyproject.toml alembic.ini ./
RUN pip install --no-cache-dir -r requirements.lock
COPY src ./src
COPY alembic ./alembic
COPY scripts/bootstrap_demo_sample.sql ./scripts/bootstrap_demo_sample.sql
COPY docker/entrypoint.py ./docker/entrypoint.py

RUN pip install --no-cache-dir --no-deps --no-build-isolation .

EXPOSE 8000
ENTRYPOINT ["python", "/app/docker/entrypoint.py"]
