"""Aggregate function implementations: #. +. >. <. %."""

from __future__ import annotations

from prototype.model.relation import Relation


def agg_count(rel: Relation, attr: str | None = None) -> int:
    """Count tuples in a relation (#.)."""
    return len(rel)


def agg_sum(rel: Relation, attr: str | None = None) -> int | float:
    """Sum an attribute across tuples (+.)."""
    if attr is None:
        raise ValueError("+. requires an attribute name")
    return sum(t[attr] for t in rel)


def agg_max(rel: Relation, attr: str | None = None) -> int | float | str:
    """Max of an attribute across tuples (>.)."""
    if attr is None:
        raise ValueError(">. requires an attribute name")
    return max(t[attr] for t in rel)


def agg_min(rel: Relation, attr: str | None = None) -> int | float | str:
    """Min of an attribute across tuples (<.)."""
    if attr is None:
        raise ValueError("<. requires an attribute name")
    return min(t[attr] for t in rel)


def agg_mean(rel: Relation, attr: str | None = None) -> int | float:
    """Mean of an attribute across tuples (%.).

    Returns an integer (floor division) when all values are integers,
    matching the design doc examples (76667, not 76666.67).
    """
    if attr is None:
        raise ValueError("%. requires an attribute name")
    values = [t[attr] for t in rel]
    total = sum(values)
    count = len(values)
    if count == 0:
        raise ValueError("%. on empty relation")
    if all(isinstance(v, int) for v in values):
        return total // count
    return total / count


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
