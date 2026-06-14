// Client API typé. Les types viennent de `schema.d.ts`, généré depuis l'OpenAPI
// du backend (`npm run generate`). Ne jamais écrire un appel à la main : passer
// par ce client pour bénéficier du typage et de la vérification de drift en CI.

import createClient, { type Client, type Middleware } from "openapi-fetch";
import type { paths } from "./schema";

export type { paths } from "./schema";
export type TokenProvider = () => string | null | Promise<string | null>;

/**
 * Crée un client API typé pour `baseUrl`, injectant le JWT Supabase courant
 * en `Authorization: Bearer` à chaque requête (auth = porte unique, spec §7).
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
