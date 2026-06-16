# Modules — convention de découpage

Chaque module est une **tranche verticale** isolée (contrat import-linter
« les modules de données ne s'importent pas entre eux »). Layout canonique :

```
modules/<nom>/
  __init__.py   # interface publique : ré-expose `router` + les fonctions consommées
                # cross-module (ex. jobs: create_job/get_job ; corpus: search_corpus)
  router.py     # adaptateur HTTP : routes FastAPI, dépend de core.deps (tenant/session)
  service.py    # logique applicative ; orchestre le repo, applique les règles
  repo.py       # accès données (SQLAlchemy), chaque méthode scopée tenant_id
  models.py     # tables SQLAlchemy
  schemas.py    # contrats Pydantic (entrée/sortie)
```

## Construction service ⁄ repo (DI)

Convention : **le routeur injecte un repo construit dans le service** —
`XService(XRepo(session))` (cf. studies/corpus/datasets). Les modules plus anciens
(simulation/documents/analytics) injectent encore la `session` et reconstruisent le
repo par méthode ; comportement identique, à aligner sur la forme repo-injectée au
prochain passage. Ne pas mélanger les deux dans un nouveau module.

## Exceptions assumées

- **jobs** — infrastructure transverse (file d'attente). Logique dans `service.py`
  (`create_job`/`get_job`, fonctions module-level idempotentes), pas de classe service ;
  pas de `schemas` d'entrée riches. Consommé par simulation/documents ET par son routeur.
- **agents** — couche d'orchestration LLM : pas de `repo.py`/`models.py` (ne possède pas
  de table ; lit le corpus via l'interface publique de `corpus`). `service.py` +
  `streaming.py` + `tools.py`.

## Autorisation

Les routes sensibles se gardent avec `core.deps.require_role("owner", …)` en dépendance
(ex. `/analytics/admin`). Tout le reste passe par la chaîne `CurrentTenantDep` +
`SessionDep` (RLS tenant active).
