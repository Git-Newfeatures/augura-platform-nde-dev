"""
Generate ground_truth_report.xlsx from ground_truth.json.

Produces 4 sheets matching the Augura DQ engine XLSX export format:
  1. Summary   — overall score, dimension breakdown, gate status
  2. Findings  — one row per finding, all scopes
  3. Attribute Cards — one row per column across all tables
  4. Provenance — same as Findings but sorted by severity then check_id

Usage:
  python3 generate_xlsx.py
"""

import json
import os
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
JSON_PATH  = os.path.join(SCRIPT_DIR, "ground_truth.json")
XLSX_PATH  = os.path.join(SCRIPT_DIR, "ground_truth_report.xlsx")

# ── colour palette ─────────────────────────────────────────────────────────────
C = {
    "header_bg":   "2D3748",  # dark slate
    "header_fg":   "FFFFFF",
    "hard_bg":     "FED7D7",  # red-100
    "hard_fg":     "C53030",
    "soft_bg":     "FEEBC8",  # orange-100
    "soft_fg":     "C05621",
    "info_bg":     "BEE3F8",  # blue-100
    "info_fg":     "2B6CB0",
    "score_green": "C6F6D5",  # green-100
    "score_amber": "FEFCBF",  # yellow-100
    "score_red":   "FED7D7",  # red-100
    "alt_row":     "F7FAFC",  # very light blue-grey
    "white":       "FFFFFF",
    "border":      "CBD5E0",
}

def hex_fill(hex_color):
    return PatternFill(fill_type="solid", fgColor=hex_color)

def header_font(bold=True):
    return Font(bold=bold, color=C["header_fg"])

def thin_border():
    s = Side(style="thin", color=C["border"])
    return Border(left=s, right=s, top=s, bottom=s)

def severity_fill(severity):
    if severity == "hard": return hex_fill(C["hard_bg"])
    if severity == "soft": return hex_fill(C["soft_bg"])
    return hex_fill(C["info_bg"])

def severity_font(severity):
    if severity == "hard": return Font(color=C["hard_fg"], bold=True)
    if severity == "soft": return Font(color=C["soft_fg"])
    return Font(color=C["info_fg"])

def score_fill(score):
    if score is None: return hex_fill(C["white"])
    if score >= 0.80: return hex_fill(C["score_green"])
    if score >= 0.60: return hex_fill(C["score_amber"])
    return hex_fill(C["score_red"])

def write_header_row(ws, row_num, columns, widths=None):
    for col_idx, col_name in enumerate(columns, 1):
        cell = ws.cell(row=row_num, column=col_idx, value=col_name)
        cell.fill   = hex_fill(C["header_bg"])
        cell.font   = header_font()
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        cell.border = thin_border()
        if widths and col_idx <= len(widths):
            ws.column_dimensions[get_column_letter(col_idx)].width = widths[col_idx - 1]

def style_data_row(ws, row_num, num_cols, alt=False, fill=None, font=None):
    bg = fill if fill else (hex_fill(C["alt_row"]) if alt else hex_fill(C["white"]))
    for col_idx in range(1, num_cols + 1):
        cell = ws.cell(row=row_num, column=col_idx)
        cell.fill   = bg
        if font: cell.font = font
        cell.border = thin_border()
        cell.alignment = Alignment(vertical="center", wrap_text=True)

# ── load JSON ──────────────────────────────────────────────────────────────────
with open(JSON_PATH) as f:
    gt = json.load(f)

meta    = gt["meta"]
scoring = gt["scoring"]
tables  = gt["tables"]
findings = gt["findings"]

wb = Workbook()
wb.remove(wb.active)  # remove default sheet

# ══════════════════════════════════════════════════════════════════════════════
# Sheet 1 — SUMMARY
# ══════════════════════════════════════════════════════════════════════════════
ws_sum = wb.create_sheet("Summary")
ws_sum.sheet_view.showGridLines = False

# Title block
ws_sum.merge_cells("A1:G1")
title_cell = ws_sum["A1"]
title_cell.value = "DQ Ground Truth Report — Degraded Dataset"
title_cell.font  = Font(bold=True, size=14, color=C["header_fg"])
title_cell.fill  = hex_fill(C["header_bg"])
title_cell.alignment = Alignment(horizontal="center", vertical="center")
ws_sum.row_dimensions[1].height = 28

