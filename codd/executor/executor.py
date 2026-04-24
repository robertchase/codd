"""Tree-walking executor for the relational algebra AST.

Evaluates AST nodes against an Environment of named relations.
Uses isinstance dispatch (visitor-style without accept methods).
"""

from __future__ import annotations

import datetime
import re
from decimal import Decimal

from codd.executor.aggregates import _promote_numeric, agg_percent, get_aggregate
from codd.executor.environment import Environment
from codd.model.relation import Relation
from codd.model.types import OrderedArray, RotatedArray, Tuple_, Value, _values_equal, str_to_date
from codd.parser import ast_nodes as ast


class ExecutionError(Exception):
    """Raised on execution errors."""


class Executor:
    """Evaluates relational algebra AST nodes."""

    def __init__(self, env: Environment) -> None:
        self._env = env

    @property
    def env(self) -> Environment:
        """Return the environment."""
        return self._env

    def execute(
        self, node: ast.RelExpr | ast.Assignment
    ) -> Relation | list[Tuple_]:
        """Execute a relational expression or assignment.

        For assignments, evaluates the expression, binds the result in the
        environment, and returns the relation.
        """
        try:
            if isinstance(node, ast.Assignment):
                return self._eval_assignment(node)
            if isinstance(node, ast.TypeAlias):
                return self._eval_type_alias(node)
            return self._eval_rel(node)
        except ExecutionError:
            raise
        except (TypeError, ValueError) as e:
            raise ExecutionError(str(e)) from e

    def _eval_assignment(self, node: ast.Assignment) -> Relation | list[Tuple_]:
        """Evaluate an assignment: name := expr."""
        result = self._eval_rel(node.expr)
        if isinstance(result, Relation):
            self._env.bind(node.name, result)
        else:
            raise ExecutionError(
                "Cannot assign a sorted array to a name (sort produces a list, not a relation)"
            )
        return result

    def _eval_type_alias(self, node: ast.TypeAlias) -> None:
        """Evaluate a type alias: name := type target."""
        self._env.bind_type(node.name, node.target_type)
        return None

    def _eval_rel(self, node: ast.RelExpr) -> Relation | list[Tuple_]:
        """Evaluate a relational expression node."""
        if isinstance(node, ast.RelName):
            return self._eval_rel_name(node)
        if isinstance(node, ast.Filter):
            return self._eval_filter(node)
        if isinstance(node, ast.NegatedFilter):
            return self._eval_negated_filter(node)
        if isinstance(node, ast.Project):
            return self._eval_project(node)
        if isinstance(node, ast.Remove):
            return self._eval_remove(node)
        if isinstance(node, ast.NaturalJoin):
            return self._eval_natural_join(node)
        if isinstance(node, ast.LeftJoin):
            return self._eval_left_join(node)
        if isinstance(node, ast.NestJoin):
            return self._eval_nest_join(node)
        if isinstance(node, ast.Unnest):
            return self._eval_unnest(node)
        if isinstance(node, ast.Extend):
            return self._eval_extend(node)
        if isinstance(node, ast.Modify):
            return self._eval_modify(node)
        if isinstance(node, ast.Rename):
            return self._eval_rename(node)
        if isinstance(node, ast.Union):
            return self._eval_union(node)
        if isinstance(node, ast.Difference):
            return self._eval_difference(node)
        if isinstance(node, ast.Intersect):
            return self._eval_intersect(node)
        if isinstance(node, ast.Summarize):
            return self._eval_summarize(node)
        if isinstance(node, ast.SummarizeAll):
            return self._eval_summarize_all(node)
        if isinstance(node, ast.BroadcastAggregate):
            return self._eval_broadcast_agg(node)
        if isinstance(node, ast.BroadcastAggregateAll):
            return self._eval_broadcast_agg_all(node)
        if isinstance(node, ast.NestBy):
            return self._eval_nest_by(node)
        if isinstance(node, ast.Sort):
            return self._eval_sort(node)
        if isinstance(node, ast.Rank):
            return self._eval_rank(node)
        if isinstance(node, ast.Split):
            return self._eval_split(node)
        if isinstance(node, ast.OrderColumns):
            return self._eval_order_columns(node)
        if isinstance(node, ast.Take):
            return self._eval_take(node)
        if isinstance(node, ast.Iota):
            return self._eval_iota(node)
        if isinstance(node, ast.RelationLiteral):
            return self._eval_relation_literal(node)
        if isinstance(node, ast.Rotate):
            return self._eval_rotate(node)
        if isinstance(node, ast.ApplySchema):
            return self._eval_apply_schema(node)
        if isinstance(node, ast.ExtractSchema):
            return self._eval_extract_schema(node)
        raise ExecutionError(f"Unknown node type: {type(node).__name__}")

    def _as_relation(self, node: ast.RelExpr) -> Relation:
        """Evaluate a node and assert it returns a Relation."""
        result = self._eval_rel(node)
        if not isinstance(result, Relation):
            raise ExecutionError("Expected a relation, got an array (did you sort?)")
        return result

    def _enforce_schema(
        self, rel: Relation, changed_attrs: frozenset[str] | None = None
    ) -> None:
        """Validate a relation against its schema after mutation.

        Only checks *changed_attrs* (if given) for efficiency.
        Raises ExecutionError on violation.
        """
        from codd.model.coerce import CoercionError, validate_schema

        try:
            validate_schema(rel, env=self._env, attrs=changed_attrs)
        except CoercionError as e:
            raise ExecutionError(str(e)) from e

    # --- Node evaluators ---

    def _eval_iota(self, node: ast.Iota) -> Relation:
        """Evaluate: i. [name:] count  (1-based)  or  I. [name:] count  (0-based).

        Generate a single-attribute relation with integers 1..count or 0..count-1.
        count may be a literal integer or a subquery expression.
        """
        op = "I." if node.zero_based else "i."
        count_val = self._eval_expr(node.count, Tuple_({}), Relation(frozenset()))
        if not isinstance(count_val, int):
            raise ExecutionError(
                f"{op} count must be an integer, got {type(count_val).__name__}"
            )
        if count_val <= 0:
            raise ExecutionError(
                f"{op} count must be a positive integer, got {count_val}"
            )
        start = 0 if node.zero_based else 1
        tuples = frozenset(
            Tuple_({node.name: i}) for i in range(start, start + count_val)
        )
        return Relation(tuples, attributes=frozenset({node.name}))

    def _eval_relation_literal(self, node: ast.RelationLiteral) -> Relation:
        """Evaluate an inline relation literal."""
        attrs = node.attributes
        tuples = frozenset(
            Tuple_(dict(zip(attrs, row))) for row in node.rows
        )
        return Relation(tuples, attributes=frozenset(attrs))

    def _eval_rel_name(self, node: ast.RelName) -> Relation:
        """Look up a named relation in the environment."""
        try:
            return self._env.lookup(node.name)
        except KeyError:
            raise ExecutionError(f"Unknown relation: {node.name!r}")

    def _eval_filter(self, node: ast.Filter) -> Relation:
        """Evaluate: source ? condition."""
        source = self._as_relation(node.source)
        predicate = self._compile_condition(node.condition)
        return source.where(predicate)

    def _eval_negated_filter(self, node: ast.NegatedFilter) -> Relation:
        """Evaluate: source ?! condition."""
        source = self._as_relation(node.source)
        predicate = self._compile_condition(node.condition)
        return source.where(lambda t: not predicate(t))

    def _eval_project(self, node: ast.Project) -> Relation:
        """Evaluate: source # attrs."""
        source = self._as_relation(node.source)
        return source.project(frozenset(node.attrs))

    def _eval_remove(self, node: ast.Remove) -> Relation:
        """Evaluate: source #! attrs."""
        source = self._as_relation(node.source)
        return source.remove(frozenset(node.attrs))

    def _eval_natural_join(self, node: ast.NaturalJoin) -> Relation:
        """Evaluate: source * right."""
        left = self._as_relation(node.source)
        right = self._as_relation(node.right)
        return left.natural_join(right)

    def _eval_left_join(self, node: ast.LeftJoin) -> Relation:
        """Evaluate: source *< right [col: default, ...].

        Keeps every left tuple.  For matched tuples the right-only attrs are
        added as in a natural join.  For unmatched tuples the right-only attrs
        are filled from *defaults*; an error is raised if any right-only attr
        lacks a default and there are unmatched tuples.
        """
        left = self._as_relation(node.source)
        right = self._as_relation(node.right)
        shared = left.attributes & right.attributes
        right_only = right.attributes - shared
        result_attrs = left.attributes | right.attributes

        # Evaluate default expressions once (they should be constants).
        defaults: dict[str, Value] = {}
        for comp in node.defaults:
            defaults[comp.name] = self._eval_expr(comp.expr, Tuple_({}), left)

        result: set[Tuple_] = set()
        for t_left in left:
            matched = False
            for t_right in right:
                if t_left.matches(t_right):
                    # t_right.merge(t_left): left wins for shared attrs,
                    # preserving the left side's types (e.g. str vs int).
                    result.add(t_right.merge(t_left))
                    matched = True
            if not matched:
                missing = right_only - frozenset(defaults.keys())
                if missing:
                    raise ExecutionError(
                        f"left join: unmatched tuple has no default for: {sorted(missing)}"
                    )
                fill = {attr: defaults[attr] for attr in right_only}
                result.add(t_left.extend(fill))

        schema = left._merge_schema(right)
        return Relation(frozenset(result), attributes=result_attrs, schema=schema)

    def _eval_nest_join(self, node: ast.NestJoin) -> Relation:
        """Evaluate: source *: name: right."""
        left = self._as_relation(node.source)
        right = self._as_relation(node.right)
        return left.nest_join(right, node.nest_name)

    def _eval_unnest(self, node: ast.Unnest) -> Relation:
        """Evaluate: source <: nest_attr."""
        source = self._as_relation(node.source)
        return source.unnest(node.nest_attr)

    @staticmethod
    def _extract_cast_types(
        computations: tuple[ast.NamedExpr, ...],
    ) -> dict[str, str]:
        """Extract schema type overrides from .as casts in computations.

        If a computation's outermost expression is a TypeCast, the declared
        target type is recorded so it can be merged into the relation schema.
        """
        overrides: dict[str, str] = {}
        for comp in computations:
            expr = comp.expr
            if isinstance(expr, ast.TypeCast):
                overrides[comp.name] = expr.target_type
        return overrides

    def _merge_cast_schema(
        self, rel: Relation, overrides: dict[str, str]
    ) -> Relation:
        """Return a copy of *rel* with schema entries updated from .as casts.

        UDT aliases in override types are resolved to their canonical form
        so downstream consumers see only built-in/pattern type strings.
        """
        if not overrides:
            return rel
        from codd.model.coerce import resolve_type_alias
        resolved_overrides = {
            attr: resolve_type_alias(t, self._env)
            for attr, t in overrides.items()
        }
        schema = dict(rel.schema)  # always returns a dict
        schema.update(resolved_overrides)
        return Relation(
            rel._tuples, attributes=rel._attributes, schema=schema
        )

    def _eval_extend(self, node: ast.Extend) -> Relation:
        """Evaluate: source + computations."""
        source = self._as_relation(node.source)
        new_names = frozenset(c.name for c in node.computations)

        def compute(t: Tuple_) -> dict[str, Value]:
            result: dict[str, Value] = {}
            for comp in node.computations:
                result[comp.name] = self._eval_expr(comp.expr, t, source)
            return result

        result = source.extend(compute, added_attrs=new_names)
        result = self._merge_cast_schema(result, self._extract_cast_types(node.computations))
        self._enforce_schema(result, changed_attrs=new_names)
        return result

    def _eval_modify(self, node: ast.Modify) -> Relation:
        """Evaluate: source =: computations (update existing attributes)."""
        source = self._as_relation(node.source)
        changed_names = frozenset(c.name for c in node.computations)

        def compute(t: Tuple_) -> dict[str, Value]:
            result: dict[str, Value] = {}
            for comp in node.computations:
                result[comp.name] = self._eval_expr(comp.expr, t, source)
            return result

        result = source.modify(compute)
        result = self._merge_cast_schema(result, self._extract_cast_types(node.computations))
        self._enforce_schema(result, changed_attrs=changed_names)
        return result

    def _eval_rename(self, node: ast.Rename) -> Relation:
        """Evaluate: source @ mappings."""
        source = self._as_relation(node.source)
        mapping = dict(node.mappings)
        return source.rename(mapping)

    def _eval_union(self, node: ast.Union) -> Relation:
        """Evaluate: source | right."""
        left = self._as_relation(node.source)
        right = self._as_relation(node.right)
        result = left.union(right)
        self._enforce_schema(result)
        return result

    def _eval_difference(self, node: ast.Difference) -> Relation:
        """Evaluate: source - right."""
        left = self._as_relation(node.source)
        right = self._as_relation(node.right)
        return left.difference(right)

    def _eval_intersect(self, node: ast.Intersect) -> Relation:
        """Evaluate: source & right."""
        left = self._as_relation(node.source)
        right = self._as_relation(node.right)
        return left.intersect(right)

    def _eval_summarize(self, node: ast.Summarize) -> Relation:
        """Evaluate: source / group_attrs [computations]."""
        source = self._as_relation(node.source)
        agg_fns: dict[str, callable] = {}
        for comp in node.computations:
            expr = comp.expr

            def make_fn(e: ast.Expr):
                def f(group_rel: Relation) -> Value:
                    return self._eval_summarize_expr(e, group_rel, source)
                return f

            agg_fns[comp.name] = make_fn(expr)

        agg_schema = self._build_agg_schema(node.computations, source)
        return source.summarize(frozenset(node.group_attrs), agg_fns,
                                agg_schema=agg_schema)

    def _eval_summarize_all(self, node: ast.SummarizeAll) -> Relation:
        """Evaluate: source /. [computations]."""
        source = self._as_relation(node.source)
        agg_fns: dict[str, callable] = {}
        for comp in node.computations:
            expr = comp.expr

            def make_fn(e: ast.Expr):
                def f(rel: Relation) -> Value:
                    return self._eval_summarize_expr(e, rel, source)
                return f

            agg_fns[comp.name] = make_fn(expr)

        agg_schema = self._build_agg_schema(node.computations, source)
        return source.summarize_all(agg_fns, agg_schema=agg_schema)

    # Aggregate functions that always return a specific type regardless of
    # the input column.  Count is int; mean and percent are always float.
    _AGG_FIXED_TYPES: dict[str, str] = {
        "#.": "int",
        "%.": "float",
        "p.": "float",
    }

    def _build_agg_schema(
        self, computations: list, source: Relation
    ) -> dict[str, str] | None:
        """Build schema for aggregate output columns.

        .as casts declare their target type (UDT aliases resolved).
        Aggregates with a fixed return type (#., %., p.) use that type.
        Otherwise a simple aggregate on a single column (e.g. +. amount)
        inherits that column's type from the source schema.
        """
        from codd.model.coerce import resolve_type_alias
        schema: dict[str, str] = {}
        src_schema = source.schema
        for comp in computations:
            expr = comp.expr
            # .as cast wins: use the declared target type, resolving UDTs.
            if isinstance(expr, ast.TypeCast):
                schema[comp.name] = resolve_type_alias(
                    expr.target_type, self._env
                )
                continue
            if isinstance(expr, ast.AggregateCall):
                # Fixed-type aggregates (#., %., p.) don't depend on input.
                if expr.func in self._AGG_FIXED_TYPES:
                    schema[comp.name] = self._AGG_FIXED_TYPES[expr.func]
                    continue
                # Simple aggregate on a single column: inherit its type.
                if expr.arg is not None:
                    src_attr = expr.arg.parts[0]
                    if src_attr in src_schema:
                        schema[comp.name] = src_schema[src_attr]
        return schema if schema else None

    def _eval_broadcast_agg(self, node: ast.BroadcastAggregate) -> Relation:
        """Evaluate: source /* group_attrs [computations].

        Computes aggregates per group and broadcasts the values back to
        every tuple in the source, preserving all original attributes.
        """
        source = self._as_relation(node.source)
        group_attrs = frozenset(node.group_attrs)

        # Build aggregate functions (same pattern as summarize).
        agg_fns: dict[str, callable] = {}
        for comp in node.computations:
            expr = comp.expr

            def make_fn(e: ast.Expr):
                def f(rel: Relation) -> Value:
                    return self._eval_summarize_expr(e, rel, source)
                return f

            agg_fns[comp.name] = make_fn(expr)

        # Group tuples and compute aggregates per group.
        groups: dict[Tuple_, list[Tuple_]] = {}
        for t in source:
            key = t.project(group_attrs)
            groups.setdefault(key, []).append(t)

        lookup: dict[Tuple_, dict[str, Value]] = {}
        for key_tuple, members in groups.items():
            group_rel = Relation(frozenset(members), attributes=source.attributes)
            lookup[key_tuple] = {
                name: fn(group_rel) for name, fn in agg_fns.items()
            }

        # Extend every tuple with its group's aggregates.
        new_attrs = source.attributes | frozenset(agg_fns.keys())
        result: set[Tuple_] = set()
        for t in source:
            key = t.project(group_attrs)
            result.add(t.extend(lookup[key]))

        agg_schema = self._build_agg_schema(node.computations, source)
        schema = _combine_schemas(source._schema, agg_schema)
        return Relation(frozenset(result), attributes=new_attrs, schema=schema)

    def _eval_broadcast_agg_all(self, node: ast.BroadcastAggregateAll) -> Relation:
        """Evaluate: source /* [computations].

        Computes aggregates over the entire source and broadcasts the
        values back to every tuple.
        """
        source = self._as_relation(node.source)

        # Compute aggregates once over the whole relation.
        agg_values: dict[str, Value] = {}
        for comp in node.computations:
            agg_values[comp.name] = self._eval_summarize_expr(
                comp.expr, source, source
            )

        # Extend every tuple with the constant aggregate values.
        new_attrs = source.attributes | frozenset(agg_values.keys())
        result: set[Tuple_] = set()
        for t in source:
            result.add(t.extend(agg_values))

        agg_schema = self._build_agg_schema(node.computations, source)
        schema = _combine_schemas(source._schema, agg_schema)
        return Relation(frozenset(result), attributes=new_attrs, schema=schema)

    def _eval_summarize_expr(
        self, expr: ast.Expr, group_rel: Relation, whole_rel: Relation
    ) -> Value:
        """Evaluate a scalar expression in summarize context.

        AggregateCall nodes are evaluated against group_rel.
        p. (percent) also receives whole_rel for the denominator.
        SubqueryExpr nodes are evaluated as relational expressions and
        unwrapped to a scalar (must be 1x1).
        BinOp, Round, and literals recurse naturally.
        AttrRef is an error (no tuple context in summarize).
        """
        if isinstance(expr, ast.IntLiteral):
            return expr.value
        if isinstance(expr, ast.FloatLiteral):
            return expr.value
        if isinstance(expr, ast.StringLiteral):
            return expr.value
        if isinstance(expr, ast.BoolLiteral):
            return expr.value
        if isinstance(expr, ast.AggregateCall):
            if expr.func == "p.":
                attr_name = expr.arg.parts[0] if expr.arg else None
                return agg_percent(group_rel, attr_name, whole_rel)
            agg_fn = get_aggregate(expr.func)
            attr_name = expr.arg.parts[0] if expr.arg else None
            return agg_fn(group_rel, attr_name)
        if isinstance(expr, ast.SubqueryExpr):
            result = self._as_relation(expr.query)
            return self._unwrap_scalar(result)
        if isinstance(expr, ast.BinOp):
            left = _promote_numeric(
                self._eval_summarize_expr(expr.left, group_rel, whole_rel)
            )
            right = _promote_numeric(
                self._eval_summarize_expr(expr.right, group_rel, whole_rel)
            )
            return self._apply_binop(expr.op, left, right)
        if isinstance(expr, ast.Round):
            value = self._eval_summarize_expr(expr.expr, group_rel, whole_rel)
            return self._apply_round(value, expr.places)
        if isinstance(expr, ast.Substring):
            value = self._eval_summarize_expr(expr.expr, group_rel, whole_rel)
            return self._apply_substring(value, expr.start, expr.end)
        if isinstance(expr, ast.StringOp):
            value = self._eval_summarize_expr(expr.expr, group_rel, whole_rel)
            return self._apply_string_op(value, expr.op)
        if isinstance(expr, ast.RegexReplace):
            value = self._eval_summarize_expr(expr.expr, group_rel, whole_rel)
            return self._apply_regex_replace(str(value), expr.pattern, expr.replacement)
        if isinstance(expr, ast.DateOp):
            value = self._eval_summarize_expr(expr.expr, group_rel, whole_rel)
            return self._apply_date_op(value, expr.fmt)
        if isinstance(expr, ast.TypeCast):
            value = self._eval_summarize_expr(expr.expr, group_rel, whole_rel)
            return self._apply_type_cast(value, expr.target_type)
        if isinstance(expr, ast.FormatStr):
            raise ExecutionError(
                "Cannot use .f in summarize context (no tuple for attribute references)"
            )
        if isinstance(expr, ast.AttrRef):
            raise ExecutionError(
                f"Cannot reference attribute {expr.name!r} in summarize context"
                " (use an aggregate function)"
            )
        raise ExecutionError(
            f"Unsupported expression in summarize: {type(expr).__name__}"
        )

    def _unwrap_scalar(self, rel: Relation) -> Value:
        """Extract the single value from a 1x1 relation."""
        if len(rel.attributes) != 1:
            raise ExecutionError(
                f"Scalar subquery must return exactly 1 attribute,"
                f" got {len(rel.attributes)}"
            )
        if len(rel) != 1:
            raise ExecutionError(
                f"Scalar subquery must return exactly 1 tuple,"
                f" got {len(rel)}"
            )
        t = next(iter(rel))
        attr = next(iter(rel.attributes))
        return t[attr]

    def _eval_nest_by(self, node: ast.NestBy) -> Relation:
        """Evaluate: source /: name: group_attrs."""
        source = self._as_relation(node.source)
        return source.nest_by(frozenset(node.group_attrs), node.nest_name)

    def _eval_sort(self, node: ast.Sort) -> list[Tuple_]:
        """Evaluate: source $ keys.

        Sort respects the relation's schema: if a key attribute has a
        declared type (e.g. int), values are coerced before comparison so
        that string "10" sorts numerically after "2".
        """
        from codd.model.coerce import coerce_value, parse_type_string

        source = self._as_relation(node.source)
        keys = node.keys
        schema = source.schema

        # Pre-compute coercion info per sort key.
        key_types: list[str | None] = []
        for k in keys:
            raw_type = schema.get(k.attr, "str")
            base_type, constraint = parse_type_string(raw_type)
            # in() constraints are not useful for coercion.
            if base_type == "in":
                key_types.append(None)
            else:
                key_types.append(base_type)

        def sort_key(t: Tuple_) -> tuple:
            parts = []
            for k, ktype in zip(keys, key_types):
                val = t[k.attr]
                # Coerce to schema type for comparison.
                if ktype is not None:
                    try:
                        val = coerce_value(val, ktype)
                    except Exception:
                        pass  # fall back to raw value
                if k.descending:
                    if isinstance(val, (int, float, Decimal)):
                        parts.append(-val)
                    else:
                        parts.append(_ReverseKey(val))
                else:
                    parts.append(val)
            return tuple(parts)

        return source.sort(sort_key)

    def _eval_rank(self, node: ast.Rank) -> Relation:
        """Evaluate: source /^ name: keys.

        Adds an attribute *name* with the dense rank of each tuple in
        the sort order defined by *keys*.  Tied tuples receive the same
        rank; ranks are 1-based with no gaps.
        """
        from codd.model.coerce import coerce_value, parse_type_string

        source = self._as_relation(node.source)
        if node.name in source.attributes:
            raise ExecutionError(
                f"/^: attribute {node.name!r} already exists "
                f"(use #! to remove it first, or choose another name)"
            )
        for k in node.keys:
            if k.attr not in source.attributes:
                raise ExecutionError(
                    f"/^: unknown key attribute {k.attr!r}"
                )

        # Mirror _eval_sort's schema-aware coercion for key values.
        schema = source.schema
        key_types: list[str | None] = []
        for k in node.keys:
            raw_type = schema.get(k.attr, "str")
            base_type, _ = parse_type_string(raw_type)
            key_types.append(None if base_type == "in" else base_type)

        def coerced_values(t: Tuple_) -> tuple:
            """Hashable tuple of coerced key values (no direction applied)."""
            parts = []
            for k, ktype in zip(node.keys, key_types):
                val = t[k.attr]
                if ktype is not None:
                    try:
                        val = coerce_value(val, ktype)
                    except Exception:
                        pass
                parts.append(val)
            return tuple(parts)

        def sort_order_key(raw_key: tuple) -> tuple:
            """Apply descending logic to a raw key tuple for ordering."""
            parts = []
            for val, k in zip(raw_key, node.keys):
                if k.descending:
                    if isinstance(val, (int, float, Decimal)):
                        parts.append(-val)
                    else:
                        parts.append(_ReverseKey(val))
                else:
                    parts.append(val)
            return tuple(parts)

        # Collect distinct raw key values, sort them, assign dense ranks.
        distinct_keys = sorted(
            {coerced_values(t) for t in source}, key=sort_order_key
        )
        ranks: dict[tuple, int] = {k: i + 1 for i, k in enumerate(distinct_keys)}

        # Build result: each tuple extended with its rank.
        result_tuples = frozenset(
            t.extend({node.name: ranks[coerced_values(t)]}) for t in source
        )
        new_attrs = source._attributes | frozenset({node.name})
        new_schema = dict(source.schema)  # default fills in str for unset attrs
        new_schema[node.name] = "int"
        return Relation(
            result_tuples, attributes=new_attrs, schema=new_schema
        )

    def _eval_split(self, node: ast.Split) -> Relation:
        """Evaluate a /> split/explode.

        See ast.Split for the forms supported.  Splits the string value
        of *col* by the regex *pattern* and emits one tuple per piece.
        When *pos* is set, a 1-based position column is also added.
        """
        source = self._as_relation(node.source)
        if node.col not in source.attributes:
            raise ExecutionError(
                f"/>: unknown attribute {node.col!r}"
            )
        if node.new != node.col and node.new in source.attributes:
            raise ExecutionError(
                f"/>: attribute {node.new!r} already exists "
                f"(use a different name or remove it first with #!)"
            )
        if node.pos is not None:
            if node.pos == node.new:
                raise ExecutionError(
                    f"/>: position name must differ from piece name "
                    f"({node.pos!r})"
                )
            if node.pos != node.col and node.pos in source.attributes:
                raise ExecutionError(
                    f"/>: position attribute {node.pos!r} already exists"
                )
        try:
            pat = re.compile(node.pattern)
        except re.error as e:
            raise ExecutionError(f"/>: invalid regex {node.pattern!r}: {e}") from e

        result: set[Tuple_] = set()
        for t in source:
            val = t[node.col]
            if not isinstance(val, str):
                raise ExecutionError(
                    f"/>: cannot split non-string value "
                    f"{node.col}={val!r} (type {type(val).__name__})"
                )
            pieces = pat.split(val)
            for idx, piece in enumerate(pieces, start=1):
                data = dict(t.data)
                if node.new == node.col:
                    data[node.col] = piece
                else:
                    data[node.new] = piece
                if node.pos is not None:
                    data[node.pos] = idx
                result.add(Tuple_(data))

        new_attrs = set(source._attributes)
        new_attrs.add(node.new)
        if node.pos is not None:
            new_attrs.add(node.pos)

        # Schema: piece is str, position is int.
        new_schema = dict(source.schema)
        new_schema[node.new] = "str"
        if node.pos is not None:
            new_schema[node.pos] = "int"
        return Relation(
            frozenset(result),
            attributes=frozenset(new_attrs),
            schema=new_schema,
        )

    def _eval_rotate(self, node: ast.Rotate) -> RotatedArray:
        """Evaluate: source r. — rotated (vertical) display.

        Accepts both relations and arrays (e.g. after $ sort).
        """
        source = self._eval_rel(node.source)
        if isinstance(source, list):
            return RotatedArray(source)
        return RotatedArray(list(source))

    def _eval_apply_schema(self, node: ast.ApplySchema) -> Relation:
        """Evaluate: R :: S — apply schema relation S to relation R."""
        from codd.model.coerce import (
            CoercionError,
            apply_schema,
            schema_from_relation,
        )

        source = self._as_relation(node.source)
        schema_rel = self._as_relation(node.schema_rel)
        try:
            schema_dict = schema_from_relation(schema_rel, env=self._env)
            return apply_schema(source, schema_dict, env=self._env)
        except CoercionError as e:
            raise ExecutionError(str(e)) from e

    def _eval_extract_schema(self, node: ast.ExtractSchema) -> Relation:
        """Evaluate: R :: — extract schema as a relation {attr, type}."""
        from codd.model.coerce import extract_schema

        source = self._as_relation(node.source)
        return extract_schema(source)

    def _eval_order_columns(self, node: ast.OrderColumns) -> OrderedArray:
        """Evaluate: source $. [col1 col2 ...].

        Projects to the listed columns and returns an OrderedArray
        that preserves the specified column display order.
        """
        source = self._eval_rel(node.source)
        columns = node.columns

        # Get tuples from relation or list.
        if isinstance(source, Relation):
            tuples = list(source)
            available: frozenset[str] | None = source.attributes
        elif isinstance(source, list):
            tuples = source
            # Attribute info is lost in a sorted empty list; skip validation.
            available = tuples[0].attributes() if tuples else None
        else:
            raise ExecutionError("$. (order columns) requires a relation or list")

        # Validate all columns exist (skip when attribute info is unavailable).
        if available is not None:
            for col in columns:
                if col not in available:
                    raise ExecutionError(
                        f"$. unknown attribute: {col!r}"
                    )

        # Project tuples to only the listed columns.
        keep = frozenset(columns)
        projected = [t.project(keep) for t in tuples]
        return OrderedArray(projected, columns)

    def _eval_take(self, node: ast.Take) -> list[Tuple_]:
        """Evaluate: source ^ N."""
        source = self._eval_rel(node.source)
        if isinstance(source, Relation):
            return list(source)[: node.count]
        if isinstance(source, list):
            return source[: node.count]
        raise ExecutionError("^ (take) requires a relation or sorted array")

    # --- Expression evaluation ---

    def _eval_expr(
        self, expr: ast.Expr, t: Tuple_, source: Relation | None = None
    ) -> Value:
        """Evaluate a scalar expression in the context of a tuple.

        source is the enclosing relation (from extend), used by p.
        """
        if isinstance(expr, ast.IntLiteral):
            return expr.value
        if isinstance(expr, ast.FloatLiteral):
            return expr.value
        if isinstance(expr, ast.StringLiteral):
            return expr.value
        if isinstance(expr, ast.BoolLiteral):
            return expr.value
        if isinstance(expr, ast.AttrRef):
            return self._eval_attr_ref(expr, t)
        if isinstance(expr, ast.BinOp):
            return self._eval_binop(expr, t, source)
        if isinstance(expr, ast.AggregateCall):
            return self._eval_aggregate_call(expr, t, source)
        if isinstance(expr, ast.SubqueryExpr):
            result = self._as_relation(expr.query)
            return self._unwrap_scalar(result)
        if isinstance(expr, ast.TernaryExpr):
            return self._eval_ternary(expr, t, source)
        if isinstance(expr, ast.Round):
            value = self._eval_expr(expr.expr, t, source)
            return self._apply_round(value, expr.places)
        if isinstance(expr, ast.Substring):
            value = self._eval_expr(expr.expr, t, source)
            return self._apply_substring(value, expr.start, expr.end)
        if isinstance(expr, ast.StringOp):
            value = self._eval_expr(expr.expr, t, source)
            return self._apply_string_op(value, expr.op)
        if isinstance(expr, ast.RegexReplace):
            value = self._eval_expr(expr.expr, t, source)
            return self._apply_regex_replace(str(value), expr.pattern, expr.replacement)
        if isinstance(expr, ast.DateOp):
            value = self._eval_expr(expr.expr, t, source)
            return self._apply_date_op(value, expr.fmt)
        if isinstance(expr, ast.FormatStr):
            value = self._eval_expr(expr.expr, t, source)
            return self._apply_format_str(str(value), t)
        if isinstance(expr, ast.TypeCast):
            value = self._eval_expr(expr.expr, t, source)
            return self._apply_type_cast(value, expr.target_type)
        raise ExecutionError(f"Unknown expression type: {type(expr).__name__}")

    def _eval_attr_ref(self, ref: ast.AttrRef, t: Tuple_) -> Value:
        """Evaluate an attribute reference, possibly dotted."""
        try:
            if len(ref.parts) == 1:
                return t[ref.parts[0]]
            # Dotted: a.b means attribute 'b' of relation-valued attribute 'a'
            # This is used in aggregate contexts like >. team.salary
            val = t[ref.parts[0]]
            for part in ref.parts[1:]:
                if isinstance(val, Relation):
                    # Can't directly access an attribute of a relation
                    # This should be handled at the aggregate level
                    raise ExecutionError(
                        f"Cannot access .{part} on a relation directly"
                    )
                val = val[part]
            return val
        except KeyError as e:
            raise ExecutionError(f"Unknown attribute: {e}") from e

    def _eval_binop(
        self, expr: ast.BinOp, t: Tuple_, source: Relation | None = None
    ) -> Value:
        """Evaluate a binary arithmetic operation.

        String values are promoted to numbers when possible.
        """
        left = _promote_numeric(self._eval_expr(expr.left, t, source))
        right = _promote_numeric(self._eval_expr(expr.right, t, source))
        return self._apply_binop(expr.op, left, right)

    def _apply_binop(self, op: str, left: Value, right: Value) -> Value:
        """Apply a binary arithmetic operator to two values.

        Date-aware: date +/- int → date, date - date → int (days).
        """
        # --- Date arithmetic ---
        left_is_date = isinstance(left, datetime.date)
        right_is_date = isinstance(right, datetime.date)

        if left_is_date or right_is_date:
            return self._apply_date_binop(op, left, right)

        if isinstance(left, str) or isinstance(right, str):
            raise ExecutionError(
                f"Cannot apply {op} to {left!r} and {right!r}"
                " (non-numeric string)"
            )

        # Harmonise float/Decimal: once a float is involved, go float.
        if isinstance(left, Decimal) and isinstance(right, float):
            left = float(left)
        elif isinstance(right, Decimal) and isinstance(left, float):
            right = float(right)

        ops = {
            "+": lambda a, b: a + b,
            "-": lambda a, b: a - b,
            "*": lambda a, b: a * b,
            "/": lambda a, b: a / b,
            "//": lambda a, b: a // b,
            "%": lambda a, b: a % b,
        }
        if op not in ops:
            raise ExecutionError(f"Unknown operator: {op}")
        return ops[op](left, right)

    def _apply_date_binop(
        self, op: str, left: Value, right: Value
    ) -> Value:
        """Apply arithmetic involving at least one date value.

        Auto-promotes string operands to dates when the other is a date.
        """
        if isinstance(left, datetime.date) and isinstance(right, str):
            right = self._to_date(right)
        elif isinstance(right, datetime.date) and isinstance(left, str):
            left = self._to_date(left)

        left_is_date = isinstance(left, datetime.date)
        right_is_date = isinstance(right, datetime.date)

        if op == "+":
            if left_is_date and right_is_date:
                raise ExecutionError("Cannot add two dates")
            if left_is_date and isinstance(right, int):
                return left + datetime.timedelta(days=right)
            if right_is_date and isinstance(left, int):
                return right + datetime.timedelta(days=left)
        elif op == "-":
            if left_is_date and right_is_date:
                return (left - right).days
            if left_is_date and isinstance(right, int):
                return left - datetime.timedelta(days=right)

        raise ExecutionError(
            f"Cannot apply {op} to {left!r} and {right!r}"
        )

    def _eval_ternary(
        self, expr: ast.TernaryExpr, t: Tuple_, source: Relation | None = None
    ) -> Value:
        """Evaluate a ternary (conditional) expression."""
        predicate = self._compile_condition(expr.condition)
        if predicate(t):
            return self._eval_expr(expr.true_expr, t, source)
        return self._eval_expr(expr.false_expr, t, source)

    def _apply_round(self, value: Value, places: int) -> Decimal:
        """Round a number to the specified decimal places, returning Decimal."""
        rounded = round(float(value), places)
        return Decimal(str(rounded)).quantize(Decimal(10) ** -places)

    def _apply_substring(self, value: Value, start: int, end: int | None) -> str:
        """Extract substring with 1-based inclusive indexing.

        Positive indices count from 1, negative from end.
        Out-of-bounds indices are clamped silently.
        """
        s = str(value)
        length = len(s)

        # Convert 1-based to 0-based.
        if start > 0:
            idx_start = start - 1
        else:
            idx_start = length + start
        idx_start = max(0, min(idx_start, length))

        if end is None:
            idx_end = length
        elif end > 0:
            idx_end = end
        else:
            idx_end = length + end + 1
        idx_end = max(0, min(idx_end, length))

        return s[idx_start:idx_end]

    _STRING_OPS: dict[str, str] = {
        "upper": "upper",
        "lower": "lower",
        "title": "title",
        "cap": "cap",
        "trim": "trim",
        "rtrim": "rtrim",
        "ltrim": "ltrim",
        "len": "len",
    }

    def _apply_string_op(self, value: Value, op: str) -> Value:
        """Apply a string transform keyword."""
        s = str(value)
        if op == "upper":
            return s.upper()
        if op == "lower":
            return s.lower()
        if op == "title":
            return s.title()
        if op == "cap":
            return s[:1].upper() + s[1:].lower() if s else s
        if op == "trim":
            return s.strip()
        if op == "rtrim":
            return s.rstrip()
        if op == "ltrim":
            return s.lstrip()
        if op == "len":
            return len(s)
        raise ExecutionError(
            f"Unknown string operation: {op!r} "
            f"(expected {', '.join(sorted(self._STRING_OPS))})"
        )

    # --- Format string ---

    _FORMAT_REF_RE = re.compile(r"\{([^}]+)\}")

    def _apply_format_str(self, template: str, t: Tuple_) -> str:
        """Resolve {attr} and {attr:fmt} references in a template string.

        Supports Python format mini-language after the colon:
            {n}          plain value
            {n:05d}      zero-padded integer, width 5
            {n:>10}      right-aligned, width 10
            {n:.2f}      float with 2 decimal places
        """
        from codd.repl.formatter import format_value

        def _replace(match: re.Match[str]) -> str:
            spec = match.group(1)
            if ":" in spec:
                attr, fmt = spec.split(":", 1)
            else:
                attr, fmt = spec, ""
            attr = attr.strip()
            try:
                val = t[attr]
            except KeyError:
                raise ExecutionError(
                    f"Unknown attribute {attr!r} in format string"
                )
            if fmt:
                try:
                    return format(val, fmt)
                except (ValueError, TypeError) as e:
                    raise ExecutionError(
                        f"Invalid format spec {fmt!r} for value {val!r}: {e}"
                    )
            return format_value(val)

        return self._FORMAT_REF_RE.sub(_replace, template)

    # --- Regex replace ---

    def _apply_regex_replace(
        self, value: str, pattern: str, replacement: str
    ) -> str:
        """Apply regex substitution: re.sub(pattern, replacement, value)."""
        try:
            return re.sub(pattern, replacement, value)
        except re.error as e:
            raise ExecutionError(f".r: invalid regex {pattern!r}: {e}") from e

    # --- Type cast ---

    def _apply_type_cast(self, value: Value, target_type: str) -> Value:
        """Coerce a value to the specified type.

        Resolves user-defined type aliases via the environment before
        coercing.  Supports decimal(N) for parameterised precision.
        """
        from codd.model.coerce import (
            coerce_value,
            CoercionError,
            BUILTIN_TYPES,
            resolve_type_alias,
            parse_type_string,
        )

        try:
            resolved = resolve_type_alias(target_type, self._env)
            base_type, constraint = parse_type_string(resolved)
        except CoercionError as e:
            raise ExecutionError(f".as: {e}") from e
        if base_type == "in":
            raise ExecutionError(
                f".as: cannot cast to an in() constraint ({resolved!r})"
            )
        precision: int | None = None
        if base_type == "decimal" and constraint is not None:
            precision = int(constraint[1])
        if base_type not in BUILTIN_TYPES:
            raise ExecutionError(
                f".as: unknown type {target_type!r}"
                f" (expected one of {', '.join(sorted(BUILTIN_TYPES))}"
                " or a user-defined type)"
            )
        try:
            return coerce_value(value, base_type, precision=precision)
        except CoercionError as e:
            raise ExecutionError(f".as: {e}") from e

    # --- Date operations ---

    _DATE_COMPONENTS: dict[str, str] = {
        "year": "year",
        "month": "month",
        "day": "day",
        "week": "week",
        "ww": "ww",
        "dow": "dow",
        "q": "q",
        "qq": "qq",
    }

    _MONTH_ABBR = [
        "", "JAN", "FEB", "MAR", "APR", "MAY", "JUN",
        "JUL", "AUG", "SEP", "OCT", "NOV", "DEC",
    ]

    _DAY_ABBR = ["MON", "TUE", "WED", "THU", "FRI", "SAT", "SUN"]

    def _apply_date_op(self, value: Value, fmt: str | None) -> Value:
        """Apply the .d operator: promotion, extraction, or formatting.

        fmt=None: promote string to datetime.date.
        fmt=keyword: extract integer component.
        fmt=pattern with {}: format as string.
        """
        d = self._to_date(value)
        if fmt is None:
            return d
        if fmt in self._DATE_COMPONENTS:
            return self._extract_date_component(d, fmt)
        if "{" in fmt:
            return self._format_date(d, fmt)
        raise ExecutionError(
            f"Unknown date format: {fmt!r} (use a component keyword "
            "or a {{...}} format pattern)"
        )

    def _to_date(self, value: Value) -> datetime.date:
        """Convert a value to datetime.date."""
        if isinstance(value, datetime.date):
            return value
        if isinstance(value, str):
            try:
                return str_to_date(value)
            except ValueError as e:
                raise ExecutionError(
                    f"Cannot parse date: {value!r} (expected YYYY-MM-DD)"
                ) from e
        raise ExecutionError(
            f"Cannot convert {type(value).__name__} to date: {value!r}"
        )

    def _extract_date_component(self, d: datetime.date, component: str) -> int:
        """Extract an integer component from a date."""
        if component == "year":
            return d.year
        if component == "month":
            return d.month
        if component == "day":
            return d.day
        if component == "week":
            return d.isocalendar().week
        if component == "ww":
            return f"{d.isocalendar().week:02d}"
        if component == "dow":
            return d.isoweekday()
        if component == "q":
            return (d.month - 1) // 3 + 1
        if component == "qq":
            return f"Q{(d.month - 1) // 3 + 1}"
        raise ExecutionError(f"Unknown date component: {component!r}")

    _FORMAT_TOKEN_RE = re.compile(r"\{(\w+)\}")

    def _format_date(self, d: datetime.date, pattern: str) -> str:
        """Format a date using a {token} pattern."""

        def _replace(match: re.Match[str]) -> str:
            token = match.group(1)
            if token == "d":
                return str(d.day)
            if token == "dd":
                return f"{d.day:02d}"
            if token == "m":
                return str(d.month)
            if token == "mm":
                return f"{d.month:02d}"
            if token == "mmm":
                return self._MONTH_ABBR[d.month]
            if token == "yy":
                return f"{d.year % 100:02d}"
            if token == "yyyy":
                return str(d.year)
            if token == "week":
                return str(d.isocalendar().week)
            if token == "ww":
                return f"{d.isocalendar().week:02d}"
            if token == "dow":
                return str(d.isoweekday())
            if token == "ddd":
                return self._DAY_ABBR[d.isoweekday() - 1]
            if token == "q":
                return str((d.month - 1) // 3 + 1)
            if token == "qq":
                return f"Q{(d.month - 1) // 3 + 1}"
            raise ExecutionError(f"Unknown date format token: {{{token}}}")

        return self._FORMAT_TOKEN_RE.sub(_replace, pattern)

    def _eval_aggregate_call(
        self, expr: ast.AggregateCall, t: Tuple_, source: Relation | None = None
    ) -> Value:
        """Evaluate an aggregate function call in extend context."""
        # p. (percent) uses the enclosing source relation as the whole.
        if expr.func == "p.":
            if expr.source is not None:
                # Explicit source: p. E salary
                whole_rel = self._as_relation(expr.source)
            elif source is not None:
                # Implicit source from extend context
                whole_rel = source
            else:
                raise ExecutionError(
                    "p. requires a source relation in this context"
                )
            attr_name = expr.arg.parts[0] if expr.arg else None
            # In extend, the "group" is a single tuple.
            single = Relation(frozenset({t}))
            return agg_percent(single, attr_name, whole_rel)

        agg_fn = get_aggregate(expr.func)

        if expr.source is not None:
            # Source is specified: evaluate it
            if isinstance(expr.source, ast.RelName):
                # Could be a reference to a tuple attribute (RVA)
                name = expr.source.name
                if name in t:
                    source_rel = t[name]
                    if not isinstance(source_rel, Relation):
                        raise ExecutionError(
                            f"{name} is not a relation-valued attribute"
                        )
                else:
                    source_rel = self._as_relation(expr.source)
            else:
                # Complex expression — evaluate it
                source_rel = self._eval_rel_expr_in_tuple_context(expr.source, t)
                if not isinstance(source_rel, Relation):
                    raise ExecutionError("Aggregate source must be a relation")
            attr_name = expr.arg.parts[0] if expr.arg else None
            return agg_fn(source_rel, attr_name)

        if expr.arg is not None:
            # Simple aggregate on an attribute — this shouldn't happen in extend
            # context without a source. Return the attr value.
            attr_name = expr.arg.parts[0] if expr.arg else None
            raise ExecutionError(
                f"Aggregate {expr.func} needs a relation source in extend context"
            )

        # Count with no source — shouldn't happen in extend context
        raise ExecutionError(
            f"Aggregate {expr.func} needs a relation source in extend context"
        )

    def _eval_rel_expr_in_tuple_context(
        self, node: ast.RelExpr, t: Tuple_
    ) -> Relation | list[Tuple_]:
        """Evaluate a relational expression where RelName might refer to a tuple attribute."""
        if isinstance(node, ast.RelName):
            name = node.name
            if name in t:
                val = t[name]
                if isinstance(val, Relation):
                    return val
                raise ExecutionError(f"{name} is not a relation")
            return self._env.lookup(name)
        if isinstance(node, ast.Filter):
            source = self._eval_rel_expr_in_tuple_context(node.source, t)
            if not isinstance(source, Relation):
                raise ExecutionError("Filter source must be a relation")
            predicate = self._compile_condition(node.condition)
            return source.where(predicate)
        if isinstance(node, ast.Project):
            source = self._eval_rel_expr_in_tuple_context(node.source, t)
            if not isinstance(source, Relation):
                raise ExecutionError("Project source must be a relation")
            return source.project(frozenset(node.attrs))
        # Fall back to normal evaluation
        return self._eval_rel(node)

    # --- Condition compilation ---

    def _compile_condition(self, cond: ast.Condition):
        """Compile a condition AST node into a predicate function."""
        if isinstance(cond, ast.Comparison):
            return self._compile_comparison(cond)
        if isinstance(cond, ast.MembershipTest):
            return self._compile_membership(cond)
        if isinstance(cond, ast.BoolCombination):
            left_fn = self._compile_condition(cond.left)
            right_fn = self._compile_condition(cond.right)
            if cond.op == "&":
                return lambda t: left_fn(t) and right_fn(t)
            if cond.op == "|":
                return lambda t: left_fn(t) or right_fn(t)
            raise ExecutionError(f"Unknown boolean operator: {cond.op}")
        raise ExecutionError(f"Unknown condition type: {type(cond).__name__}")

    def _compile_comparison(self, comp: ast.Comparison):
        """Compile a comparison into a predicate function."""
        if isinstance(comp.left, ast.AggregateCall):
            agg_node = comp.left

            def get_left(t: Tuple_) -> Value:
                return self._eval_aggregate_call(agg_node, t)
        elif isinstance(comp.left, ast.AttrRef):
            attr_parts = comp.left.parts

            def get_left(t: Tuple_) -> Value:
                val = t[attr_parts[0]]
                for part in attr_parts[1:]:
                    val = val[part]
                return val
        else:
            # General expression LHS (e.g. name .s "lower").
            lhs_expr = comp.left

            def get_left(t: Tuple_) -> Value:
                return self._eval_expr(lhs_expr, t, None)

        right_expr = comp.right
        op = comp.op

        # Pre-evaluate constant RHS
        if isinstance(right_expr, ast.IntLiteral):
            rval = right_expr.value
            return _make_scalar_cmp(get_left, op, rval)
        if isinstance(right_expr, ast.FloatLiteral):
            rval = right_expr.value
            return _make_scalar_cmp(get_left, op, rval)
        if isinstance(right_expr, ast.StringLiteral):
            rval = right_expr.value
            return _make_scalar_cmp(get_left, op, rval)
        if isinstance(right_expr, ast.BoolLiteral):
            rval = right_expr.value
            return _make_scalar_cmp(get_left, op, rval)
        if isinstance(right_expr, ast.SetLiteral):
            # Set membership
            elements = set()
            for elem in right_expr.elements:
                if isinstance(elem, ast.IntLiteral):
                    elements.add(elem.value)
                elif isinstance(elem, ast.FloatLiteral):
                    elements.add(elem.value)
                elif isinstance(elem, ast.StringLiteral):
                    elements.add(elem.value)
                else:
                    raise ExecutionError("Set literal elements must be constants")
            if op == "=":
                return lambda t: get_left(t) in elements
            if op == "!=":
                return lambda t: get_left(t) not in elements
            raise ExecutionError(f"Cannot use {op} with set literals")
        if isinstance(right_expr, ast.AttrRef):
            right_parts = right_expr.parts
            def get_right(t: Tuple_) -> Value:
                val = t[right_parts[0]]
                for part in right_parts[1:]:
                    val = val[part]
                return val
            return _make_dynamic_cmp(get_left, op, get_right)
        if isinstance(right_expr, ast.SubqueryExpr):
            # Evaluate subquery and check membership or scalar comparison.
            result = self._as_relation(right_expr.query)
            # The subquery result should be a single-attribute relation.
            if len(result.attributes) != 1:
                raise ExecutionError(
                    "Subquery in filter must return a single attribute"
                )
            attr = next(iter(result.attributes))
            # A 1x1 subquery is a scalar: unwrap and compare normally.
            if len(result) == 1:
                rval = next(iter(result))[attr]
                return _make_scalar_cmp(get_left, op, rval)
            values = {t[attr] for t in result}
            if op == "=":
                return lambda t: get_left(t) in values
            if op == "!=":
                return lambda t: get_left(t) not in values
            raise ExecutionError(
                f"Cannot use {op} with a multi-row subquery "
                "(only = and != are set-membership; for scalar comparison "
                "the subquery must return exactly one row)"
            )
        # Fallback: evaluate as a constant scalar expression (e.g. "today" .d - 14).
        dummy = Tuple_({})
        rval = self._eval_expr(right_expr, dummy, None)
        return _make_scalar_cmp(get_left, op, rval)

    def _compile_membership(self, node: ast.MembershipTest):
        """Compile: value in. rel_expr — membership test.

        The RHS must evaluate to a single-column relation.  The LHS
        can be an attribute reference, literal, or scalar expression.
        """
        # Evaluate the RHS relation once (eagerly).
        rel = self._as_relation(node.rel_expr)
        if len(rel.attributes) != 1:
            raise ExecutionError(
                f"in. requires a single-column relation, "
                f"got {len(rel.attributes)} columns: {sorted(rel.attributes)}"
            )
        attr = next(iter(rel.attributes))
        member_values = [t[attr] for t in rel]
        member_set = frozenset(member_values)  # fast path (exact match)
        negated = node.negated

        def _is_member(val: Value) -> bool:
            """Check membership with coercion fallback.

            Try the O(1) frozenset lookup first.  If that misses, fall back
            to a coercion-aware linear scan so that, e.g., the string "42"
            and the integer 42 are treated as equal (matching natural join).
            """
            if val in member_set:
                return True
            return any(_values_equal(val, m) for m in member_values)

        left = node.left
        if isinstance(left, ast.AttrRef):
            parts = left.parts

            def predicate(t: Tuple_) -> bool:
                val = t[parts[0]]
                for p in parts[1:]:
                    val = val[p]
                result = _is_member(val)
                return not result if negated else result
        elif isinstance(left, (ast.StringLiteral, ast.IntLiteral,
                               ast.FloatLiteral, ast.BoolLiteral)):
            # Constant LHS — evaluate once.
            const_result = _is_member(left.value)
            if negated:
                const_result = not const_result

            def predicate(t: Tuple_) -> bool:
                return const_result
        else:
            # General expression LHS.
            expr = left

            def predicate(t: Tuple_) -> bool:
                val = self._eval_expr(expr, t, None)
                result = _is_member(val)
                return not result if negated else result

        return predicate


class _ReverseKey:
    """Wrapper for reverse-sorting non-numeric types."""

    __slots__ = ("_val",)

    def __init__(self, val: object) -> None:
        self._val = val

    def __lt__(self, other: _ReverseKey) -> bool:
        return self._val > other._val

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, _ReverseKey):
            return NotImplemented
        return self._val == other._val

    def __le__(self, other: _ReverseKey) -> bool:
        return self._val >= other._val


