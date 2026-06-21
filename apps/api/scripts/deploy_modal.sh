#!/usr/bin/env bash
# Déploie le backend FastAPI sur Modal et (re)crée le secret prod `augura-api`
# à partir d'apps/api/.env — les valeurs ne sont jamais écrites dans ce script
# ni affichées (lues à l'exécution depuis .env, non versionné).
#
# Prérequis (one-time) : `modal setup`  (auth navigateur) — ou exporter
#   MODAL_TOKEN_ID / MODAL_TOKEN_SECRET dans l'env.
#
# Usage :
#   bash scripts/deploy_modal.sh                       # CORS = regex *.vercel.app (prod + previews)
#   bash scripts/deploy_modal.sh 'https://app.augura.io' # + un domaine custom explicite
#
# Le CORS couvre par défaut toutes les origines Vercel (prod + previews dynamiques)
# via AUGURA_CORS_ORIGIN_REGEX. L'argument optionnel ajoute un domaine explicite.
set -euo pipefail
cd "$(dirname "$0")/.."

FRONT_ORIGIN="${1:-}"   # optionnel : domaine custom en plus des previews Vercel
[ -f .env ] || { echo "apps/api/.env introuvable (valeurs prod requises)"; exit 1; }

# Charge AUGURA_* + clés LLM depuis .env sans les afficher.
set -a; set +x; . ./.env; set +a

# JWT : HS256 (secret) si présent, sinon JWKS (RS256). L'app gère les deux.
declare -a EXTRA=()
[ -n "${AUGURA_SUPABASE_JWT_SECRET:-}" ] && EXTRA+=("AUGURA_SUPABASE_JWT_SECRET=${AUGURA_SUPABASE_JWT_SECRET}")
[ -n "${AUGURA_SUPABASE_JWKS_URL:-}" ]   && EXTRA+=("AUGURA_SUPABASE_JWKS_URL=${AUGURA_SUPABASE_JWKS_URL}")
[ -n "${AUGURA_SUPABASE_JWT_ISSUER:-}" ] && EXTRA+=("AUGURA_SUPABASE_JWT_ISSUER=${AUGURA_SUPABASE_JWT_ISSUER}")
# Clé Anthropic : .env la nomme ANTHROPIC_API_KEY (ou AUGURA_ANTHROPIC_API_KEY).
ANTHRO="${AUGURA_ANTHROPIC_API_KEY:-${ANTHROPIC_API_KEY:-}}"
[ -n "$ANTHRO" ] && EXTRA+=("AUGURA_ANTHROPIC_API_KEY=${ANTHRO}")
OPENAI="${AUGURA_OPENAI_API_KEY:-${OPENAI_API_KEY:-}}"
[ -n "$OPENAI" ] && EXTRA+=("AUGURA_OPENAI_API_KEY=${OPENAI}")
# Contournement du 403 WAF CT.gov sur les IP datacenter Modal (absents ⇒ appel direct,
# dégradation gracieuse). Relais (fonction Edge) PRIVILÉGIÉ ; proxy httpx en alternative.
[ -n "${AUGURA_CTGOV_RELAY_URL:-}" ] && EXTRA+=("AUGURA_CTGOV_RELAY_URL=${AUGURA_CTGOV_RELAY_URL}")
[ -n "${AUGURA_CTGOV_PROXY_URL:-}" ] && EXTRA+=("AUGURA_CTGOV_PROXY_URL=${AUGURA_CTGOV_PROXY_URL}")

echo "[1/3] secret Modal 'augura-api' (env=prod, cors regex=*.vercel.app${FRONT_ORIGIN:+ + $FRONT_ORIGIN})"
uv run modal secret create augura-api --force \
  AUGURA_ENV=prod \
  AUGURA_DATABASE_URL="${AUGURA_DATABASE_URL:?AUGURA_DATABASE_URL manquant dans .env}" \
  AUGURA_CORS_ORIGIN_REGEX='^https://.*\.vercel\.app$' \
  AUGURA_CORS_ORIGINS="${FRONT_ORIGIN}" \
  AUGURA_SUPABASE_JWT_AUDIENCE="${AUGURA_SUPABASE_JWT_AUDIENCE:-authenticated}" \
  "${EXTRA[@]}"

echo "[2/3] déploiement"
uv run modal deploy modal_app.py

echo "[3/3] terminé. Récupère l'URL imprimée ci-dessus puis vérifie :"
echo "  curl https://<workspace>--augura-api-api.modal.run/healthz"
echo "Ensuite, mets VITE_API_URL = cette URL dans Vercel (env Production) et redéploie le front."
