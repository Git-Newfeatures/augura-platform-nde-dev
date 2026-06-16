# @augura/api-client

Client TypeScript **généré** depuis l'OpenAPI du backend FastAPI (spec §9).
**Ne jamais éditer `src/schema.d.ts` ni `openapi.json` à la main.**

## Régénérer

```bash
# 1. Dump du contrat OpenAPI depuis le backend
cd ../../apps/api && AUGURA_ENV=dev uv run python scripts/dump_openapi.py \
  > ../../packages/api-client/openapi.json
# 2. Types TS
cd ../../packages/api-client && npm run generate
```

La CI (`client-drift`) régénère les deux et casse si le client commité a dérivé
du contrat — le front ne peut donc jamais appeler une API qui n'existe pas.

## Usage

```ts
import { createApiClient } from "@augura/api-client/src/client";

const api = createApiClient(import.meta.env.VITE_API_URL, async () => {
  const { data } = await supabase.auth.getSession();
  return data.session?.access_token ?? null;
});

const { data, error } = await api.GET("/studies");
```
