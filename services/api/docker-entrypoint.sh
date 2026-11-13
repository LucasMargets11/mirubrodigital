#!/bin/sh
set -e

# ── Production entrypoint for the API container ─────────────────────────────
# Modes (first argument):
#
#   migrate    — one-off task: apply migrations, run the post-migration database
#                checks with the real environment, exit.
#   precheck   — one-off task: `check --deploy --tag security` (no DB writes).
#   postcheck  — one-off task: database checks only (e.g. before enabling
#                AI_USAGE_METERING_ENABLED on an already migrated database).
#   anything else is exec'd as-is (gunicorn by default, celery for workers).
#
# Optional pre-start hooks for the default mode:
#   RUN_MIGRATIONS=true    — run the `migrate` sequence below before starting
#   RUN_COLLECTSTATIC=true — run `manage.py collectstatic --noinput`
#
# Migration sequence and AI usage metering (appointments.E002):
#   The `database`-tagged check fails while AI_USAGE_METERING_ENABLED=true and
#   appointments.0015 is not applied, and Django runs it inside `migrate`, so a
#   database that still lacks 0015 could never be upgraded with metering on.
#   The migrate process itself never meters usage, so it runs with metering
#   forced off for that process only; the check then runs again with the real
#   environment and fails the task if the schema is still not ready.

cd /app

run_migrate() {
    echo "[entrypoint] Applying migrations (AI usage metering off for this process)..."
    AI_USAGE_METERING_ENABLED=false python manage.py migrate --noinput
    echo "[entrypoint] Migrations applied. Post-migration database checks..."
    python manage.py check --database default --tag database
    echo "[entrypoint] Post-migration checks passed."
}

case "$1" in
    migrate)
        run_migrate
        exit 0
        ;;
    precheck)
        python manage.py check --deploy --tag security --fail-level ERROR
        exit 0
        ;;
    postcheck)
        python manage.py check --database default --tag database
        exit 0
        ;;
esac

if [ "${RUN_MIGRATIONS:-false}" = "true" ]; then
    run_migrate
fi

if [ "${RUN_COLLECTSTATIC:-false}" = "true" ]; then
    echo "[entrypoint] RUN_COLLECTSTATIC=true — collecting static files..."
    python manage.py collectstatic --noinput
    echo "[entrypoint] Static files collected."
fi

# Hand off to the CMD (gunicorn by default)
exec "$@"
