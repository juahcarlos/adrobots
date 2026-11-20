FROM python:3.12.8-slim-bookworm

ENV UV_PROJECT_ENVIRONMENT=/opt/venv \
    UV_COMPILE_BYTECODE=1 \
    PYTHONDONTWRITEBYTECODE=1

WORKDIR /app

RUN pip install --no-cache-dir uv==0.13.5

COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev

COPY . .

RUN useradd --create-home --uid 1000 appuser \
    && mkdir -p /home/appuser && chown -R appuser:appuser /home/appuser
USER appuser

EXPOSE 8000

ENV PATH="/opt/venv/bin:$PATH"

CMD ["sh", "-c", "alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port 8000"]
