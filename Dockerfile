FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY pyproject.toml README.md ./
COPY src ./src

RUN pip install --no-cache-dir . \
    && playwright install --with-deps chromium

COPY targets.example.yml ./

RUN mkdir -p /app/.data/debug

CMD ["python", "-m", "vfs_bot", "run"]
