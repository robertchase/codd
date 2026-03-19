"""AST node dataclasses for the relational algebra parser."""

from __future__ import annotations

from dataclasses import dataclass, field


# --- Expressions (compute scalar values) ---


@dataclass(frozen=True)
class IntLiteral:
    """Integer literal."""

    value: int


@dataclass(frozen=True)
class FloatLiteral:
    """Float literal."""

    value: float


@dataclass(frozen=True)
class StringLiteral:
    """String literal."""

    value: str


@dataclass(frozen=True)
class BoolLiteral:
    """Boolean literal."""

    value: bool


@dataclass(frozen=True)
class AttrRef:
    """Attribute reference, e.g. 'salary' or 'team.salary'."""

    parts: tuple[str, ...]

    @property
    def name(self) -> str:
        """Return the full dotted name."""
        return ".".join(self.parts)


@dataclass(frozen=True)
class BinOp:
    """Binary arithmetic operation inside extend expressions.

    op is one of: +, -, *, /
    """

    left: Expr
    op: str
    right: Expr


@dataclass(frozen=True)
class SetLiteral:
    """Set literal: {10, 20, 30}."""

    elements: tuple[Expr, ...]


@dataclass(frozen=True)
class AggregateCall:
    """Aggregate function call: #. or +. salary or %. salary.

    func is one of: #., +., >., <., %.
    arg is the attribute to aggregate over (None for #. which counts tuples).
    If source is set, it's an expression providing the relation to aggregate
    (e.g., `team` in `#. team` or `(team ? role = "engineer")`).
    """

    func: str
    arg: AttrRef | None = None
    source: RelExpr | None = None


@dataclass(frozen=True)
class SubqueryExpr:
    """A parenthesized relational expression used as a scalar value (e.g., in filter RHS)."""

    query: RelExpr


@dataclass(frozen=True)
class TernaryExpr:
    """Conditional expression: ? condition true_expr false_expr."""

    condition: Comparison
    true_expr: Expr
    false_expr: Expr


@dataclass(frozen=True)
class Round:
    """Precision primitive: expr ~ N."""

    expr: Expr
    places: int


@dataclass(frozen=True)
class Substring:
    """Substring primitive: expr .s [start] or expr .s [start end].

    1-based inclusive indexing, negative indices count from end.
    """

    expr: Expr
    start: int
    end: int | None = None


@dataclass(frozen=True)
class DateOp:
    """Date operator: expr .d [fmt].

    fmt=None: type promotion (string → Date).
    fmt=keyword (no braces): component extraction → int.
    fmt=pattern (contains {): formatting → str.
    """

    expr: Expr
    fmt: str | None = None


# Expr is the union of all expression types
Expr = (
    IntLiteral
    | FloatLiteral
    | StringLiteral
    | BoolLiteral
    | AttrRef
    | BinOp
    | SetLiteral
    | AggregateCall
    | SubqueryExpr
    | TernaryExpr
    | Round
    | Substring
    | DateOp
)


# --- Conditions (inside filters) ---


@dataclass(frozen=True)
class Comparison:
    """A comparison: left op value.

    left can be an attribute reference or an aggregate call (e.g. #. phones).
    op is one of: =, !=, >, <, >=, <=
    """

    left: AttrRef | AggregateCall
    op: str
    right: Expr


@dataclass(frozen=True)
class BoolCombination:
    """Boolean combination of conditions: left & right or left | right."""

    left: Condition
    op: str  # "&" or "|"
    right: Condition


Condition = Comparison | BoolCombination


# --- Relational expressions (chain operations on relations) ---


@dataclass(frozen=True)
class RelName:
    """A named relation variable."""

    name: str


@dataclass(frozen=True)
class Filter:
    """Filter: ? condition."""

    source: RelExpr
    condition: Condition


@dataclass(frozen=True)
class NegatedFilter:
    """Negated filter: ?! condition."""

    source: RelExpr
    condition: Condition


@dataclass(frozen=True)
class Project:
    """Project: # attr or # [attr1 attr2]."""

    source: RelExpr
    attrs: tuple[str, ...]


@dataclass(frozen=True)
class Remove:
    """Remove: #! attr or #! [attr1 attr2]."""

    source: RelExpr
    attrs: tuple[str, ...]


