# `i.` — Iota (Relation Generator)

## Problem

Codd operates on relations but has no way to synthesize one from nothing. You can load CSV files and query existing relations, but you cannot generate a relation programmatically. This blocks use cases like:

- Date ranges: 365-row relation for every day in a year
- Lookup tables: mapping integers to labels
- Test data: quick throw-away relations for experimenting in the REPL

## Design

`i.` is a **relation source** — it occupies the same grammatical position as a relation name or parenthesized subquery. It produces a single-attribute relation of consecutive integers starting at 1.

### Syntax

```
i. [name:] COUNT
```

- `COUNT` — literal positive integer (required)
- `name:` — optional attribute name (default: `i`)

### Examples

```
i. 5                → {i}  with tuples {1, 2, 3, 4, 5}
i. month: 12        → {month}  with tuples {1, 2, ..., 12}
i. day: 365         → {day}  with tuples {1, 2, ..., 365}
```

### Derived ranges

No start/end syntax. Arithmetic handles offsets:

```
i. 11 =: i: i + 9          → {i}  with 10, 11, ..., 20
i. 26 =: letter: i + 64    → ASCII codes, with further .s or future ops
```

### Composition

`i.` participates in the postfix chain like any other source:

```
-- 365-day date table (assuming .d date primitive)
i. day: 365 +: date: .d '2025-12-31' + day

```

### 1-based

Consistent with `.s` substring indexing and the language's general convention. First value is 1, last is COUNT.

### Literal-only count

COUNT must be a literal integer, not an expression. `i.` is a source, not an operator evaluated against tuples, so there is no tuple context for expression evaluation. If a computed count becomes necessary, a subquery could supply it later.

## Grammar

In the parser, `i.` is a new atom in `_parse_atom` alongside `RelName` and parenthesized subqueries:

```
atom := IDENT
      | '(' postfix_chain ')'
      | 'i.' [IDENT ':'] INTEGER
```

## AST

```python
@dataclass(frozen=True)
class Iota:
    """Iota source: i. [name:] count."""
    count: int
    name: str = "i"
```

`Iota` is added to the `RelExpr` union.

## Executor

Generates a `Relation` with `count` tuples, each containing a single attribute (`name`) with values 1 through `count`.

## Future: Inline Relation Literals

A separate but complementary feature — small ad-hoc relations written inline. `i.` handles computed sequences; literals handle enumerated data. Literal syntax is TBD (deferred).
