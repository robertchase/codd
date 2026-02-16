"""Relation: an immutable set of tuples with relational operations."""

from __future__ import annotations

from typing import Callable

from prototype.model.types import Tuple_, Value


class Relation:
    """An immutable relation (set of tuples).

    Backed by frozenset[Tuple_] for automatic deduplication.
    All relational operations return new Relations.
    """

    __slots__ = ("_tuples", "_attributes", "_hash")

    def __init__(
        self,
        tuples: frozenset[Tuple_] | set[Tuple_] | list[Tuple_],
        attributes: frozenset[str] | None = None,
    ) -> None:
        if isinstance(tuples, frozenset):
            fs = tuples
        else:
            fs = frozenset(tuples)
        object.__setattr__(self, "_tuples", fs)

        if attributes is not None:
            object.__setattr__(self, "_attributes", attributes)
        elif fs:
            first = next(iter(fs))
            object.__setattr__(self, "_attributes", first.attributes())
        else:
            object.__setattr__(self, "_attributes", frozenset())
        object.__setattr__(self, "_hash", None)

    @property
    def tuples(self) -> frozenset[Tuple_]:
        """Return the underlying frozenset of tuples."""
        return self._tuples

    @property
    def attributes(self) -> frozenset[str]:
        """Return the set of attribute names."""
        return self._attributes

    def __len__(self) -> int:
        return len(self._tuples)

    def __iter__(self):
        return iter(self._tuples)

    def __contains__(self, item: Tuple_) -> bool:
        return item in self._tuples

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Relation):
            return NotImplemented
        return self._tuples == other._tuples and self._attributes == other._attributes

    def __hash__(self) -> int:
        if self._hash is None:
            h = hash((self._tuples, self._attributes))
            object.__setattr__(self, "_hash", h)
        return self._hash

    def __repr__(self) -> str:
        tups = ", ".join(repr(t) for t in self._tuples)
        return f"{{{tups}}}"

    def __setattr__(self, name: str, value: object) -> None:
        raise AttributeError("Relation is immutable")

    # --- Relational operations ---

    def project(self, attrs: frozenset[str]) -> Relation:
        """Project: keep only the specified attributes (#)."""
        projected = frozenset(t.project(attrs) for t in self._tuples)
        return Relation(projected, attributes=attrs)

    def where(self, predicate: Callable[[Tuple_], bool]) -> Relation:
        """Filter: keep tuples matching the predicate (?)."""
        filtered = frozenset(t for t in self._tuples if predicate(t))
        return Relation(filtered, attributes=self._attributes)

    def natural_join(self, other: Relation) -> Relation:
        """Natural join: combine on shared attributes (*)."""
        result_attrs = self._attributes | other._attributes
        result: set[Tuple_] = set()
        for t1 in self._tuples:
            for t2 in other._tuples:
                if t1.matches(t2):
                    result.add(t1.merge(t2))
        return Relation(frozenset(result), attributes=result_attrs)

    def nest_join(self, other: Relation, nest_name: str) -> Relation:
        """Nest join: like natural join but nests unmatched as empty sets (*:).

        For each tuple in self, find matching tuples in other,
        remove the shared attributes from the matches, and nest
        the result as a relation-valued attribute.
        """
        shared = self._attributes & other._attributes
        non_shared = other._attributes - shared
        result_attrs = self._attributes | frozenset({nest_name})

        result: set[Tuple_] = set()
        for t1 in self._tuples:
            matches: set[Tuple_] = set()
            for t2 in other._tuples:
                if t1.matches(t2):
                    matches.add(t2.project(non_shared))
            nested = Relation(frozenset(matches), attributes=non_shared)
            result.add(t1.extend({nest_name: nested}))
        return Relation(frozenset(result), attributes=result_attrs)

    def extend(self, compute: Callable[[Tuple_], dict[str, Value]]) -> Relation:
        """Extend: add computed attributes to each tuple (+)."""
        result: set[Tuple_] = set()
        new_attrs: frozenset[str] | None = None
        for t in self._tuples:
            new_values = compute(t)
            if new_attrs is None:
                new_attrs = self._attributes | frozenset(new_values.keys())
            result.add(t.extend(new_values))
        if new_attrs is None:
            new_attrs = self._attributes
        return Relation(frozenset(result), attributes=new_attrs)

    def modify(self, compute: Callable[[Tuple_], dict[str, Value]]) -> Relation:
        """Modify: replace existing attributes (+:)."""
        return self.extend(compute)

    def rename(self, mapping: dict[str, str]) -> Relation:
        """Rename: change attribute names (@)."""
        new_attrs = frozenset(mapping.get(a, a) for a in self._attributes)
        result = frozenset(t.rename(mapping) for t in self._tuples)
        return Relation(result, attributes=new_attrs)

    def union(self, other: Relation) -> Relation:
        """Union: tuples in either relation (|)."""
        return Relation(
            self._tuples | other._tuples, attributes=self._attributes
        )

    def difference(self, other: Relation) -> Relation:
        """Difference: tuples in self but not in other (-)."""
        return Relation(
            self._tuples - other._tuples, attributes=self._attributes
        )

    def intersect(self, other: Relation) -> Relation:
        """Intersect: tuples in both relations (&)."""
        return Relation(
            self._tuples & other._tuples, attributes=self._attributes
        )

    def summarize(
        self,
        group_attrs: frozenset[str],
        aggregates: dict[str, Callable[[Relation], Value]],
    ) -> Relation:
        """Summarize: group by key attrs, compute aggregates (/).

        Returns a relation with the grouping key(s) plus the named aggregates.
        """
        groups: dict[Tuple_, list[Tuple_]] = {}
        for t in self._tuples:
            key = t.project(group_attrs)
            groups.setdefault(key, []).append(t)

        result_attrs = group_attrs | frozenset(aggregates.keys())
        result: set[Tuple_] = set()
        for key_tuple, members in groups.items():
            group_rel = Relation(frozenset(members), attributes=self._attributes)
            agg_values = {name: fn(group_rel) for name, fn in aggregates.items()}
            result.add(key_tuple.extend(agg_values))
        return Relation(frozenset(result), attributes=result_attrs)

    def summarize_all(
        self, aggregates: dict[str, Callable[[Relation], Value]]
    ) -> Relation:
        """Summarize all: collapse entire relation, no grouping key (/.)."""
        agg_values = {name: fn(self) for name, fn in aggregates.items()}
        result_attrs = frozenset(aggregates.keys())
        return Relation(frozenset({Tuple_(agg_values)}), attributes=result_attrs)

    def nest_by(
        self, group_attrs: frozenset[str], nest_name: str
    ) -> Relation:
        """Nest by: group and nest into RVA, no collapse (/:).

        Returns a relation where each tuple has the grouping key(s)
        plus a relation-valued attribute containing the group members
        (with the grouping key attributes removed from the nested tuples).
        """
        groups: dict[Tuple_, list[Tuple_]] = {}
        for t in self._tuples:
            key = t.project(group_attrs)
            groups.setdefault(key, []).append(t)

        non_key_attrs = self._attributes - group_attrs
        result_attrs = group_attrs | frozenset({nest_name})
        result: set[Tuple_] = set()
        for key_tuple, members in groups.items():
            nested_tuples = frozenset(t.project(non_key_attrs) for t in members)
            nested = Relation(nested_tuples, attributes=non_key_attrs)
            result.add(key_tuple.extend({nest_name: nested}))
        return Relation(frozenset(result), attributes=result_attrs)

    def sort(self, key_fn: Callable[[Tuple_], object]) -> list[Tuple_]:
        """Sort: order the tuples, returning a list ($).

        This leaves the relational world — the result is an array.
        """
        return sorted(self._tuples, key=key_fn)
