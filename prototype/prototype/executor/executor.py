"""Tree-walking executor for the relational algebra AST.

Evaluates AST nodes against an Environment of named relations.
Uses isinstance dispatch (visitor-style without accept methods).
"""

from __future__ import annotations

from decimal import Decimal

from prototype.executor.aggregates import _promote_numeric, get_aggregate
from prototype.executor.environment import Environment
from prototype.model.relation import Relation
from prototype.model.types import Tuple_, Value
from prototype.parser import ast_nodes as ast


class ExecutionError(Exception):
    """Raised on execution errors."""


_FUNCTION_REGISTRY: dict[str, callable] = {
    "round": lambda args: (
        Decimal(str(round(float(args[0]), args[1])))
        if isinstance(args[0], Decimal)
        else round(args[0], args[1])
    ),
}


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
        if isinstance(node, ast.Take):
            return self._eval_take(node)
        raise ExecutionError(f"Unknown node type: {type(node).__name__}")

    def _as_relation(self, node: ast.RelExpr) -> Relation:
        """Evaluate a node and assert it returns a Relation."""
        result = self._eval_rel(node)
        if not isinstance(result, Relation):
            raise ExecutionError("Expected a relation, got an array (did you sort?)")
        return result

    # --- Node evaluators ---

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
                result[comp.name] = self._eval_expr(comp.expr, t)
            return result

        return source.extend(compute)

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
        """Evaluate: source / group_attrs [aggregates]."""
        source = self._as_relation(node.source)
        agg_fns: dict[str, callable] = {}
        for agg in node.aggregates:
            agg_fn = get_aggregate(agg.func)
            attr = agg.attr

            if agg.source is not None:
                # Conditional aggregation or dotted: source provides the relation
                src_node = agg.source
                def make_fn(fn, a, src):
                    def f(group_rel: Relation) -> Value:
                        # In summarize context, the source is evaluated relative
                        # to the group members, not the environment.
                        # For simple summarize, we just use group_rel directly.
                        return fn(group_rel, a)
                    return f
                agg_fns[agg.name] = make_fn(agg_fn, attr, src_node)
            else:
                def make_fn(fn, a):
                    def f(group_rel: Relation) -> Value:
                        return fn(group_rel, a)
                    return f
                agg_fns[agg.name] = make_fn(agg_fn, attr)

        return source.summarize(frozenset(node.group_attrs), agg_fns)

    def _eval_summarize_all(self, node: ast.SummarizeAll) -> Relation:
        """Evaluate: source /. [aggregates]."""
        source = self._as_relation(node.source)
        agg_fns: dict[str, callable] = {}
        for agg in node.aggregates:
            agg_fn = get_aggregate(agg.func)
            attr = agg.attr

            def make_fn(fn, a):
                def f(rel: Relation) -> Value:
                    return fn(rel, a)
                return f
            agg_fns[agg.name] = make_fn(agg_fn, attr)

        return source.summarize_all(agg_fns)

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

    def _eval_take(self, node: ast.Take) -> list[Tuple_]:
        """Evaluate: source ^ N."""
        source = self._eval_rel(node.source)
        if isinstance(source, Relation):
            return list(source)[: node.count]
        if isinstance(source, list):
            return source[: node.count]
        raise ExecutionError("^ (take) requires a relation or sorted array")

    # --- Expression evaluation ---

    def _eval_expr(self, expr: ast.Expr, t: Tuple_) -> Value:
        """Evaluate a scalar expression in the context of a tuple."""
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
            return self._eval_binop(expr, t)
        if isinstance(expr, ast.AggregateCall):
            return self._eval_aggregate_call(expr, t)
        if isinstance(expr, ast.SubqueryExpr):
            return self._as_relation(expr.query)
        if isinstance(expr, ast.TernaryExpr):
            return self._eval_ternary(expr, t)
        if isinstance(expr, ast.FunctionCall):
            return self._eval_function_call(expr, t)
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

    def _eval_binop(self, expr: ast.BinOp, t: Tuple_) -> Value:
        """Evaluate a binary arithmetic operation.

        String values are promoted to numbers when possible.
        """
        left = _promote_numeric(self._eval_expr(expr.left, t))
        right = _promote_numeric(self._eval_expr(expr.right, t))

        if isinstance(left, str) or isinstance(right, str):
            raise ExecutionError(
                f"Cannot apply {expr.op} to {left!r} and {right!r}"
                " (non-numeric string)"
            )

        ops = {
            "+": lambda a, b: a + b,
            "-": lambda a, b: a - b,
            "*": lambda a, b: a * b,
            "/": lambda a, b: a / b if isinstance(a, (float, Decimal)) or isinstance(b, (float, Decimal)) else a // b,
        }
        if expr.op not in ops:
            raise ExecutionError(f"Unknown operator: {expr.op}")
        return ops[expr.op](left, right)

    def _eval_ternary(self, expr: ast.TernaryExpr, t: Tuple_) -> Value:
        """Evaluate a ternary (conditional) expression."""
        predicate = self._compile_comparison(expr.condition)
        if predicate(t):
            return self._eval_expr(expr.true_expr, t)
        return self._eval_expr(expr.false_expr, t)

    def _eval_function_call(self, expr: ast.FunctionCall, t: Tuple_) -> Value:
        """Evaluate a function call expression."""
        fn = _FUNCTION_REGISTRY.get(expr.name)
        if fn is None:
            raise ExecutionError(f"Unknown function: {expr.name!r}")
        evaluated_args = [self._eval_expr(arg, t) for arg in expr.args]
        return fn(evaluated_args)

    def _eval_aggregate_call(self, expr: ast.AggregateCall, t: Tuple_) -> Value:
        """Evaluate an aggregate function call in extend context."""
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
    """Promote strings to match a numeric counterpart for comparison.

    If one side is numeric and the other is a string, promote the string.
    If both are strings, promote both (enables numeric comparison on str columns).
    """
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

    if isinstance(rval, (int, float, Decimal)):
        # RHS is numeric — promote LHS strings for comparison
        def pred(t: Tuple_) -> bool:
            lval, rv = _coerce_pair(get_left(t), rval)
            return fn(lval, rv)
        return pred

    return lambda t: fn(get_left(t), rval)


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
