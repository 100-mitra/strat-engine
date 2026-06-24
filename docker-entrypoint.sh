#!/bin/sh
# Apply database migrations on container start, then hand off to the CMD (gunicorn).
# Migrations are idempotent, so this is safe to run on every boot of the single-instance demo.
set -e

python manage.py migrate --noinput

exec "$@"
