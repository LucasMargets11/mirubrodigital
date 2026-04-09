#!/bin/sh
set -e

# ── Production entrypoint for the API container ─────────────────────────────
# Supports two optional pre-start hooks controlled by environment variables:
#
#   RUN_MIGRATIONS=true   — run `manage.py migrate --noinput` before starting
#   RUN_COLLECTSTATIC=true — run `manage.py collectstatic --noinput`
#
# Usage examples:
#   • ECS one-off task (migrate only):
#       command: ["sh", "docker-entrypoint.sh", "migrate"]
#   • Normal web container (no auto-migrate — migrations run as a separate task):
#       command: ["sh", "docker-entrypoint.sh"]    (falls through to CMD)
#   • Auto-migrate on start (simple deployments):
#       environment: RUN_MIGRATIONS=true
#
# When called with "migrate" as the first argument, it runs migrations and exits
# (useful for ECS RunTask / Kubernetes Job).

cd /app

if [ "$1" = "migrate" ]; then
    echo "[entrypoint] Running migrations (one-off task)..."
    python src/manage.py migrate --noinput
    echo "[entrypoint] Migrations complete."
    exit 0
fi

if [ "${RUN_MIGRATIONS:-false}" = "true" ]; then
    echo "[entrypoint] RUN_MIGRATIONS=true — applying migrations..."
    python src/manage.py migrate --noinput
    echo "[entrypoint] Migrations applied."
fi

if [ "${RUN_COLLECTSTATIC:-false}" = "true" ]; then
    echo "[entrypoint] RUN_COLLECTSTATIC=true — collecting static files..."
    python src/manage.py collectstatic --noinput
    echo "[entrypoint] Static files collected."
fi

# Hand off to the CMD (gunicorn by default)
exec "$@"