meta_rows = [
    ("Bundle ID",      meta["bundle_id"]),
    ("Dataset",        meta["dataset_version"]),
    ("Created",        meta["created_at"]),
    ("Policy version", meta["policy_version"]),
    ("Score profile",  meta["score_profile"]),
    ("Score tolerance",f"±{meta['score_tolerance']}"),
]
for i, (k, v) in enumerate(meta_rows, 2):
    ws_sum.cell(row=i, column=1, value=k).font = Font(bold=True)
    ws_sum.cell(row=i, column=2, value=v)

# Overall score
overall_row = len(meta_rows) + 3
ws_sum.merge_cells(f"A{overall_row}:G{overall_row}")
overall_cell = ws_sum.cell(row=overall_row, column=1)
overall_score = scoring["overall_score"]
overall_cell.value = f"Overall DQ Score: {overall_score:.2f}  |  Gate: {scoring['score_gate']}  |  Hard findings: {scoring['hard_findings_total']}  |  Requires resolution: {scoring['requires_resolution']}"
overall_cell.font  = Font(bold=True, size=12)
overall_cell.fill  = score_fill(overall_score)
overall_cell.alignment = Alignment(horizontal="center", vertical="center")
ws_sum.row_dimensions[overall_row].height = 24

# Dimension table
dim_row = overall_row + 2
dim_headers = ["Dimension", "Score", "Weight", "Weighted Score", "Hard Findings", "Soft Findings", "Info Findings", "Deduction Breakdown"]
write_header_row(ws_sum, dim_row, dim_headers, widths=[18, 10, 10, 14, 14, 14, 14, 55])

DIM_ORDER = ["completeness", "validity", "consistency", "coherence", "labelling"]
for i, dim_name in enumerate(DIM_ORDER):
    dim = scoring["dimensions"][dim_name]
    r = dim_row + 1 + i
    vals = [
        dim_name.capitalize(),
        f"{dim['score']:.2f}",
        f"{dim['weight']*100:.0f}%",
        f"{dim['score'] * dim['weight']:.4f}",
        dim["finding_counts"]["hard"],
        dim["finding_counts"]["soft"],
        dim["finding_counts"]["info"],
        dim.get("deduction_breakdown", ""),
    ]
    for col_idx, v in enumerate(vals, 1):
        cell = ws_sum.cell(row=r, column=col_idx, value=v)
        cell.fill   = score_fill(dim["score"]) if col_idx == 2 else (hex_fill(C["alt_row"]) if i % 2 else hex_fill(C["white"]))
        cell.border = thin_border()
        cell.alignment = Alignment(vertical="center", wrap_text=True)
        if col_idx == 2: cell.font = Font(bold=True)

# Totals row
r = dim_row + 1 + len(DIM_ORDER)
ws_sum.cell(row=r, column=1, value="TOTAL").font = Font(bold=True)
ws_sum.cell(row=r, column=2, value=f"{scoring['overall_score']:.2f}").font = Font(bold=True)
ws_sum.cell(row=r, column=5, value=scoring["hard_findings_total"]).font = Font(bold=True)
soft_total = sum(scoring["dimensions"][d]["finding_counts"]["soft"] for d in DIM_ORDER)
info_total = sum(scoring["dimensions"][d]["finding_counts"]["info"] for d in DIM_ORDER)
ws_sum.cell(row=r, column=6, value=soft_total).font = Font(bold=True)
ws_sum.cell(row=r, column=7, value=info_total).font = Font(bold=True)
for col_idx in range(1, 9):
    cell = ws_sum.cell(row=r, column=col_idx)
    cell.fill   = score_fill(scoring["overall_score"])
    cell.border = thin_border()

# Tables-in-scope note
note_row = r + 2
ws_sum.cell(row=note_row, column=1, value="Tables in scope:").font = Font(bold=True)
ws_sum.cell(row=note_row, column=2, value=", ".join(meta["tables_in_scope"]))

ws_sum.column_dimensions["A"].width = 18
ws_sum.freeze_panes = f"A{dim_row+1}"

# ══════════════════════════════════════════════════════════════════════════════
# Sheet 2 — FINDINGS
# ══════════════════════════════════════════════════════════════════════════════
ws_fin = wb.create_sheet("Findings")
ws_fin.sheet_view.showGridLines = False

