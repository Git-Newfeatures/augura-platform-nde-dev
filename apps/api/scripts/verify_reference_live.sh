#!/usr/bin/env bash
# Self-contained runtime check of the /reference/* endpoints:
#   provisions a throwaway Postgres+pgvector, applies the canonical bundle
#   (schema -> functions -> seed -> policies), creates a test tenant, then
#   queries the real FastAPI app (role augura_api, RLS active) via scripts/
#   verify_reference.py. Does NOT touch the real Supabase database.
#
# Prerequisites: Docker. Usage: from apps/api/  ->  bash scripts/verify_reference_live.sh
set -euo pipefail
cd "$(dirname "$0")/.."

C=augura-verify-pg
ORG=33cb3ba0-00fe-420b-a8c7-70736aaacc44
USER_ID=11111111-1111-4111-8111-111111111111

cleanup() { docker rm -f "$C" >/dev/null 2>&1 || true; }
trap cleanup EXIT
cleanup

echo "[1/4] Postgres+pgvector"
docker run -d --name "$C" -e POSTGRES_PASSWORD=postgres -p 55432:5432 pgvector/pgvector:pg16 >/dev/null
for _ in $(seq 1 40); do docker exec "$C" pg_isready -U postgres >/dev/null 2>&1 && break; sleep 1; done

PSQL() { docker exec -i "$C" psql -v ON_ERROR_STOP=1 -U postgres -d postgres "$@"; }

echo "[2/4] canonical bundle (schema -> functions -> seed -> policies)"
PSQL < supabase/schema.sql    >/dev/null
PSQL < supabase/functions.sql >/dev/null
PSQL < supabase/seed.sql       >/dev/null
PSQL < supabase/policies.sql  >/dev/null

echo "[3/4] test tenant + augura_api password"
PSQL >/dev/null <<SQL
insert into orgs (id,name,slug) values ('$ORG','Verify Org','verify-org') on conflict do nothing;
insert into memberships (org_id,user_id,role) values ('$ORG','$USER_ID','owner') on conflict do nothing;
alter role augura_api with password 'augura_api_pw';
SQL

echo "[4/4] checking the endpoints (app as augura_api, RLS active)"
export AUGURA_ENV=dev
export AUGURA_SUPABASE_JWT_SECRET="${AUGURA_SUPABASE_JWT_SECRET:-verify-secret-rotate-me-please}"
export AUGURA_DATABASE_URL="postgresql://augura_api:augura_api_pw@localhost:55432/postgres"
uv run python scripts/verify_reference.py
