"""Garde anti-régression sur la chaîne de dépendances (Bearer → tenant → session).

La requête d'appartenance vivait inline dans `get_current_tenant` sans aucune
couverture : un `:org::uuid` mal analysé par `text()` faisait planter en 500
*toute* requête authentifiée, bug invisible des tests (qui s'arrêtaient au 401).
On épingle ici la compilation de la requête, sans base.
"""

from uuid import UUID

import pytest
from sqlalchemy.dialects import postgresql

from augura_api.core.deps import membership_lookup_stmt, require_role
from augura_api.core.errors import ForbiddenError
from augura_api.core.ids import TenantId, UserId
from augura_api.core.tenancy import CurrentTenant

_T = TenantId(UUID("33cb3ba0-00fe-420b-a8c7-70736aaacc44"))
_U = UserId(UUID("11111111-1111-4111-8111-111111111111"))


def _tenant(role: str) -> CurrentTenant:
    return CurrentTenant(tenant_id=_T, user_id=_U, role=role)


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


async def test_require_role_allows_listed_role() -> None:
    """Le rôle autorisé traverse la dépendance (le tenant est renvoyé tel quel)."""
    dep = require_role("owner")
    out = await dep(_tenant("owner"))
    assert out.role == "owner"


@pytest.mark.parametrize("role", ["member", "viewer"])
async def test_require_role_forbids_other_roles(role: str) -> None:
    """Un rôle non listé (member/viewer) est refusé en 403 — garde sur /analytics/admin."""
    dep = require_role("owner")
    with pytest.raises(ForbiddenError):
        await dep(_tenant(role))
