# Parser + Executor Prototype

## Goal

Prove the relational algebra grammar from `documents/algebra.md` works by building a parser and executor that runs queries against in-memory relations. Provides an interactive REPL for experimentation.

## Architecture

Three-stage pipeline: **Lex → Parse → Execute**

```
source text → Lexer → [Token] → Parser → AST → Executor → Relation | list[Tuple_]
```

Each stage is independent and testable in isolation.

## Data Model

### Tuple_

Immutable, hashable wrapper around `dict[str, Value]`. Supports `project`, `extend`, `rename`, `merge`, and `matches` (shared-attribute agreement for joins). Uses `__slots__` and lazy hash caching.

### Relation

Immutable set of tuples backed by `frozenset[Tuple_]` — automatic deduplication enforces set semantics. Carries an `attributes: frozenset[str]` for empty relations. All 15 relational operations return new Relations.

### Value

`int | float | str | bool | Relation` — the last case enables relation-valued attributes (RVAs) for nest join and nest by.

### Type boundary

`sort()` returns `list[Tuple_]`, not a `Relation`. This enforces the algebra's rule that `$` leaves the relational world. The executor propagates this: `Take` requires its source to be a list.

## Lexer

Hand-written single-pass lexer with two-character lookahead for digraph detection. Digraphs (`?!`, `*:`, `<:`, `/.`, `/:`, `#.`, `+.`, `>.`, `<.`, `%.`, `:=`, `|=`, `-=`, `?=`, `!=`, `>=`, `<=`, `!~`, `::`, `+:`) are checked before single-character operators. Line comments start with `--`.

50+ token types in the `TokenType` enum. Each `Token` carries type, value, line, and column.

## Parser

Recursive descent. The core is `_parse_postfix_chain`: parse an atom (relation name or parenthesized expression), then consume postfix operators left-to-right until none match.

### Why hand-written

- Grammar is small (~20 productions)
- Error messages matter for REPL UX
- The left-to-right chain model with context-dependent disambiguation (`*` = join vs multiply, `/` = summarize vs divide) is easier to express directly than in a PEG grammar

### Context disambiguation

`*` and `/` have different meanings depending on context:
- At chain level: `*` is natural join, `/` is summarize
- Inside `+` (extend) computations: `*` is multiply, `/` is divide

The parser knows which context it's in because extend computation parsing uses `_parse_computation_expr` (arithmetic context) while the main chain uses `_parse_postfix_chain` (relational context).

### Bracket elision

Single items don't need brackets; multiple items do. This applies uniformly to `#` (project), `@` (rename), `$` (sort), `+` (extend). The parser checks for `[` to decide which form to use.

### Binary operator right-hand side

For `|`, `-`, `&`: the left operand builds up freely in the chain. The right operand is always an atom — either a bare relation name or a parenthesized expression.

For `*`, `*:`: the right operand is always a bare relation name (plus `> alias` for `*:`), so no parens needed.

## AST

26 frozen dataclasses in two categories:

- **Expressions** (scalar values): `IntLiteral`, `FloatLiteral`, `StringLiteral`, `BoolLiteral`, `AttrRef`, `BinOp`, `SetLiteral`, `AggregateCall`, `SubqueryExpr`
- **Relational expressions** (relations/arrays): `RelName`, `Filter`, `NegatedFilter`, `Project`, `NaturalJoin`, `NestJoin`, `Unnest`, `Extend`, `Rename`, `Union`, `Difference`, `Intersect`, `Summarize`, `SummarizeAll`, `NestBy`, `Sort`, `Take`

Plus `Condition` types for filters: `Comparison`, `BoolCombination`.

## Executor

Tree-walking evaluator using `isinstance` dispatch — no visitor pattern, no `accept()` methods on AST nodes.

### Environment

Mutable mapping of relation names to `Relation` values. The REPL's `\load` command populates it with sample data.

### Aggregate functions

Five implementations: `#.` (count), `+.` (sum), `>.` (max), `<.` (min), `%.` (mean). Mean uses integer floor division when all values are integers, matching the design doc examples (76666 not 76666.67).

### Condition compilation

Filter conditions are compiled into predicate functions (`Callable[[Tuple_], bool]`) with pre-evaluated constant right-hand sides. Set literals are converted to Python sets for O(1) membership testing.

### Tuple-context evaluation

For `/:` (nest by) + `+` (extend) chains like `E /: dept_id > team + [top: >. team.salary]`, the executor resolves `team` by checking the current tuple's attributes before falling back to the environment. This allows aggregate functions to operate on relation-valued attributes.

## v0.1 Scope

### Implemented

`?`, `?!`, `#`, `*`, `*:`, `<:`, `@`, `+`, `-`, `|`, `&`, `/`, `/.`, `/:`, `$`, `^`, chained `?` (AND), `|`/`&` inside filter parens (OR/AND), bracket elision, set literals, aggregate functions (`#.`, `+.`, `>.`, `<.`, `%.`), REPL with sample data, `eval` CLI command.

### Deferred

`+:` (modify), mutation operators (`:=`, `|=`, `-=`, `?=`), regex (`~`, `!~`), type predicates (`::`), transactions, DDL, file storage, the prose layer.

## Testing

181 tests across 6 files:

| File | Tests | Scope |
|------|-------|-------|
| test_model.py | 41 | Tuple_ and Relation operations |
| test_lexer.py | 44 | Tokenization, digraphs, literals, errors |
| test_parser.py | 36 | AST construction for all operator types |
| test_executor.py | 23 | Execution of individual operators |
| test_aggregates.py | 9 | Aggregate function implementations |
| test_integration.py | 28 | End-to-end: parse + execute examples from algebra.md |

## Usage

```
uv run -m prototype.cli repl          # interactive REPL
uv run -m prototype.cli eval "E # name"  # evaluate expression
uv run pytest                          # run all tests
```

REPL commands: `\load` (load sample data), `\env` (show bindings), `\quit` (exit).
