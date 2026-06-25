#!/bin/sh
# Prepare the database, seed the demo, then hand off to the CMD (gunicorn).
# All steps are idempotent, so this is safe to run on every container boot. Keeping these here
# (rather than in a platform start command) means the same image behaves identically under
# docker-compose and on Railway/Render, with no ENTRYPOINT-vs-start-command conflicts.
set -e

python manage.py migrate --noinput
python manage.py seed_demo

exec "$@"
