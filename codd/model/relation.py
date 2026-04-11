"""Relation: an immutable set of tuples with relational operations."""

from __future__ import annotations

from typing import Callable

from codd.model.types import Tuple_, Value


class Relation:
    """An immutable relation (set of tuples).

    Backed by frozenset[Tuple_] for automatic deduplication.
    All relational operations return new Relations.
    """

    __slots__ = ("_tuples", "_attributes", "_schema", "_hash")

    def __init__(
        self,
        tuples: frozenset[Tuple_] | set[Tuple_] | list[Tuple_],
        attributes: frozenset[str] | None = None,
        schema: dict[str, str] | None = None,
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

        # Schema: attr name → type name.  None means untyped (implicit str).
        object.__setattr__(self, "_schema", schema)
        object.__setattr__(self, "_hash", None)

    @property
    def tuples(self) -> frozenset[Tuple_]:
        """Return the underlying frozenset of tuples."""
        return self._tuples

    @property
    def attributes(self) -> frozenset[str]:
        """Return the set of attribute names."""
        return self._attributes

    @property
    def schema(self) -> dict[str, str]:
        """Return the schema: attr name → type name.

        If no explicit schema was set, all attributes default to 'str'.
        """
        if self._schema is not None:
            return dict(self._schema)
        return {a: "str" for a in sorted(self._attributes)}

    def __len__(self) -> int:
        return len(self._tuples)

    def __iter__(self):
        return iter(self._tuples)

    def __contains__(self, item: Tuple_) -> bool:
        return item in self._tuples

    def _project_schema(self, attrs: frozenset[str]) -> dict[str, str] | None:
        """Return schema filtered to the given attributes, or None."""
        if self._schema is None:
            return None
        return {a: t for a, t in self._schema.items() if a in attrs}

    def _merge_schema(self, other: Relation) -> dict[str, str] | None:
        """Merge schemas from two relations, or None if neither has one."""
        if self._schema is None and other._schema is None:
            return None
        s1 = self._schema or {}
        s2 = other._schema or {}
        return {**s1, **s2}

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
        unknown = attrs - self._attributes
        if unknown:
            raise ValueError(f"project references unknown attributes: {sorted(unknown)}")
        projected = frozenset(t.project(attrs) for t in self._tuples)
        return Relation(projected, attributes=attrs, schema=self._project_schema(attrs))

    def remove(self, attrs: frozenset[str]) -> Relation:
        """Remove: drop the specified attributes, keep the rest (#!)."""
        unknown = attrs - self._attributes
        if unknown:
            raise ValueError(f"remove references unknown attributes: {sorted(unknown)}")
        return self.project(self._attributes - attrs)

    def where(self, predicate: Callable[[Tuple_], bool]) -> Relation:
        """Filter: keep tuples matching the predicate (?)."""
        filtered = frozenset(t for t in self._tuples if predicate(t))
        return Relation(filtered, attributes=self._attributes, schema=self._schema)

    def natural_join(self, other: Relation) -> Relation:
        """Natural join: combine on shared attributes (*)."""
        result_attrs = self._attributes | other._attributes
        result: set[Tuple_] = set()
        for t1 in self._tuples:
            for t2 in other._tuples:
                if t1.matches(t2):
                    result.add(t1.merge(t2))
        return Relation(frozenset(result), attributes=result_attrs,
                        schema=self._merge_schema(other))

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

    def extend(
        self,
        compute: Callable[[Tuple_], dict[str, Value]],
        added_attrs: frozenset[str] | None = None,
    ) -> Relation:
        """Extend: add computed attributes to each tuple (+).

        *added_attrs* names the columns the compute function will produce.
        When provided it is used to build the result heading even if the
        relation is empty (avoiding the silent attribute-drop that would
        otherwise occur on an empty relation).
        """
        result: set[Tuple_] = set()
        new_attrs: frozenset[str] | None = (
            self._attributes | added_attrs if added_attrs is not None else None
        )
        for t in self._tuples:
            new_values = compute(t)
            if new_attrs is None:
                overlap = self._attributes & frozenset(new_values.keys())
                if overlap:
                    raise ValueError(
                        f"extend cannot overwrite existing attributes (use modify): {sorted(overlap)}"
                    )
                new_attrs = self._attributes | frozenset(new_values.keys())
            result.add(t.extend(new_values))
        if new_attrs is None:
            new_attrs = self._attributes
        return Relation(frozenset(result), attributes=new_attrs, schema=self._schema)

    def modify(self, compute: Callable[[Tuple_], dict[str, Value]]) -> Relation:
        """Modify: replace existing attributes (+:)."""
        result: set[Tuple_] = set()
        for t in self._tuples:
            new_values = compute(t)
            unknown = frozenset(new_values.keys()) - self._attributes
            if unknown:
                raise ValueError(
                    f"modify references unknown attributes: {sorted(unknown)}"
                )
            result.add(t.extend(new_values))
        return Relation(frozenset(result), attributes=self._attributes,
                        schema=self._schema)

    def rename(self, mapping: dict[str, str]) -> Relation:
        """Rename: change attribute names (@)."""
        unknown = frozenset(mapping.keys()) - self._attributes
        if unknown:
            raise ValueError(f"rename references unknown attributes: {sorted(unknown)}")
        new_attrs = frozenset(mapping.get(a, a) for a in self._attributes)
        result = frozenset(t.rename(mapping) for t in self._tuples)
        new_schema = None
        if self._schema is not None:
            new_schema = {mapping.get(a, a): t for a, t in self._schema.items()}
        return Relation(result, attributes=new_attrs, schema=new_schema)

    def _check_same_heading(self, other: Relation, op: str) -> None:
        """Raise ValueError if two relations have different attributes."""
        if self._attributes != other._attributes:
            raise ValueError(
                f"{op} requires matching attributes: "
                f"{sorted(self._attributes)} vs {sorted(other._attributes)}"
            )

    def _normalize(self) -> Relation:
        """Return a copy of this relation with all tuple values coerced to their
        effective schema types.

        The effective schema is ``self.schema`` — explicit when ``_schema`` is
        set, defaulting to all-``str`` otherwise.  This ensures that set
        arithmetic (union/difference/intersect) compares values by their logical
        type rather than their incidental Python type.  For example, if the
        effective schema says ``id: str`` but the internal representation holds
        the Python int ``42``, normalization converts it to ``"42"`` so that set
        equality works correctly against a relation that holds ``"42"`` as str.

        Columns with ``in(...)`` constraints are left unchanged — ``in()`` is a
        membership constraint, not a storage-type change.
        """
        # Local import avoids circular dependency (coerce.py imports Relation).
        from codd.model.coerce import coerce_value, parse_type_string
        effective_schema = self.schema  # always returns a dict; defaults to all-str
        result: set[Tuple_] = set()
        for t in self._tuples:
            data = t.data
            for attr, type_str in effective_schema.items():
                if attr not in data:
                    continue
                base_type, constraint = parse_type_string(type_str)
                if base_type == "in":
                    continue  # in() is a constraint, not a type coercion
                if base_type == "decimal" and constraint is not None:
                    precision = int(constraint[1])
                    data[attr] = coerce_value(data[attr], "decimal", precision=precision)
                else:
                    data[attr] = coerce_value(data[attr], base_type)
            result.add(Tuple_(data))
        return Relation(frozenset(result), attributes=self._attributes,
                        schema=self._schema)

    def _normalize_to(self, schema: dict[str, str]) -> Relation:
        """Normalize this relation's tuples to a given schema.

        Like _normalize() but uses the provided schema instead of self.schema.
        This ensures both sides of a set operation use the same types — the
        LHS schema prevails.
        """
        from codd.model.coerce import coerce_value, parse_type_string

        result: set[Tuple_] = set()
        for t in self._tuples:
            data = t.data
            for attr, type_str in schema.items():
                if attr not in data:
                    continue
                base_type, constraint = parse_type_string(type_str)
                if base_type == "in":
                    continue
                if base_type == "decimal" and constraint is not None:
                    precision = int(constraint[1])
                    data[attr] = coerce_value(data[attr], "decimal", precision=precision)
                else:
                    data[attr] = coerce_value(data[attr], base_type)
            result.add(Tuple_(data))
        return Relation(frozenset(result), attributes=self._attributes,
                        schema=self._schema)

    def union(self, other: Relation) -> Relation:
        """Union: tuples in either relation (|).  LHS schema prevails."""
        self._check_same_heading(other, "union")
        target_schema = self.schema
        left = self._normalize_to(target_schema)
        right = other._normalize_to(target_schema)
        return Relation(
            left._tuples | right._tuples, attributes=self._attributes,
            schema=self._schema,
        )

    def difference(self, other: Relation) -> Relation:
        """Difference: tuples in self but not in other (-).  LHS schema prevails."""
        self._check_same_heading(other, "difference")
        target_schema = self.schema
        left = self._normalize_to(target_schema)
        right = other._normalize_to(target_schema)
        return Relation(
            left._tuples - right._tuples, attributes=self._attributes,
            schema=self._schema,
        )

    def intersect(self, other: Relation) -> Relation:
        """Intersect: tuples in both relations (&).  LHS schema prevails."""
        self._check_same_heading(other, "intersect")
        target_schema = self.schema
        left = self._normalize_to(target_schema)
        right = other._normalize_to(target_schema)
        return Relation(
            left._tuples & right._tuples, attributes=self._attributes,
            schema=self._schema,
        )

    def summarize(
        self,
        group_attrs: frozenset[str],
        aggregates: dict[str, Callable[[Relation], Value]],
        agg_schema: dict[str, str] | None = None,
    ) -> Relation:
        """Summarize: group by key attrs, compute aggregates (/).

        Returns a relation with the grouping key(s) plus the named aggregates.
        *agg_schema* optionally provides type names for the aggregate columns.
        """
        unknown = group_attrs - self._attributes
        if unknown:
            raise ValueError(
                f"summarize group key references unknown attributes: {sorted(unknown)}"
            )
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
        # Schema: group key types from source, aggregate types from agg_schema.
        schema = self._project_schema(group_attrs)
        if agg_schema:
            if schema is None:
                schema = {}
            schema.update(agg_schema)
        return Relation(frozenset(result), attributes=result_attrs, schema=schema)

    def summarize_all(
        self,
        aggregates: dict[str, Callable[[Relation], Value]],
        agg_schema: dict[str, str] | None = None,
    ) -> Relation:
        """Summarize all: collapse entire relation, no grouping key (/.)."""
        agg_values = {name: fn(self) for name, fn in aggregates.items()}
        result_attrs = frozenset(aggregates.keys())
        return Relation(
            frozenset({Tuple_(agg_values)}),
            attributes=result_attrs,
            schema=agg_schema,
        )

    def nest_by(
        self, group_attrs: frozenset[str], nest_name: str
    ) -> Relation:
        """Nest by: group and nest into RVA, no collapse (/:).

        Returns a relation where each tuple has the grouping key(s)
        plus a relation-valued attribute containing the group members
        (with the grouping key attributes removed from the nested tuples).
        """
        unknown = group_attrs - self._attributes
        if unknown:
            raise ValueError(
                f"nest_by group key references unknown attributes: {sorted(unknown)}"
            )
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

    def unnest(self, nest_attr: str) -> Relation:
        """Unnest: flatten a relation-valued attribute (<:).

        For each tuple, expand the RVA into individual tuples merged
        with the parent (minus the RVA attribute). Tuples with empty
        RVAs are dropped.
        """
        result: set[Tuple_] = set()
        result_attrs: frozenset[str] | None = None
        parent_attrs = self._attributes - {nest_attr}
        for t in self._tuples:
            rva = t[nest_attr]
            if not isinstance(rva, Relation):
                raise ValueError(f"{nest_attr} is not a relation-valued attribute")
            if len(rva) == 0:
                continue
            if result_attrs is None:
                result_attrs = parent_attrs | rva.attributes
            parent = t.project(parent_attrs)
            for nested in rva:
                result.add(parent.merge(nested))
        if result_attrs is None:
            result_attrs = parent_attrs
        return Relation(frozenset(result), attributes=result_attrs)

    def sort(self, key_fn: Callable[[Tuple_], object]) -> list[Tuple_]:
        """Sort: order the tuples, returning a list ($).

        This leaves the relational world — the result is an array.
        """
        return sorted(self._tuples, key=key_fn)
