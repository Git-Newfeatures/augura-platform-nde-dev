"""Test du générateur de seed sémantique (CSV → SQL)."""

import csv
from pathlib import Path

from scripts.gen_semantic_seed import rows_to_sql


def _write_csv(p: Path, header: list[str], rows: list[list[str]]) -> None:
    with p.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(header)
        w.writerows(rows)


def test_rows_to_sql_handles_nulls_quotes_bools_nums(tmp_path: Path) -> None:
    csv_path = tmp_path / "table_archetypes.csv"
    _write_csv(
        csv_path,
        ["archetype_id", "archetype_name", "key_selectors", "semantic_score",
         "is_surrogate", "description_template", "review_status", "version", "active"],
        [["a1", "O'Brien grain", "person|time", "0.8", "false", "", "approved", "v1", "true"]],
    )
    sql = rows_to_sql("table_archetypes", csv_path)
    assert "insert into table_archetypes" in sql
    assert "on conflict do nothing" in sql
    assert "'O''Brien grain'" in sql          # single-quote escaped
    assert "0.8" in sql and ", true" in sql    # numeric + boolean unquoted
    assert "false" in sql
    assert "NULL" in sql                        # empty description_template → NULL
