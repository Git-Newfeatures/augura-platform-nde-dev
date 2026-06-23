"""Pure-file guards on the alembic migration chain (no database needed)."""

from pathlib import Path

ALEMBIC_DIR = Path(__file__).parents[2] / "alembic" / "versions"


def test_migrations_beyond_baseline_are_idempotent() -> None:
    """0001 applies the bundle wholesale; every migration >=0002 must be safely
    re-runnable on an already-migrated DB (CREATE/DROP ... IF [NOT] EXISTS or
    CREATE OR REPLACE)."""
    offenders: list[str] = []
    for path in sorted(ALEMBIC_DIR.glob("0*.py")):
        if path.name.startswith("0001"):
            continue
        src = path.read_text(encoding="utf-8").lower()
        if not any(tok in src for tok in ("if not exists", "if exists", "create or replace")):
            offenders.append(path.name)
    assert not offenders, (
        f"non-idempotent migrations (no IF [NOT] EXISTS / CREATE OR REPLACE): {offenders}"
    )
