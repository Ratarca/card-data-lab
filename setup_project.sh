#!/usr/bin/env bash
# Reproducible local setup for PostgreSQL, the DuckDB warehouse, and Streamlit.
# Run from any directory with: ./setup_project.sh
# Set START_DASHBOARD=0 to prepare services without starting the foreground UI.

set -euo pipefail

project_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$project_dir"

export UV_CACHE_DIR="${UV_CACHE_DIR:-/tmp/cardlab-uv-cache}"
project_pg_user="${PGUSER:-cardlab}"
project_pg_database="${PGDATABASE:-cardlab}"

echo "[1/5] Syncing the Python environment"
uv sync

echo "[2/5] Starting PostgreSQL infrastructure"
uv run task infra

echo "[3/5] Waiting for PostgreSQL"
for attempt in $(seq 1 30); do
    if docker compose exec -T postgres pg_isready -U "$project_pg_user" -d "$project_pg_database" >/dev/null 2>&1; then
        break
    fi
    if [[ "$attempt" -eq 30 ]]; then
        echo "PostgreSQL did not become ready within 30 seconds." >&2
        exit 1
    fi
    sleep 1
done

echo "[4/5] Applying OLTP migrations and initializing DuckDB bronze"
uv run task migrate
uv run task lake-init

echo "[5/5] Building bronze, silver, and gold warehouse tables"
uv run task dbt-build

if [[ "${START_DASHBOARD:-1}" == "1" ]]; then
    echo "Setup complete. Starting Streamlit at http://127.0.0.1:8501"
    exec uv run task dashboard
fi

echo "Setup complete. Start the dashboard with: uv run task dashboard"
