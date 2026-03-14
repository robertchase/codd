"""ASCII table and CSV formatters for displaying relations and arrays."""

from __future__ import annotations

import csv
import io
from decimal import Decimal

from codd.model.relation import Relation
from codd.model.types import OrderedArray, Tuple_


def format_value(value: object) -> str:
    """Format a single value for display."""
    if isinstance(value, Relation):
        if len(value) == 0:
            return "{}"
        tuples_str = ", ".join(_format_tuple_inline(t) for t in value)
        return "{" + tuples_str + "}"
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, str):
        return value
    return str(value)


def _format_tuple_inline(t: Tuple_) -> str:
    """Format a tuple inline for nested relation display."""
    parts = []
    for k in sorted(t.data.keys()):
        v = t[k]
        if isinstance(v, str):
            parts.append(f'{k}: "{v}"')
        else:
            parts.append(f"{k}: {format_value(v)}")
    return "(" + ", ".join(parts) + ")"


def format_relation(rel: Relation) -> str:
    """Format a relation as an ASCII table."""
    if len(rel) == 0:
        attrs = sorted(rel.attributes)
        if attrs:
            return _build_table(attrs, [])
        return "(empty relation)"

    # Determine column order: sort alphabetically
    attrs = sorted(rel.attributes)
    rows = []
    for t in rel:
        rows.append([format_value(t[a]) for a in attrs])

    return _build_table(attrs, rows)


def _array_attrs(arr: list[Tuple_]) -> list[str]:
    """Determine column order for an array.

    Uses explicit column_order from OrderedArray if available,
    otherwise sorts alphabetically.
    """
    if isinstance(arr, OrderedArray):
        return list(arr.column_order)
    return sorted(arr[0].data.keys())


def format_array(arr: list[Tuple_]) -> str:
    """Format a sorted array (list of tuples) as an ASCII table."""
    if not arr:
        return "(empty array)"

    attrs = _array_attrs(arr)
    rows = []
    for t in arr:
        rows.append([format_value(t[a]) for a in attrs])

    return _build_table(attrs, rows)


def format_csv(rel: Relation) -> str:
    """Format a relation as CSV text."""
    attrs = sorted(rel.attributes)
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(attrs)
    for t in rel:
        writer.writerow([format_value(t[a]) for a in attrs])
    return buf.getvalue().rstrip("\n")


def format_array_csv(arr: list[Tuple_]) -> str:
    """Format a sorted array (list of tuples) as CSV text."""
    if not arr:
        return ""
    attrs = _array_attrs(arr)
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(attrs)
    for t in arr:
        writer.writerow([format_value(t[a]) for a in attrs])
    return buf.getvalue().rstrip("\n")


def _build_table(headers: list[str], rows: list[list[str]]) -> str:
    """Build an ASCII table from headers and rows."""
    # Calculate column widths
    widths = [len(h) for h in headers]
    for row in rows:
        for i, cell in enumerate(row):
            widths[i] = max(widths[i], len(cell))

    # Build separator line
    sep = "+-" + "-+-".join("-" * w for w in widths) + "-+"

    # Build header
    header = "| " + " | ".join(h.ljust(w) for h, w in zip(headers, widths)) + " |"

    # Build rows
    lines = [sep, header, sep]
    for row in rows:
        line = "| " + " | ".join(cell.ljust(w) for cell, w in zip(row, widths)) + " |"
        lines.append(line)
    lines.append(sep)

    return "\n".join(lines)
