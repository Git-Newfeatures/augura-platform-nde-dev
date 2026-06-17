"""Génère le SQL de seed de la taxonomie sémantique depuis les CSV du MVP.

Usage: python scripts/gen_semantic_seed.py <csv_dir> > seed_fragment.sql
Déterministe : colonnes citées, valeurs échappées, vides → NULL, bool/num non quotés.
Le fragment produit est destiné à être collé dans supabase/seed.sql.
"""

from __future__ import annotations

import csv
import sys
from pathlib import Path

# Colonnes booléennes et numériques par table (le reste = texte). Aligne avec le DDL.
BOOL_COLS: dict[str, set[str]] = {
    "taxonomy_concepts": {"active"},
    "table_archetypes": {"is_surrogate", "active"},
    "taxonomy_measurement_units": {"is_preferred"},
    "unit_conversions": {"bidirectional"},
}
NUM_COLS: dict[str, set[str]] = {
    "taxonomy_concepts": {"layer", "value_min", "value_max"},
    "table_archetypes": {"semantic_score"},
    "unit_conversions": {"scale_factor", "offset", "precision"},
}
# Ordre d'insertion (FK : concepts d'abord).
TABLES = [
    "taxonomy_concepts",
    "taxonomy_synonyms",
    "taxonomy_dq_valid_values",
    "taxonomy_measurement_units",
    "unit_conversions",
    "table_archetypes",
    "dq_constraints",
]


def _lit(table: str, col: str, raw: str) -> str:
    val = (raw or "").strip()
    if val == "":
        return "NULL"
    if col in BOOL_COLS.get(table, set()):
        return "true" if val.lower() in ("true", "t", "1", "yes") else "false"
    if col in NUM_COLS.get(table, set()):
        return val  # numeric literal as-is
    return "'" + val.replace("'", "''") + "'"  # quoted text, escaped


def rows_to_sql(table: str, csv_path: Path) -> str:
    with csv_path.open(newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        cols = reader.fieldnames or []
        col_sql = ", ".join(f'"{c}"' for c in cols)
        lines: list[str] = []
        for row in reader:
            vals = ", ".join(_lit(table, c, row.get(c, "")) for c in cols)
            lines.append(f"insert into {table} ({col_sql}) values ({vals}) on conflict do nothing;")
    return "\n".join(lines)


def main() -> None:
    csv_dir = Path(sys.argv[1])
    header = "-- ===== semantic taxonomy seed (A1) — généré par gen_semantic_seed.py ====="
    out: list[str] = [header]
    for table in TABLES:
        csv_path = csv_dir / f"{table}.csv"
        if not csv_path.exists():
            print(f"-- WARNING: {csv_path} absent, table {table} non seedée", file=sys.stderr)
            continue
        out.append(f"-- {table}")
        out.append(rows_to_sql(table, csv_path))
    print("\n".join(out))


if __name__ == "__main__":
    main()
