#!/usr/bin/env bash
# Deploys the FastAPI backend to Modal and (re)creates the prod secret `augura-api`
# from apps/api/.env — the values are never written into this script
# nor displayed (read at runtime from .env, which is not version-controlled).
#
# Prerequisites (one-time): `modal setup`  (browser auth) — or export
#   MODAL_TOKEN_ID / MODAL_TOKEN_SECRET in the env.
#
# Usage:
#   bash scripts/deploy_modal.sh                       # CORS = regex *.vercel.app (prod + previews)
#   bash scripts/deploy_modal.sh 'https://app.augura.io' # + an explicit custom domain
#
# By default CORS covers all Vercel origins (prod + dynamic previews)
# via AUGURA_CORS_ORIGIN_REGEX. The optional argument adds an explicit domain.
set -euo pipefail
cd "$(dirname "$0")/.."

FRONT_ORIGIN="${1:-}"   # optional: custom domain on top of the Vercel previews
[ -f .env ] || { echo "apps/api/.env not found (prod values required)"; exit 1; }

# Load AUGURA_* + LLM keys from .env without displaying them.
set -a; set +x; . ./.env; set +a

# JWT: HS256 (secret) if present, otherwise JWKS (RS256). The app handles both.
declare -a EXTRA=()
[ -n "${AUGURA_SUPABASE_JWT_SECRET:-}" ] && EXTRA+=("AUGURA_SUPABASE_JWT_SECRET=${AUGURA_SUPABASE_JWT_SECRET}")
[ -n "${AUGURA_SUPABASE_JWKS_URL:-}" ]   && EXTRA+=("AUGURA_SUPABASE_JWKS_URL=${AUGURA_SUPABASE_JWKS_URL}")
[ -n "${AUGURA_SUPABASE_JWT_ISSUER:-}" ] && EXTRA+=("AUGURA_SUPABASE_JWT_ISSUER=${AUGURA_SUPABASE_JWT_ISSUER}")
# Anthropic key: .env names it ANTHROPIC_API_KEY (or AUGURA_ANTHROPIC_API_KEY).
ANTHRO="${AUGURA_ANTHROPIC_API_KEY:-${ANTHROPIC_API_KEY:-}}"
[ -n "$ANTHRO" ] && EXTRA+=("AUGURA_ANTHROPIC_API_KEY=${ANTHRO}")
OPENAI="${AUGURA_OPENAI_API_KEY:-${OPENAI_API_KEY:-}}"
[ -n "$OPENAI" ] && EXTRA+=("AUGURA_OPENAI_API_KEY=${OPENAI}")
# Workaround for the CT.gov WAF 403 on Modal datacenter IPs (absent ⇒ direct call,
# graceful degradation). Relay (Edge function) PREFERRED; httpx proxy as a fallback.
[ -n "${AUGURA_CTGOV_RELAY_URL:-}" ] && EXTRA+=("AUGURA_CTGOV_RELAY_URL=${AUGURA_CTGOV_RELAY_URL}")
[ -n "${AUGURA_CTGOV_PROXY_URL:-}" ] && EXTRA+=("AUGURA_CTGOV_PROXY_URL=${AUGURA_CTGOV_PROXY_URL}")
# Supabase Storage (dataset bytes — consistent cross-container on Modal). Absent ⇒
# fallback to ephemeral local disk: REQUIRED in prod so the DQ run can re-read the upload.
[ -n "${AUGURA_SUPABASE_URL:-}" ]              && EXTRA+=("AUGURA_SUPABASE_URL=${AUGURA_SUPABASE_URL}")
[ -n "${AUGURA_SUPABASE_SERVICE_ROLE_KEY:-}" ] && EXTRA+=("AUGURA_SUPABASE_SERVICE_ROLE_KEY=${AUGURA_SUPABASE_SERVICE_ROLE_KEY}")
[ -n "${AUGURA_STORAGE_BUCKET:-}" ]            && EXTRA+=("AUGURA_STORAGE_BUCKET=${AUGURA_STORAGE_BUCKET}")

echo "[1/3] secret Modal 'augura-api' (env=prod, cors regex=*.vercel.app${FRONT_ORIGIN:+ + $FRONT_ORIGIN})"
uv run modal secret create augura-api --force \
  AUGURA_ENV=prod \
  AUGURA_DATABASE_URL="${AUGURA_DATABASE_URL:?AUGURA_DATABASE_URL missing from .env}" \
  AUGURA_CORS_ORIGIN_REGEX='^https://.*\.vercel\.app$' \
  AUGURA_CORS_ORIGINS="${FRONT_ORIGIN}" \
  AUGURA_SUPABASE_JWT_AUDIENCE="${AUGURA_SUPABASE_JWT_AUDIENCE:-authenticated}" \
  "${EXTRA[@]}"

echo "[2/3] deployment"
uv run modal deploy modal_app.py

echo "[3/3] done. Take the URL printed above and verify:"
echo "  curl https://<workspace>--augura-api-api.modal.run/healthz"
echo "Then set VITE_API_URL = that URL in Vercel (Production env) and redeploy the frontend."