def _coerce_pair(a: Value, b: Value) -> tuple[Value, Value]:
    """Promote strings to match a numeric or date counterpart for comparison.

    If one side is numeric and the other is a string, promote the string.
    If both are strings, promote both (enables numeric comparison on str columns).
    If one side is a date and the other is a date-like string, promote the string.
    """
    if isinstance(a, datetime.date) and isinstance(b, str):
        try:
            return a, str_to_date(b)
        except ValueError:
            return a, b
    if isinstance(b, datetime.date) and isinstance(a, str):
        try:
            return str_to_date(a), b
        except ValueError:
            return a, b
    if isinstance(a, str) and isinstance(b, (int, float, Decimal)):
        return _promote_numeric(a), b
    if isinstance(b, str) and isinstance(a, (int, float, Decimal)):
        return a, _promote_numeric(b)
    if isinstance(a, str) and isinstance(b, str):
        return _promote_numeric(a), _promote_numeric(b)
    return a, b


def _combine_schemas(
    base: dict[str, str] | None, extra: dict[str, str] | None
) -> dict[str, str] | None:
    """Merge two optional schema dicts."""
    if base is None and extra is None:
        return None
    merged: dict[str, str] = {}
    if base:
        merged.update(base)
    if extra:
        merged.update(extra)
    return merged if merged else None


