"""Null detection and column type inference.

colshift sees every cell as an optional string (loaders normalize JSONL
scalars to canonical strings). This module decides which cells count as
null and whether a column is numeric, categorical, or entirely empty.
"""

from __future__ import annotations

import math
from typing import FrozenSet, List, Optional, Sequence, Tuple

#: Tokens treated as null by default (exact match after stripping outer
#: whitespace). Whitespace-only cells are always null, whatever the set.
DEFAULT_NULL_TOKENS: FrozenSet[str] = frozenset(
    {
        "",
        "null",
        "NULL",
        "Null",
        "None",
        "NONE",
        "none",
        "NaN",
        "nan",
        "NAN",
        "NA",
        "N/A",
        "n/a",
        "#N/A",
    }
)

#: Column kinds produced by :func:`infer_kind`.
KIND_NUMERIC = "numeric"
KIND_CATEGORICAL = "categorical"
KIND_EMPTY = "empty"


def is_null(raw: Optional[str], null_tokens: FrozenSet[str] = DEFAULT_NULL_TOKENS) -> bool:
    """Return True when a raw cell should be treated as missing."""
    if raw is None:
        return True
    stripped = raw.strip()
    return stripped == "" or stripped in null_tokens


def parse_number(raw: str) -> Optional[float]:
    """Parse a cell as a finite number, or return None.

    Stricter than ``float()`` on purpose: Python accepts ``"1_000"``,
    ``"inf"`` and ``"nan"``, none of which should silently make a CSV
    column numeric.
    """
    text = raw.strip()
    if not text or "_" in text:
        return None
    try:
        value = float(text)
    except ValueError:
        return None
    if math.isnan(value) or math.isinf(value):
        return None
    return value


def split_nulls(
    raws: Sequence[Optional[str]],
    null_tokens: FrozenSet[str] = DEFAULT_NULL_TOKENS,
) -> Tuple[List[str], int]:
    """Split raw cells into (non-null values, null count)."""
    values: List[str] = []
    nulls = 0
    for raw in raws:
        if is_null(raw, null_tokens):
            nulls += 1
        else:
            values.append(raw)  # type: ignore[arg-type]  # is_null rejects None
    return values, nulls


def infer_kind(non_null_values: Sequence[str]) -> str:
    """Classify a column from its non-null cells.

    A column is numeric only when *every* non-null cell parses as a finite
    number — one stray string means downstream consumers cannot treat the
    column as numeric either, so neither do we.
    """
    if not non_null_values:
        return KIND_EMPTY
    for value in non_null_values:
        if parse_number(value) is None:
            return KIND_CATEGORICAL
    return KIND_NUMERIC


def numeric_values(
    raws: Sequence[Optional[str]],
    null_tokens: FrozenSet[str] = DEFAULT_NULL_TOKENS,
) -> List[float]:
    """Parsed non-null numeric values of a column known to be numeric."""
    values, _ = split_nulls(raws, null_tokens)
    parsed: List[float] = []
    for value in values:
        number = parse_number(value)
        if number is not None:
            parsed.append(number)
    return parsed
