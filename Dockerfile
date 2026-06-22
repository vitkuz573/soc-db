FROM python:3.12-slim AS builder

WORKDIR /app
COPY pyproject.toml README.md ./
COPY src/ ./src/
RUN pip install --no-cache-dir build && pip install --no-cache-dir .

FROM python:3.12-slim

RUN groupadd -r socdb && useradd -r -g socdb -d /app -s /sbin/nologin socdb

WORKDIR /app
COPY --from=builder /usr/local/lib/python3.12/site-packages /usr/local/lib/python3.12/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

COPY data/ /app/data/
COPY schema/ /app/schema/
COPY api/ /app/api/

RUN chown -R socdb:socdb /app

USER socdb
EXPOSE 8000

ENV SOC_DB_LOG_LEVEL=INFO
ENV SOC_DB_LOG_FORMAT=json

HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')"

CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "2"]
