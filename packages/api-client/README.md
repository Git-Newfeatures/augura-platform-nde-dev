# @augura/api-client

TypeScript client **generated** from the FastAPI backend's OpenAPI (spec §9).
**Never edit `src/schema.d.ts` or `openapi.json` by hand.**

## Regenerate

```bash
# 1. Dump the OpenAPI contract from the backend
cd ../../apps/api && AUGURA_ENV=dev uv run python scripts/dump_openapi.py \
  > ../../packages/api-client/openapi.json
# 2. TS types
cd ../../packages/api-client && npm run generate
```

The CI (`client-drift`) regenerates both and breaks if the committed client has drifted
from the contract — so the frontend can never call an API that does not exist.

## Usage

```ts
import { createApiClient } from "@augura/api-client/src/client";

const api = createApiClient(import.meta.env.VITE_API_URL, async () => {
  const { data } = await supabase.auth.getSession();
  return data.session?.access_token ?? null;
});

const { data, error } = await api.GET("/studies");
```
