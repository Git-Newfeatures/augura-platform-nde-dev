"""Generate the semantic-taxonomy seed SQL from the MVP CSVs.

Usage: python scripts/gen_semantic_seed.py <csv_dir> > seed_fragment.sql
Deterministic: quoted columns, escaped values, empties → NULL, bool/num unquoted.
The produced fragment is meant to be pasted into supabase/seed.sql.
"""

from __future__ import annotations

import csv
import sys
from pathlib import Path

# Boolean and numeric columns per table (the rest = text). Keep aligned with the DDL.
BOOL_COLS: dict[str, set[str]] = {
    "taxonomy_concepts": {"active"},
    "table_archetypes": {"is_surrogate", "active"},
    "taxonomy_measurement_units": {"is_preferred"},
    "unit_conversions": {"bidirectional"},
    "ontology_relations": {"active"},
    "ontology_relation_qualifiers": {"is_hard_constraint"},
}
NUM_COLS: dict[str, set[str]] = {
    "taxonomy_concepts": {"layer", "value_min", "value_max"},
    "table_archetypes": {"semantic_score"},
    "unit_conversions": {"scale_factor", "offset", "precision"},
}
# Insertion order (FK: concepts first, then causal_predicates before
# ontology_relations, then evidence/qualifiers).
TABLES = [
    "taxonomy_concepts",
    "taxonomy_synonyms",
    "taxonomy_dq_valid_values",
    "taxonomy_measurement_units",
    "unit_conversions",
    "table_archetypes",
    "dq_constraints",
    # Ontology/causal (B1)
    "taxonomy_standard_codes",
    "taxonomy_therapeutic_areas",
    "taxonomy_relationships",
    "causal_predicates",
    "dq_predicates",
    "ontology_relations",
    "ontology_relation_evidence",
    "ontology_relation_qualifiers",
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
    header = "-- ===== semantic taxonomy + ontology seed (A1+B1) — gen_semantic_seed.py ====="
    out: list[str] = [header]
    for table in TABLES:
        csv_path = csv_dir / f"{table}.csv"
        if not csv_path.exists():
            print(f"-- WARNING: {csv_path} missing, table {table} not seeded", file=sys.stderr)
            continue
        out.append(f"-- {table}")
        out.append(rows_to_sql(table, csv_path))
    print("\n".join(out))


if __name__ == "__main__":
    main()
