"""Guard: integration tests must NEVER target the demo Supabase project.

The fixtures commit (they open `session.begin()`), so running the suite against
the demo database leaves rows behind (an "Integration" study, test datasets, jobs…).
In CI they run against an ephemeral Postgres; locally, point AUGURA_DATABASE_URL
at a throwaway Supabase branch. If the URL contains the demo project ref, we fail
hard BEFORE writing anything at all.
"""

import os

import pytest

# Demo/connected Supabase project (must not be polluted). Extend if needed.
_FORBIDDEN_PROJECT_REFS = ("fqmoylmvjoafihiuiiuj",)


@pytest.fixture(autouse=True)
def _forbid_demo_db() -> None:
    url = os.environ.get("AUGURA_DATABASE_URL", "")
    for ref in _FORBIDDEN_PROJECT_REFS:
        if ref in url:
            pytest.fail(
                f"Integration tests pointed at the demo Supabase project ({ref}): "
                "they would commit data. Use a throwaway Supabase branch "
                "(or let CI use its ephemeral Postgres).",
                pytrace=False,
            )
