"""Snapshot loaders: CSV, TSV, and JSON Lines to a uniform in-memory table.

Every cell becomes ``Optional[str]``: JSONL scalars are normalized to
canonical strings (bool -> "true"/"false", numbers via their shortest
round-trip repr, nested values as compact sorted JSON) and JSON ``null``
becomes ``None``. Null-token detection happens later, at profiling time,
so loaders stay format-only.
"""

from __future__ import annotations

import csv
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

from .errors import InputError

#: File extensions accepted as raw snapshot data.
TABLE_SUFFIXES = {".csv": "csv", ".tsv": "tsv", ".tab": "tsv", ".jsonl": "jsonl", ".ndjson": "jsonl"}


@dataclass
class Dataset:
    """A loaded snapshot: ordered columns of optional-string cells."""

    source: str
    format: str
    columns: List[str]
    rows: int
    values: Dict[str, List[Optional[str]]] = field(default_factory=dict)


def load_table(
    path: "str | Path",
    delimiter: Optional[str] = None,
) -> Dataset:
    """Load a snapshot file by extension (.csv, .tsv/.tab, .jsonl/.ndjson)."""
    path = Path(path)
    if not path.is_file():
        raise InputError(f"snapshot not found: {path}")
    fmt = TABLE_SUFFIXES.get(path.suffix.lower())
    if fmt is None:
        supported = ", ".join(sorted(TABLE_SUFFIXES))
        raise InputError(
            f"unsupported snapshot extension '{path.suffix}' for {path} (supported: {supported})"
        )
    if fmt == "jsonl":
        return _load_jsonl(path)
    if delimiter is None:
        delimiter = "\t" if fmt == "tsv" else ","
    return _load_delimited(path, fmt, delimiter)


def _load_delimited(path: Path, fmt: str, delimiter: str) -> Dataset:
    """Load a delimited file with a mandatory header row.

    Short rows are padded with nulls (trailing empty cells are routinely
    dropped by exporters); rows *longer* than the header are an error —
    that always means a quoting or delimiter problem worth surfacing.
    """
    # utf-8-sig transparently eats a BOM, which spreadsheet exports love to add.
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.reader(handle, delimiter=delimiter)
        try:
            header = next(reader)
        except StopIteration:
            raise InputError(f"{path}: file is empty (a header row is required)") from None
        header = [name.strip() for name in header]
        if any(not name for name in header):
            raise InputError(f"{path}: header contains an empty column name")
        seen = set()
        for name in header:
            if name in seen:
                raise InputError(f"{path}: duplicate column name '{name}' in header")
            seen.add(name)
        values: Dict[str, List[Optional[str]]] = {name: [] for name in header}
        rows = 0
        for line_no, row in enumerate(reader, start=2):
            if not row:
                continue  # skip completely blank lines
            if len(row) > len(header):
                raise InputError(
                    f"{path}: row {line_no} has {len(row)} fields, header has {len(header)} "
                    "(check quoting or pass --delimiter)"
                )
            rows += 1
            for index, name in enumerate(header):
                values[name].append(row[index] if index < len(row) else None)
        return Dataset(source=str(path), format=fmt, columns=header, rows=rows, values=values)


def _load_jsonl(path: Path) -> Dataset:
    """Load JSON Lines; columns are the union of keys in first-seen order."""
    columns: List[str] = []
    seen_columns: set = set()
    records: List[Dict[str, Optional[str]]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line_no, line in enumerate(handle, start=1):
            text = line.strip()
            if not text:
                continue
            try:
                obj = json.loads(text)
            except json.JSONDecodeError as exc:
                raise InputError(f"{path}: line {line_no} is not valid JSON ({exc.msg})") from None
            if not isinstance(obj, dict):
                raise InputError(
                    f"{path}: line {line_no} is a JSON {type(obj).__name__}, expected an object"
                )
            record: Dict[str, Optional[str]] = {}
            for key, value in obj.items():
                if key not in seen_columns:
                    seen_columns.add(key)
                    columns.append(key)
                record[key] = _normalize_json_value(value)
            records.append(record)
    values: Dict[str, List[Optional[str]]] = {name: [] for name in columns}
    for record in records:
        for name in columns:
            values[name].append(record.get(name))
    return Dataset(source=str(path), format="jsonl", columns=columns, rows=len(records), values=values)


def _normalize_json_value(value: object) -> Optional[str]:
    """Canonical string form of a JSONL cell (None for JSON null)."""
    if value is None:
        return None
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        return repr(value)
    if isinstance(value, str):
        return value
    # Nested arrays/objects become one canonical categorical token.
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
