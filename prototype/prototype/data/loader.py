"""CSV loading: parse CSV data into Relations with type inference."""

from __future__ import annotations

import csv
from decimal import Decimal, InvalidOperation
from typing import TextIO

from prototype.model.relation import Relation
from prototype.model.types import Tuple_, Value


def load_csv(source: TextIO, name: str) -> Relation:
    """Read CSV data from a text stream and return a Relation.

    The first row is treated as headers (attribute names).
    Type inference is applied per column: int > Decimal > bool > str.
    Empty strings remain as empty strings (no missing-value decomposition yet).
    """
    reader = csv.reader(source)
    try:
        headers = next(reader)
    except StopIteration:
        return Relation(frozenset(), attributes=frozenset())

    headers = [h.strip() for h in headers]

    rows: list[dict[str, str]] = []
    for row in reader:
        if len(row) != len(headers):
            continue  # skip malformed rows
        rows.append(dict(zip(headers, row)))

    if not rows:
        return Relation(frozenset(), attributes=frozenset(headers))

    types = infer_types(rows)
    tuples: set[Tuple_] = set()
    for row in rows:
        coerced = coerce_row(row, types)
        tuples.add(Tuple_(coerced))

    return Relation(frozenset(tuples), attributes=frozenset(headers))


def infer_types(rows: list[dict[str, str]]) -> dict[str, type]:
    """Scan column values and infer the best type per column.

    Priority: int > Decimal > bool > str.
    A column is int if every non-empty value parses as int.
    A column is Decimal if every non-empty value parses as a decimal number (but not all int).
    A column is bool if every non-empty value is 'true' or 'false' (case-insensitive).
    Otherwise str.
    """
    if not rows:
        return {}

    columns: dict[str, list[str]] = {k: [] for k in rows[0]}
    for row in rows:
        for k, v in row.items():
            columns[k].append(v)

    result: dict[str, type] = {}
    for col, values in columns.items():
        result[col] = _infer_column_type(values)
    return result


def _infer_column_type(values: list[str]) -> type:
    """Infer the type for a single column's values."""
    non_empty = [v for v in values if v != ""]
    if not non_empty:
        return str

    # Try int
    if all(_is_int(v) for v in non_empty):
        return int

    # Try Decimal
    if all(_is_decimal(v) for v in non_empty):
        return Decimal

    # Try bool
    if all(v.lower() in ("true", "false") for v in non_empty):
        return bool

    return str


def _is_int(s: str) -> bool:
    """Check if a string is a valid integer literal."""
    try:
        int(s)
        return True
    except ValueError:
        return False


def _is_decimal(s: str) -> bool:
    """Check if a string is a valid decimal number."""
    try:
        Decimal(s)
        return True
    except InvalidOperation:
        return False


def coerce_row(row: dict[str, str], types: dict[str, type]) -> dict[str, Value]:
    """Convert string values in a row to their inferred types."""
    result: dict[str, Value] = {}
    for k, v in row.items():
        result[k] = _coerce_value(v, types.get(k, str))
    return result


def _coerce_value(value: str, target_type: type) -> Value:
    """Coerce a single string value to the target type."""
    if value == "":
        return value  # keep empty string as-is

    if target_type is int:
        return int(value)
    if target_type is Decimal:
        return Decimal(value)
    if target_type is bool:
        return value.lower() == "true"
    return value