def _make_scalar_cmp(get_left, op: str, rval: Value):
    """Create a comparison predicate with a constant RHS."""
    if op in ("=~", "!=~"):
        return _make_regex_cmp(get_left, op, rval)
    cmp_ops = {
        "=": lambda a, b: a == b,
        "!=": lambda a, b: a != b,
        ">": lambda a, b: a > b,
        "<": lambda a, b: a < b,
        ">=": lambda a, b: a >= b,
        "<=": lambda a, b: a <= b,
    }
    fn = cmp_ops[op]

    # Coerce types for comparison (numeric promotion, date promotion).
    def pred(t: Tuple_) -> bool:
        lval, rv = _coerce_pair(get_left(t), rval)
        return fn(lval, rv)
    return pred


def _make_dynamic_cmp(get_left, op: str, get_right):
    """Create a comparison predicate with a dynamic RHS."""
    if op in ("=~", "!=~"):
        negate = op == "!=~"

        def regex_pred(t: Tuple_) -> bool:
            pattern = str(get_right(t))
            try:
                match = bool(re.search(pattern, str(get_left(t))))
            except re.error as e:
                raise ExecutionError(f"Invalid regex pattern: {pattern!r} ({e})")
            return not match if negate else match
        return regex_pred
    cmp_ops = {
        "=": lambda a, b: a == b,
        "!=": lambda a, b: a != b,
        ">": lambda a, b: a > b,
        "<": lambda a, b: a < b,
        ">=": lambda a, b: a >= b,
        "<=": lambda a, b: a <= b,
    }
    fn = cmp_ops[op]

    def pred(t: Tuple_) -> bool:
        lval, rval = _coerce_pair(get_left(t), get_right(t))
        return fn(lval, rval)
    return pred


def _make_regex_cmp(get_left, op: str, pattern_val: Value):
    """Create a regex match predicate with a pre-compiled pattern."""
    negate = op == "!=~"
    try:
        compiled = re.compile(str(pattern_val))
    except re.error as e:
        raise ExecutionError(f"Invalid regex pattern: {pattern_val!r} ({e})")

    def pred(t: Tuple_) -> bool:
        match = bool(compiled.search(str(get_left(t))))
        return not match if negate else match
    return pred
