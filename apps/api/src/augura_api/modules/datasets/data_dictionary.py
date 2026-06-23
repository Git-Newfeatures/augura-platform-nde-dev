"""Parse a data dictionary into a structured data model.

A data dictionary documents the variables of a dataset (name, label, type, description,
allowed values). Two paths:

- **structured** — a CSV/XLSX whose header row looks like a dictionary (a name-ish column
  plus at least one descriptive column: label / description / type / values). Parsed
  deterministically, no LLM.
- **free-form** — anything else (prose ``.txt``/``.md``, or a CSV/XLSX that does not match the
  dictionary shape). An LLM extracts the entries; this requires an Anthropic key
  (``get_anthropic_client`` raises 503 otherwise).
"""

from __future__ import annotations

import re

from anthropic.types import ToolParam
from pydantic import BaseModel

from augura_api.core.config import Settings
from augura_api.core.errors import (
    BadRequestError,
    PayloadTooLargeError,
    UnsupportedMediaTypeError,
)
from augura_api.core.llm.runtime import get_anthropic_client, run_structured_agent
from augura_api.modules.datasets import schemas
from augura_api.modules.datasets.parsing import MAX_UPLOAD_BYTES, Sheet, parse_upload

# Header synonyms used to recognize a dictionary-shaped table (normalized: alnum, lowercase).
_NAME_KEYS = {
    "name", "variable", "field", "column", "var", "varname", "variablename",
    "columnname", "fieldname",
}  # fmt: skip
_LABEL_KEYS = {"label", "title", "display", "displayname", "shortlabel"}
_DESC_KEYS = {
    "description", "desc", "definition", "notes", "note", "comment", "comments", "meaning",
}  # fmt: skip
_TYPE_KEYS = {"type", "datatype", "valuetype", "format", "kind"}
_VALUES_KEYS = {
    "values", "allowedvalues", "categories", "codes", "levels", "validvalues",
    "valuelabels", "range",
}  # fmt: skip

_MAX_TEXT = 20_000  # cap the free-form payload sent to the LLM

_SYSTEM = (
    "You are a clinical data engineer. Extract every variable described in the data "
    "dictionary into the extract_data_dictionary tool. Keep labels concise. value_type "
    "must be one of: numeric, categorical, binary, date, text. Only fill allowed_values "
    "when the dictionary explicitly lists the permitted values/codes."
)

_DICT_TOOL: ToolParam = {
    "name": "extract_data_dictionary",
    "description": "Extract every variable described in a clinical data dictionary.",
    "input_schema": {
        "type": "object",
        "required": ["entries"],
        "properties": {
            "entries": {
                "type": "array",
                "items": {
                    "type": "object",
                    "required": ["name"],
                    "properties": {
                        "name": {"type": "string", "description": "variable / column identifier"},
                        "label": {"type": "string", "description": "human-readable label"},
                        "value_type": {
                            "type": "string",
                            "description": "numeric | categorical | binary | date | text",
                        },
                        "description": {"type": "string"},
                        "allowed_values": {"type": "array", "items": {"type": "string"}},
                    },
                },
            }
        },
    },
}


class _DictLLMOut(BaseModel):
    entries: list[schemas.DataDictionaryEntry] = []


def _norm(header: str) -> str:
    return "".join(ch for ch in header.lower() if ch.isalnum())


def _find(headers: list[str], keys: set[str]) -> int | None:
    for i, h in enumerate(headers):
        if _norm(h) in keys:
            return i
    return None


def _cell(row: list[str], idx: int | None) -> str:
    return row[idx].strip() if idx is not None and 0 <= idx < len(row) else ""


def _split_values(raw: str) -> list[str]:
    out = [p.strip() for p in re.split(r"[;|\n]+", raw or "")]
    return [p for p in out if p]


def _looks_structured(sheet: Sheet) -> bool:
    headers = sheet.headers
    return _find(headers, _NAME_KEYS) is not None and any(
        _find(headers, keys) is not None
        for keys in (_LABEL_KEYS, _DESC_KEYS, _TYPE_KEYS, _VALUES_KEYS)
    )


def _parse_structured(sheet: Sheet) -> list[schemas.DataDictionaryEntry]:
    headers = sheet.headers
    i_name = _find(headers, _NAME_KEYS)
    i_label = _find(headers, _LABEL_KEYS)
    i_desc = _find(headers, _DESC_KEYS)
    i_type = _find(headers, _TYPE_KEYS)
    i_values = _find(headers, _VALUES_KEYS)
    entries: list[schemas.DataDictionaryEntry] = []
    for row in sheet.rows:
        name = _cell(row, i_name)
        if not name:
            continue
        entries.append(
            schemas.DataDictionaryEntry(
                name=name,
                label=_cell(row, i_label) or None,
                value_type=_cell(row, i_type) or None,
                description=_cell(row, i_desc) or None,
                allowed_values=_split_values(_cell(row, i_values)),
            )
        )
    return entries


def _decode(data: bytes) -> str:
    for enc in ("utf-8-sig", "utf-8", "latin-1"):
        try:
            return data.decode(enc)
        except UnicodeDecodeError:
            continue
    raise BadRequestError("unreadable file (unsupported encoding)")


def _sheets_to_text(sheets: list[Sheet]) -> str:
    lines: list[str] = []
    for sheet in sheets:
        lines.append("\t".join(sheet.headers))
        lines.extend("\t".join(row) for row in sheet.rows)
    return "\n".join(lines)


async def parse_data_dictionary(
    settings: Settings, filename: str, data: bytes
) -> schemas.DataDictionaryResult:
    """Parse a data-dictionary file. Tries the deterministic structured path first; falls
    back to the LLM for free-form input (which needs an Anthropic key)."""
    ext = filename.lower().rsplit(".", 1)[-1] if "." in filename else ""
    if ext in ("csv", "xlsx"):
        sheets = parse_upload(filename, data)  # raises 413/415/400
        for sheet in sheets:
            if _looks_structured(sheet):
                entries = _parse_structured(sheet)
                if entries:
                    return schemas.DataDictionaryResult(source_kind="structured", entries=entries)
        text = _sheets_to_text(sheets)
    elif ext in ("txt", "md", "markdown", "text"):
        if len(data) > MAX_UPLOAD_BYTES:
            raise PayloadTooLargeError("file too large", max_bytes=MAX_UPLOAD_BYTES, size=len(data))
        text = _decode(data)
    else:
        raise UnsupportedMediaTypeError(
            "unsupported data dictionary format (use .csv, .xlsx, .txt or .md)", ext=ext
        )

    if not text.strip():
        raise BadRequestError("empty data dictionary")

    warnings: list[str] = []
    if len(text) > _MAX_TEXT:
        warnings.append(f"dictionary truncated to {_MAX_TEXT} characters for parsing")
        text = text[:_MAX_TEXT]

    client = get_anthropic_client(settings)  # raises 503 if the key is missing
    result = await run_structured_agent(
        client,
        model=settings.agent_model_fast,
        system=_SYSTEM,
        tool=_DICT_TOOL,
        messages=[
            {
                "role": "user",
                "content": (
                    "Extract every variable described in the following data dictionary.\n\n"
                    f"DATA DICTIONARY:\n{text}"
                ),
            }
        ],
        output_model=_DictLLMOut,
        max_tokens=4000,
    )
    entries = [e for e in result.output.entries if e.name.strip()]
    warnings.append(f"parsed by {result.model}")
    return schemas.DataDictionaryResult(
        source_kind="free_form_llm", entries=entries, warnings=warnings
    )
