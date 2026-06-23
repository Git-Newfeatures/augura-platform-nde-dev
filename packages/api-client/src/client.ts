// Typed API client. The types come from `schema.d.ts`, generated from the
// backend's OpenAPI (`npm run generate`). Never write a call by hand: go
// through this client to benefit from typing and the CI drift check.

import createClient, { type Client, type Middleware } from "openapi-fetch";
import type { paths } from "./schema";

export type { paths } from "./schema";
export type TokenProvider = () => string | null | Promise<string | null>;

/**
 * Creates a typed API client for `baseUrl`, injecting the current Supabase JWT
 * as `Authorization: Bearer` on every request (auth = single gate, spec §7).
 */
export function createApiClient(
  baseUrl: string,
  getToken: TokenProvider,
): Client<paths> {
  const client = createClient<paths>({ baseUrl });

  const authMiddleware: Middleware = {
    async onRequest({ request }) {
      const token = await getToken();
      if (token) {
        request.headers.set("Authorization", `Bearer ${token}`);
      }
      return request;
    },
  };

  client.use(authMiddleware);
  return client;
}
