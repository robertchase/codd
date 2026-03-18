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
from codd.model.types import OrderedArray, Tuple_, Value
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
        if isinstance(node, ast.NestBy):
            return self._eval_nest_by(node)
        if isinstance(node, ast.Sort):
            return self._eval_sort(node)
        if isinstance(node, ast.OrderColumns):
            return self._eval_order_columns(node)
        if isinstance(node, ast.Take):
            return self._eval_take(node)
        if isinstance(node, ast.Iota):
            return self._eval_iota(node)
        raise ExecutionError(f"Unknown node type: {type(node).__name__}")

    def _as_relation(self, node: ast.RelExpr) -> Relation:
        """Evaluate a node and assert it returns a Relation."""
        result = self._eval_rel(node)
        if not isinstance(result, Relation):
            raise ExecutionError("Expected a relation, got an array (did you sort?)")
        return result

    # --- Node evaluators ---

    def _eval_iota(self, node: ast.Iota) -> Relation:
        """Evaluate: i. [name:] count.

        Generate a single-attribute relation with integers 1..count.
        """
        tuples = frozenset(
            Tuple_({node.name: i}) for i in range(1, node.count + 1)
        )
        return Relation(tuples, attributes=frozenset({node.name}))

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

    def _eval_nest_join(self, node: ast.NestJoin) -> Relation:
        """Evaluate: source *: right > name."""
        left = self._as_relation(node.source)
        right = self._as_relation(node.right)
        return left.nest_join(right, node.nest_name)

    def _eval_unnest(self, node: ast.Unnest) -> Relation:
        """Evaluate: source <: nest_attr."""
        source = self._as_relation(node.source)
        return source.unnest(node.nest_attr)

    def _eval_extend(self, node: ast.Extend) -> Relation:
        """Evaluate: source + computations."""
        source = self._as_relation(node.source)

        def compute(t: Tuple_) -> dict[str, Value]:
            result: dict[str, Value] = {}
            for comp in node.computations:
                result[comp.name] = self._eval_expr(comp.expr, t, source)
            return result

        return source.extend(compute)

    def _eval_modify(self, node: ast.Modify) -> Relation:
        """Evaluate: source =: computations (update existing attributes)."""
        source = self._as_relation(node.source)

        def compute(t: Tuple_) -> dict[str, Value]:
            result: dict[str, Value] = {}
            for comp in node.computations:
                result[comp.name] = self._eval_expr(comp.expr, t, source)
            return result

        return source.modify(compute)

    def _eval_rename(self, node: ast.Rename) -> Relation:
        """Evaluate: source @ mappings."""
        source = self._as_relation(node.source)
        mapping = dict(node.mappings)
        return source.rename(mapping)

    def _eval_union(self, node: ast.Union) -> Relation:
        """Evaluate: source | right."""
        left = self._as_relation(node.source)
        right = self._as_relation(node.right)
        return left.union(right)

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

        return source.summarize(frozenset(node.group_attrs), agg_fns)

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

        return source.summarize_all(agg_fns)

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
        if isinstance(expr, ast.DateOp):
            value = self._eval_summarize_expr(expr.expr, group_rel, whole_rel)
            return self._apply_date_op(value, expr.fmt)
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
        """Evaluate: source /: group_attrs > name."""
        source = self._as_relation(node.source)
        return source.nest_by(frozenset(node.group_attrs), node.nest_name)

    def _eval_sort(self, node: ast.Sort) -> list[Tuple_]:
        """Evaluate: source $ keys."""
        source = self._as_relation(node.source)
        keys = node.keys

        def sort_key(t: Tuple_) -> tuple:
            parts = []
            for k in keys:
                val = t[k.attr]
                if k.descending:
                    # Negate for numeric types, reverse for strings
                    if isinstance(val, (int, float, Decimal)):
                        parts.append(-val)
                    else:
                        # For strings, we use a wrapper that reverses comparison
                        parts.append(_ReverseKey(val))
                else:
                    parts.append(val)
            return tuple(parts)

        return source.sort(sort_key)

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
            available = source.attributes
        elif isinstance(source, list):
            tuples = source
            available = tuples[0].attributes() if tuples else frozenset()
        else:
            raise ExecutionError("$. (order columns) requires a relation or list")

        # Validate all columns exist.
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
        if isinstance(expr, ast.DateOp):
            value = self._eval_expr(expr.expr, t, source)
            return self._apply_date_op(value, expr.fmt)
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
        }
        if op not in ops:
            raise ExecutionError(f"Unknown operator: {op}")
        return ops[op](left, right)

    def _apply_date_binop(
        self, op: str, left: Value, right: Value
    ) -> Value:
        """Apply arithmetic involving at least one date value."""
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
        predicate = self._compile_comparison(expr.condition)
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

    # --- Date operations ---

    _DATE_COMPONENTS: dict[str, str] = {
        "year": "year",
        "month": "month",
        "day": "day",
        "week": "week",
        "dow": "dow",
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
            if value == "today":
                return datetime.date.today()
            try:
                return datetime.date.fromisoformat(value)
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
        if component == "dow":
            return d.isoweekday()
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
            if token == "dow":
                return str(d.isoweekday())
            if token == "ddd":
                return self._DAY_ABBR[d.isoweekday() - 1]
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
        else:
            attr_parts = comp.left.parts

            def get_left(t: Tuple_) -> Value:
                val = t[attr_parts[0]]
                for part in attr_parts[1:]:
                    val = val[part]
                return val

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
            # Evaluate subquery and check membership
            result = self._as_relation(right_expr.query)
            # The subquery result should be a single-attribute relation
            if len(result.attributes) != 1:
                raise ExecutionError(
                    "Subquery in filter must return a single attribute"
                )
            attr = next(iter(result.attributes))
            values = {t[attr] for t in result}
            if op == "=":
                return lambda t: get_left(t) in values
            if op == "!=":
                return lambda t: get_left(t) not in values
            raise ExecutionError(f"Cannot use {op} with subquery")
        raise ExecutionError(f"Unknown RHS type: {type(right_expr).__name__}")


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
            return a, datetime.date.fromisoformat(b)
        except ValueError:
            return a, b
    if isinstance(b, datetime.date) and isinstance(a, str):
        try:
            return datetime.date.fromisoformat(a), b
        except ValueError:
            return a, b
    if isinstance(a, str) and isinstance(b, (int, float, Decimal)):
        return _promote_numeric(a), b
    if isinstance(b, str) and isinstance(a, (int, float, Decimal)):
        return a, _promote_numeric(b)
    if isinstance(a, str) and isinstance(b, str):
        return _promote_numeric(a), _promote_numeric(b)
    return a, b


def _make_scalar_cmp(get_left, op: str, rval: Value):
    """Create a comparison predicate with a constant RHS."""
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
