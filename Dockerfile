FROM python:3.12-slim@sha256:3f095bce82c410e9ece1c8f718f3f5bcfdab5635657e00c2ed8ac35ad5081350 AS builder

WORKDIR /build
COPY pyproject.toml requirements.txt ./
RUN pip install --no-cache-dir --user .

FROM python:3.12-slim@sha256:3f095bce82c410e9ece1c8f718f3f5bcfdab5635657e00c2ed8ac35ad5081350

RUN groupadd -r socdb && useradd -r -g socdb -d /app -s /sbin/nologin socdb

WORKDIR /app
COPY --from=builder /root/.local /usr/local
COPY src/ src/
COPY data/ data/
COPY schema/ schema/
COPY api/ api/

EXPOSE 8000
USER socdb

HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/')" || exit 1

CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000"]
