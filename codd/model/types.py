"""Core types: Tuple_ and Value."""

from __future__ import annotations

import datetime
from decimal import Decimal
from typing import Union

# A Value can be a scalar or a nested Relation.
# We use a forward reference for Relation to avoid circular imports.
Value = Union[int, float, Decimal, str, bool, datetime.date, "Relation"]

# Re-export after Relation is defined; at runtime the union resolves lazily.


def _values_equal(a: Value, b: Value) -> bool:
    """Coercion-aware equality for join matching and comparisons.

    Handles date/string promotion (ISO format) and numeric/string promotion.
    """
    if a == b:
        return True
    # Date/string coercion.
    if isinstance(a, datetime.date) and isinstance(b, str):
        try:
            return a == datetime.date.fromisoformat(b)
        except ValueError:
            return False
    if isinstance(b, datetime.date) and isinstance(a, str):
        try:
            return datetime.date.fromisoformat(a) == b
        except ValueError:
            return False
    # Numeric/string coercion.
    if isinstance(a, str) and isinstance(b, (int, float, Decimal)):
        try:
            return Decimal(a) == b
        except Exception:
            return False
    if isinstance(b, str) and isinstance(a, (int, float, Decimal)):
        try:
            return a == Decimal(b)
        except Exception:
            return False
    return False


class Tuple_:
    """An immutable, hashable tuple (set of named values).

    Wraps a dict[str, Value] but is immutable and supports hashing
    for use inside frozensets.
    """

    __slots__ = ("_data", "_hash")

    def __init__(self, data: dict[str, Value] | None = None, **kwargs: Value) -> None:
        if data is not None:
            object.__setattr__(self, "_data", dict(data))
        else:
            object.__setattr__(self, "_data", dict(kwargs))
        object.__setattr__(self, "_hash", None)

    @property
    def data(self) -> dict[str, Value]:
        """Return a copy of the underlying data."""
        return dict(self._data)

    def get(self, attr: str) -> Value:
        """Get the value of an attribute."""
        return self._data[attr]

    def attributes(self) -> frozenset[str]:
        """Return the set of attribute names."""
        return frozenset(self._data.keys())

    def project(self, attrs: frozenset[str]) -> Tuple_:
        """Return a new Tuple_ keeping only the specified attributes."""
        return Tuple_({k: v for k, v in self._data.items() if k in attrs})

    def extend(self, new_attrs: dict[str, Value]) -> Tuple_:
        """Return a new Tuple_ with additional attributes."""
        merged = {**self._data, **new_attrs}
        return Tuple_(merged)

    def rename(self, mapping: dict[str, str]) -> Tuple_:
        """Return a new Tuple_ with attributes renamed per mapping (old -> new)."""
        return Tuple_(
            {mapping.get(k, k): v for k, v in self._data.items()}
        )

    def matches(self, other: Tuple_) -> bool:
        """Check if this tuple matches another on their shared attributes.

        Uses coercion-aware equality (date/string, numeric/string).
        """
        shared = self.attributes() & other.attributes()
        return all(_values_equal(self._data[k], other._data[k]) for k in shared)

    def merge(self, other: Tuple_) -> Tuple_:
        """Merge two tuples (for natural join). Shared attributes must agree."""
        return Tuple_({**self._data, **other._data})

    def __getitem__(self, key: str) -> Value:
        return self._data[key]

    def __contains__(self, key: str) -> bool:
        return key in self._data

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Tuple_):
            return NotImplemented
        return self._data == other._data

    def __hash__(self) -> int:
        if self._hash is None:
            h = hash(tuple(sorted(self._hashable_items())))
            object.__setattr__(self, "_hash", h)
        return self._hash

    def _hashable_items(self) -> list[tuple[str, object]]:
        """Convert items to a hashable form, handling nested Relations."""
        from codd.model.relation import Relation

        items: list[tuple[str, object]] = []
        for k, v in self._data.items():
            if isinstance(v, Relation):
                items.append((k, v))
            else:
                items.append((k, v))
        return items

    def __repr__(self) -> str:
        from codd.model.relation import Relation

        parts = []
        for k, v in self._data.items():
            if isinstance(v, str):
                parts.append(f'{k}: "{v}"')
            elif isinstance(v, Relation):
                parts.append(f"{k}: {v!r}")
            else:
                parts.append(f"{k}: {v}")
        return "(" + ", ".join(parts) + ")"

    def __setattr__(self, name: str, value: object) -> None:
        raise AttributeError("Tuple_ is immutable")


class OrderedArray(list["Tuple_"]):
    """A list of tuples with a defined column order for display.

    Subclasses list so it passes isinstance(x, list) checks throughout
    the system, but carries column_order metadata for formatters.
    """

    def __init__(self, tuples: list[Tuple_], column_order: tuple[str, ...]) -> None:
        super().__init__(tuples)
        # Use object.__setattr__ style to avoid conflicts, but list is mutable
        self.column_order = column_order
