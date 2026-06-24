"""The variable-check prompt must NOT contain raw dataset cell values (PHI egress).

Only column statistics (kind/null%/range/n_distinct) may cross the LLM boundary.
"""

from augura_api.modules.agents.tools import build_varcheck_user_message


def test_varcheck_prompt_excludes_raw_cell_samples() -> None:
    sheets = [
        {
            "name": "cohort",
            "headers": ["patient_email", "hba1c_12m"],
            "sample": [["alice@example.com", 7.1], ["bob@example.com", 6.4]],
            "column_stats": [
                {
                    "column": "patient_email",
                    "value_kind": "string",
                    "null_pct": 0.0,
                    "n_distinct": 2,
                },
                {
                    "column": "hba1c_12m",
                    "value_kind": "numeric",
                    "null_pct": 0.0,
                    "min": 6.4,
                    "max": 7.1,
                },
            ],
        }
    ]
    msg = build_varcheck_user_message(product_description="x", sheets=sheets)

    # No raw cell values leak into the prompt.
    assert "alice@example.com" not in msg
    assert "bob@example.com" not in msg
    assert "sample:" not in msg
    # Statistics the classifier needs are still present.
    assert "hba1c_12m" in msg
    assert "kind: numeric" in msg
    assert "range: 6.4" in msg
