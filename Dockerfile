FROM python:3.12-slim

# - PYTHONUNBUFFERED: stream logs immediately (good for container log capture)
# - MPLBACKEND=Agg: matplotlib must run headless (no display) to render QuantStats tearsheets
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    MPLBACKEND=Agg

WORKDIR /app

# libgomp1 is required at runtime by the scientific stack (numpy/scipy OpenMP).
RUN apt-get update \
    && apt-get install -y --no-install-recommends libgomp1 \
    && rm -rf /var/lib/apt/lists/*

# Install the exact, fully-pinned dependency set first for reproducible builds + layer caching.
COPY requirements.lock ./
RUN pip install -r requirements.lock

# Application code.
COPY . .

# Collect static assets (Django admin + DRF browsable API) for WhiteNoise to serve.
RUN SECRET_KEY=build-time DEBUG=0 python manage.py collectstatic --noinput

EXPOSE 8000

# Shell-form so ${PORT} (set by Render/Railway) is expanded; defaults to 8000 for local compose.
ENTRYPOINT ["./docker-entrypoint.sh"]
CMD gunicorn config.wsgi:application --bind 0.0.0.0:${PORT:-8000} --workers ${WEB_CONCURRENCY:-3} --timeout 120
