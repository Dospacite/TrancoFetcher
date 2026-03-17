FROM ghcr.io/d4vinci/scrapling:latest

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app/src

COPY requirements.txt /app/requirements.txt
RUN python -m pip install --no-cache-dir -r /app/requirements.txt

COPY src /app/src
COPY README.md /app/README.md

ENTRYPOINT []
CMD ["python", "-m", "tranco_fetcher"]
