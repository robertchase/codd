"""Aggregate function implementations: #. +. >. <. %."""

from __future__ import annotations

from decimal import Decimal, InvalidOperation

from prototype.model.relation import Relation
from prototype.model.types import Value


def _promote_numeric(val: Value) -> Value:
    """Promote a string to int or Decimal if possible."""
    if not isinstance(val, str):
        return val
    try:
        return int(val)
    except ValueError:
        pass
    try:
        return Decimal(val)
    except InvalidOperation:
        return val


def _extract_values(rel: Relation, attr: str) -> list[Value]:
    """Extract and promote values for an attribute across all tuples."""
    return [_promote_numeric(t[attr]) for t in rel]


def agg_count(rel: Relation, attr: str | None = None) -> int:
    """Count tuples in a relation (#.)."""
    return len(rel)


def agg_sum(rel: Relation, attr: str | None = None) -> int | float:
    """Sum an attribute across tuples (+.)."""
    if attr is None:
        raise ValueError("+. requires an attribute name")
    values = _extract_values(rel, attr)
    return sum(values)


def agg_max(rel: Relation, attr: str | None = None) -> int | float | str:
    """Max of an attribute across tuples (>.)."""
    if attr is None:
        raise ValueError(">. requires an attribute name")
    values = _extract_values(rel, attr)
    return max(values)


def agg_min(rel: Relation, attr: str | None = None) -> int | float | str:
    """Min of an attribute across tuples (<.)."""
    if attr is None:
        raise ValueError("<. requires an attribute name")
    values = _extract_values(rel, attr)
    return min(values)


def agg_mean(rel: Relation, attr: str | None = None) -> float:
    """Mean of an attribute across tuples (%.)."""
    if attr is None:
        raise ValueError("%. requires an attribute name")
    values = _extract_values(rel, attr)
    count = len(values)
    if count == 0:
        raise ValueError("%. on empty relation")
    return sum(float(v) for v in values) / count


AGGREGATE_FUNCTIONS: dict[str, type] = {}


def get_aggregate(func_name: str):
    """Return the aggregate function for the given name."""
    dispatch = {
        "#.": agg_count,
        "+.": agg_sum,
        ">.": agg_max,
        "<.": agg_min,
        "%.": agg_mean,
    }
    if func_name not in dispatch:
        raise ValueError(f"Unknown aggregate function: {func_name!r}")
    return dispatch[func_name]
