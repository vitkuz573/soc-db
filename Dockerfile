FROM python:3.12-slim AS builder

WORKDIR /build
COPY pyproject.toml requirements.txt ./
COPY src/ src/
RUN pip install --no-cache-dir --user .

FROM python:3.12-slim

RUN groupadd -r socdb && useradd -r -g socdb -d /app -s /sbin/nologin socdb

WORKDIR /app
COPY --from=builder /root/.local /usr/local
COPY data/ data/
COPY schema/ schema/
COPY api/ api/

RUN pip install --no-cache-dir fastapi uvicorn && \
    rm -rf /root/.cache

EXPOSE 8000
USER socdb

HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/')" || exit 1

CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000"]