@dataclass(frozen=True)
class NaturalJoin:
    """Natural join: * RelName."""

    source: RelExpr
    right: RelExpr


@dataclass(frozen=True)
class NestJoin:
    """Nest join: *: RelName > nest_name."""

    source: RelExpr
    right: RelExpr
    nest_name: str


@dataclass(frozen=True)
class Unnest:
    """Unnest: <: attr_name — flatten a relation-valued attribute."""

    source: RelExpr
    nest_attr: str


@dataclass(frozen=True)
class NamedExpr:
    """A named computed expression: name: expr."""

    name: str
    expr: Expr


@dataclass(frozen=True)
class Extend:
    """Extend: + name: expr or + [name1: expr1  name2: expr2]."""

    source: RelExpr
    computations: tuple[NamedExpr, ...]


@dataclass(frozen=True)
class Modify:
    """Modify: =: name: expr or =: [name1: expr1  name2: expr2]."""

    source: RelExpr
    computations: tuple[NamedExpr, ...]


@dataclass(frozen=True)
class Rename:
    """Rename: @ old > new or @ [old1 > new1  old2 > new2]."""

    source: RelExpr
    mappings: tuple[tuple[str, str], ...]  # (old_name, new_name) pairs


@dataclass(frozen=True)
class Union:
    """Union: | (right_expr)."""

    source: RelExpr
    right: RelExpr


@dataclass(frozen=True)
class Difference:
    """Difference: - (right_expr)."""

    source: RelExpr
    right: RelExpr


@dataclass(frozen=True)
class Intersect:
    """Intersect: & (right_expr)."""

    source: RelExpr
    right: RelExpr


@dataclass(frozen=True)
class Summarize:
    """Summarize: / key [name1: expr1  name2: expr2] or / [key1 key2] [exprs]."""

    source: RelExpr
    group_attrs: tuple[str, ...]
    computations: tuple[NamedExpr, ...]


@dataclass(frozen=True)
class SummarizeAll:
    """Summarize all: /. [name1: expr1  name2: expr2]."""

    source: RelExpr
    computations: tuple[NamedExpr, ...]


@dataclass(frozen=True)
class NestBy:
    """Nest by: /: key > name or /: [key1 key2] > name."""

    source: RelExpr
    group_attrs: tuple[str, ...]
    nest_name: str


@dataclass(frozen=True)
class SortKey:
    """A sort key: attr or attr- (descending)."""

    attr: str
    descending: bool = False


@dataclass(frozen=True)
class Sort:
    """Sort: $ key or $ [key1 key2-]."""

    source: RelExpr
    keys: tuple[SortKey, ...]


@dataclass(frozen=True)
class OrderColumns:
    """Order columns: $. [col1 col2 ...] or $. col."""

    source: RelExpr
    columns: tuple[str, ...]


@dataclass(frozen=True)
class Take:
    """Take: ^ N (follows Sort)."""

    source: RelExpr
    count: int


@dataclass(frozen=True)
class Iota:
    """Iota source: i. [name:] count.

    Generates a single-attribute relation with consecutive integers 1..count.
    """

    count: int
    name: str = "i"


@dataclass(frozen=True)
class Rotate:
    """Rotate display: r. — transposes tuples for vertical display."""

    source: RelExpr


@dataclass(frozen=True)
class RelationLiteral:
    """Inline relation literal: {header; row; row; ...}.

    Header is a tuple of attribute names.
    Each row is a tuple of literal values (str, int, float, bool).
    """

    attributes: tuple[str, ...]
    rows: tuple[tuple[str | int | float | bool, ...], ...]


# RelExpr is the union of all relational expression types
RelExpr = (
    RelName
    | Filter
    | NegatedFilter
    | Project
    | Remove
    | NaturalJoin
    | NestJoin
    | Unnest
    | Extend
    | Modify
    | Rename
    | Union
    | Difference
    | Intersect
    | Summarize
    | SummarizeAll
    | NestBy
    | Sort
    | OrderColumns
    | Take
    | Iota
    | Rotate
    | RelationLiteral
)


# --- Top-level statements ---


@dataclass(frozen=True)
class Assignment:
    """Assignment: name := expr."""

    name: str
    expr: RelExpr
