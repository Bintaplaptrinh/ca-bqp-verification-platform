#!/usr/bin/env sh
set -eu
cd "$(dirname "$0")/../../apps/backend"
alembic upgrade head
alembic current
alembic downgrade base
alembic upgrade head
alembic current
