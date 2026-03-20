FROM python:3.12.8-slim AS builder

WORKDIR /app
COPY pyproject.toml .
COPY src/ src/
RUN pip install --no-cache-dir .

FROM python:3.12.8-slim

RUN apt-get update && apt-get install -y --no-install-recommends curl && rm -rf /var/lib/apt/lists/*
RUN useradd --create-home --shell /bin/bash appuser
RUN mkdir -p /home/appuser/.ag402 && chown appuser:appuser /home/appuser/.ag402
WORKDIR /app

COPY --from=builder /usr/local/lib/python3.12/site-packages /usr/local/lib/python3.12/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin
COPY src/ src/
COPY static/ static/

USER appuser
EXPOSE 8000

CMD ["python", "-m", "rugcheck.main"]
