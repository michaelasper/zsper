FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY pyproject.toml README.md ./
COPY src ./src
COPY services/brain-api/app ./services/brain-api/app

RUN pip install --no-cache-dir \
    . \
    "fastapi>=0.115" \
    "httpx>=0.27" \
    "pydantic>=2.8" \
    "psycopg[binary]>=3.2" \
    "redis>=5.0" \
    "docling>=2.0" \
    "numpy>=2.0" \
    "rank-bm25>=0.2" \
    "sentence-transformers>=3.0" \
    "uvicorn[standard]>=0.30"

WORKDIR /app/services/brain-api

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
