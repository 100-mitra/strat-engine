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

# Ensure the entrypoint is executable. Build contexts uploaded from Windows (e.g. `railway up`)
# don't preserve the +x bit, so set it explicitly rather than relying on the source file's mode.
RUN chmod +x docker-entrypoint.sh

# Pre-render the seeded strategy's sample metrics + tearsheet (no DB needed) so the landing page
# shows real numbers and a one-click tearsheet. Must run before collectstatic.
RUN SECRET_KEY=build-time DEBUG=0 python manage.py render_sample

# Collect static assets (Django admin + DRF browsable API + the sample tearsheet) for WhiteNoise.
RUN SECRET_KEY=build-time DEBUG=0 python manage.py collectstatic --noinput

EXPOSE 8000

# Invoke via `sh` so execution never depends on the +x bit; the CMD's ${PORT} (set by
# Render/Railway) is expanded by the shell-form CMD below, defaulting to 8000 for local compose.
# --preload imports the app once in the master and forks workers (copy-on-write), so the heavy
# scientific stack isn't duplicated per worker — important headroom on small free-tier instances.
ENTRYPOINT ["sh", "./docker-entrypoint.sh"]
CMD gunicorn config.wsgi:application --bind 0.0.0.0:${PORT:-8000} --workers ${WEB_CONCURRENCY:-2} --preload --timeout 120