fin_headers = ["Finding ID", "Check ID", "Category", "Scope", "Severity", "Table", "Column(s)", "Message", "Key Evidence", "Resolution"]
fin_widths   = [14, 16, 14, 14, 10, 28, 32, 60, 55, 18]
write_header_row(ws_fin, 1, fin_headers, fin_widths)
ws_fin.row_dimensions[1].height = 22
ws_fin.freeze_panes = "A2"

# Sort: hard first, then soft, then info; within severity by check_id
severity_order = {"hard": 0, "soft": 1, "info": 2}
sorted_findings = sorted(findings, key=lambda f: (severity_order[f["severity"]], f["check_id"]))

for i, finding in enumerate(sorted_findings, 2):
    cols_val = finding.get("column") or (", ".join(finding.get("columns", [])) if finding.get("columns") else "")
    ev = finding.get("evidence", {})
    # Build compact key-evidence string
    key_ev_parts = []
    if "sample_offenders" in ev and ev["sample_offenders"]:
        s = ev["sample_offenders"][0]
        if "value" in s:     key_ev_parts.append(f"value={s['value']}")
        if "raw_value" in s: key_ev_parts.append(f"raw='{s['raw_value']}'")
        if "row_id" in s:    key_ev_parts.append(f"row={s['row_id']}")
        if "patient_id" in s:key_ev_parts.append(f"patient={s['patient_id']}")
    if "missing_rate" in ev:   key_ev_parts.append(f"missing_rate={ev['missing_rate']:.1%}")
    if "outlier_count" in ev:  key_ev_parts.append(f"outliers={ev['outlier_count']}")
    if "sentinel_values_found" in ev: key_ev_parts.append(f"sentinels={ev['sentinel_values_found']}")
    if "orphan_values" in ev:  key_ev_parts.append(f"orphan_fk={ev['orphan_values']}")
    if "entity_pair" in ev:    key_ev_parts.append(f"pair={ev['entity_pair']}")
    if "entity_id" in ev:      key_ev_parts.append(f"entity={ev['entity_id']}")
    key_ev = " | ".join(key_ev_parts) if key_ev_parts else ""

    vals = [
        finding["id"],
        finding["check_id"],
        finding["category"],
        finding["scope"],
        finding["severity"],
        finding.get("table") or "dataset",
        cols_val,
        finding["message"],
        key_ev,
        "",  # resolution — empty for ground truth
    ]
    alt = (i % 2 == 0)
    sev_fill = severity_fill(finding["severity"])
    sev_font = severity_font(finding["severity"])

    for col_idx, v in enumerate(vals, 1):
        cell = ws_fin.cell(row=i, column=col_idx, value=v)
        if col_idx in (1, 5):
            cell.fill = sev_fill
            cell.font = sev_font
        else:
            cell.fill = hex_fill(C["alt_row"]) if alt else hex_fill(C["white"])
        cell.border    = thin_border()
        cell.alignment = Alignment(vertical="center", wrap_text=True)
    ws_fin.row_dimensions[i].height = 42

# ══════════════════════════════════════════════════════════════════════════════
# Sheet 3 — ATTRIBUTE CARDS
# ══════════════════════════════════════════════════════════════════════════════
ws_attr = wb.create_sheet("Attribute Cards")
ws_attr.sheet_view.showGridLines = False

attr_headers = ["Table", "Column", "Role", "Type", "Missing Rate", "Sentinel / Non-Numeric", "Plausible Range", "Outlier Count", "Invalid Coded Values", "Finding Count", "Finding IDs"]
attr_widths   = [28, 28, 20, 14, 14, 22, 20, 14, 24, 14, 40]
write_header_row(ws_attr, 1, attr_headers, attr_widths)
ws_attr.row_dimensions[1].height = 22
ws_attr.freeze_panes = "A2"

