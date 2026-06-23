"""Combine several uploaded files of one dataset into a logical table.

Files share columns ("se suivent"). Per sheet name we build the union of headers
(first-seen order, new headers appended) and concatenate rows aligned by header
name — blanks where a file lacks a column. CSV files have a single sheet 'data',
so the common case is a plain union + append.
"""

from __future__ import annotations

from dataclasses import dataclass

from augura_api.modules.datasets.parsing import Sheet


@dataclass(frozen=True)
class CombinedSheet:
    name: str
    headers: list[str]
    rows: list[list[str]]


def file_headers(sheets: list[Sheet]) -> list[str]:
    """Distinct headers of one file, across its sheets, in first-seen order."""
    out: list[str] = []
    for sheet in sheets:
        for h in sheet.headers:
            if h not in out:
                out.append(h)
    return out


def combine_sheets(files: list[tuple[str, list[Sheet]]]) -> list[CombinedSheet]:
    order: list[str] = []
    headers: dict[str, list[str]] = {}
    rows: dict[str, list[list[str]]] = {}
    for _filename, sheets in files:
        for sheet in sheets:
            if sheet.name not in headers:
                order.append(sheet.name)
                headers[sheet.name] = []
                rows[sheet.name] = []
            for h in sheet.headers:
                if h not in headers[sheet.name]:
                    headers[sheet.name].append(h)
    for _filename, sheets in files:
        for sheet in sheets:
            hdr = headers[sheet.name]
            pos = {h: i for i, h in enumerate(sheet.headers)}
            for row in sheet.rows:
                rows[sheet.name].append(
                    [row[pos[h]] if h in pos and pos[h] < len(row) else "" for h in hdr]
                )
    return [CombinedSheet(name=n, headers=headers[n], rows=rows[n]) for n in order]


def file_warnings(established: list[str], new_headers: list[str], filename: str) -> list[str]:
    """Human-readable diff of an added file's headers vs the established union."""
    added = [h for h in new_headers if h not in established]
    missing = [h for h in established if h not in new_headers]
    out: list[str] = []
    if added:
        out.append(f"{filename} added column(s): {', '.join(added)}")
    if missing:
        out.append(f"{filename} missing column(s): {', '.join(missing)} — filled blank")
    return out
