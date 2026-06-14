"""Garde anti-régression sur la chaîne de dépendances (Bearer → tenant → session).

La requête d'appartenance vivait inline dans `get_current_tenant` sans aucune
couverture : un `:org::uuid` mal analysé par `text()` faisait planter en 500
*toute* requête authentifiée, bug invisible des tests (qui s'arrêtaient au 401).
On épingle ici la compilation de la requête, sans base.
"""

from uuid import UUID

import pytest
from sqlalchemy.dialects import postgresql

from augura_api.core.deps import membership_lookup_stmt
from augura_api.core.ids import TenantId


@pytest.mark.parametrize(
    "requested_org",
    [None, TenantId(UUID("33cb3ba0-00fe-420b-a8c7-70736aaacc44"))],
    ids=["no-org", "with-org"],
)
def test_membership_lookup_stmt_compiles(requested_org: TenantId | None) -> None:
    """Avec ou sans org demandé, la requête compile sous le dialecte PostgreSQL
    et déclare bien le paramètre lié `org` (la régression levait un ArgumentError)."""
    stmt = membership_lookup_stmt(requested_org)
    compiled = stmt.compile(
        dialect=postgresql.dialect(), compile_kwargs={"render_postcaststring": True}
    )
    sql = str(compiled)
    assert "cast(" in sql.lower()  # cast(:org as uuid), pas :org::uuid
    assert "org" in compiled.params
    expected = str(requested_org) if requested_org else None
    assert compiled.params["org"] == expected