attr_rows = []
for table in tables:
    tl = table["table_label"]
    for card in table.get("attribute_cards", []):
        attr_rows.append({
            "table":          tl,
            "column":         card["column"],
            "role":           card.get("role", ""),
            "type":           card.get("type", ""),
            "missing_rate":   card.get("missing_rate", 0.0),
            "sentinel":       str(card.get("sentinel_values", card.get("sentinel_count", ""))) if (card.get("sentinel_count") or card.get("non_numeric_rows")) else "",
            "plausible_range":str(card["plausible_range"]) if "plausible_range" in card else "",
            "outlier_count":  card.get("outlier_count", ""),
            "invalid_coded":  str(card.get("invalid_sample", "")) if card.get("invalid_count") else "",
            "finding_count":  card.get("finding_count", 0),
            "finding_ids":    ", ".join(card.get("findings", [])),
        })

for i, row in enumerate(attr_rows, 2):
    alt = (i % 2 == 0)
    vals = [
        row["table"], row["column"], row["role"], row["type"],
        f"{row['missing_rate']:.1%}" if row["missing_rate"] else "0.0%",
        row["sentinel"],
        row["plausible_range"],
        row["outlier_count"],
        row["invalid_coded"],
        row["finding_count"],
        row["finding_ids"],
    ]
    has_finding = row["finding_count"] > 0
    for col_idx, v in enumerate(vals, 1):
        cell = ws_attr.cell(row=i, column=col_idx, value=v)
        if has_finding and col_idx == 2:
            cell.font = Font(bold=True)
        cell.fill   = hex_fill(C["soft_bg"]) if has_finding else (hex_fill(C["alt_row"]) if alt else hex_fill(C["white"]))
        cell.border = thin_border()
        cell.alignment = Alignment(vertical="center", wrap_text=True)
    ws_attr.row_dimensions[i].height = 18

# ══════════════════════════════════════════════════════════════════════════════
# Sheet 4 — PROVENANCE
# ══════════════════════════════════════════════════════════════════════════════
ws_prov = wb.create_sheet("Provenance")
ws_prov.sheet_view.showGridLines = False

prov_headers = ["#", "Finding ID", "Check ID", "Category", "Scope", "Severity", "Table", "Column(s)", "Message", "Evidence (summary)", "Resolution"]
prov_widths   = [6, 14, 16, 14, 14, 10, 28, 32, 60, 55, 18]
write_header_row(ws_prov, 1, prov_headers, prov_widths)
ws_prov.row_dimensions[1].height = 22
ws_prov.freeze_panes = "A2"

for i, finding in enumerate(sorted_findings, 2):
    cols_val = finding.get("column") or (", ".join(finding.get("columns", [])) if finding.get("columns") else "")
    ev = finding.get("evidence", {})
    ev_summary = json.dumps({k: v for k, v in ev.items() if k != "sample_offenders"}, ensure_ascii=False)
    if "sample_offenders" in ev and ev["sample_offenders"]:
        ev_summary += f" | first_offender: {json.dumps(ev['sample_offenders'][0], ensure_ascii=False)}"

    vals = [
        i - 1,
        finding["id"],
        finding["check_id"],
        finding["category"],
        finding["scope"],
        finding["severity"],
        finding.get("table") or "dataset",
        cols_val,
        finding["message"],
        ev_summary[:300] + ("…" if len(ev_summary) > 300 else ""),
        "",
    ]
    alt = (i % 2 == 0)
    sev_fill = severity_fill(finding["severity"])
    sev_font = severity_font(finding["severity"])

    for col_idx, v in enumerate(vals, 1):
        cell = ws_prov.cell(row=i, column=col_idx, value=v)
        if col_idx in (2, 6):
            cell.fill = sev_fill
            cell.font = sev_font
        else:
            cell.fill = hex_fill(C["alt_row"]) if alt else hex_fill(C["white"])
        cell.border    = thin_border()
        cell.alignment = Alignment(vertical="center", wrap_text=True)
    ws_prov.row_dimensions[i].height = 42

# ── save ───────────────────────────────────────────────────────────────────────
wb.save(XLSX_PATH)
print(f"Saved: {XLSX_PATH}")
print(f"  Sheet 'Summary':        score={scoring['overall_score']:.2f}, gate={scoring['score_gate']}")
print(f"  Sheet 'Findings':       {len(sorted_findings)} findings ({scoring['hard_findings_total']} hard)")
print(f"  Sheet 'Attribute Cards':{len(attr_rows)} columns across {len(tables)} tables")
print(f"  Sheet 'Provenance':     {len(sorted_findings)} entries (same as Findings, sorted by severity)")
