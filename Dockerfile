FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    UV_PROJECT_ENVIRONMENT=/opt/venv \
    PATH=/opt/venv/bin:$PATH

# ffmpeg decodes the iTunes m4a previews to wav for Essentia.
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
RUN pip install --no-cache-dir uv==0.13.3

# Dependencies first for layer caching; the lockfile pins every version.
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev
COPY analyzer.py app.py ./

# The pod runs as this user and mounts its data volume at /data.
RUN useradd --uid 10001 --no-create-home --shell /usr/sbin/nologin tempo \
    && mkdir /data && chown 10001:10001 /data
USER 10001
ENV TEMPO_DB=/data/tempo.db
EXPOSE 8000

HEALTHCHECK CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/healthz')"
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000"]
