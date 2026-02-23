# Auto-naming for Summarize Columns

## Problem

Summarize currently requires explicit `name: expr` for every computed column:

```
R / dept [n: #.  total: +. salary  avg: %. salary]
```

This is verbose for the common case where a readable name can be derived from the aggregate itself. It also means the simpler single-computation form still requires a name:

```
R / dept n: #.
```

In REPL exploration especially, having to invent names for straightforward aggregates slows things down.

## Proposed Change

Allow aggregate expressions in summarize without the `name:` prefix. The column name is auto-generated from the aggregate type and its argument.

### Auto-naming Rules

| Expression   | Auto-name    | Rationale                                      |
|--------------|--------------|-------------------------------------------------|
| `#.`         | `count`      | Counting group tuples, no column involved       |
| `#. phones`  | `count_phones` | Counting an RVA — the source is meaningful    |
| `+. salary`  | `sum_salary` |                                                 |
| `>. salary`  | `max_salary` |                                                 |
| `<. salary`  | `min_salary` |                                                 |
| `%. salary`  | `mean_salary`|                                                 |

Mapping from aggregate token to name prefix:

- `#.` → `count`
- `+.` → `sum`
- `>.` → `max`
- `<.` → `min`
- `%.` → `mean`

### Explicit Names Still Work

The `name: expr` form remains available as an override:

```
R / dept [#.  avg: %. salary]
```

yields columns `dept`, `count`, `avg`.

### Complex Expressions Require Names

Auto-naming only applies when the entire computation is a single `AggregateCall` AST node. If the expression involves arithmetic or other structure (producing `BinOp`, `SubqueryExpr`, etc.), the parser requires an explicit name. Example:

```
-- This requires a name because the expression is a BinOp:
R / dept pct: +. salary / (R /. total: +. salary)

-- This gets auto-named because it's a bare aggregate:
R / dept +. salary
```

This keeps auto-naming predictable: bare aggregate → readable name; formula → name it yourself.

### Duplicate Auto-names

Duplicate auto-generated names are a parse error:

```
R / dept [+. salary  +. salary]   -- error: duplicate column name 'sum_salary'
```

This is a degenerate query anyway. Use explicit names to disambiguate:

```
R / dept [base: +. salary  bonus: +. bonus_salary]
```

## Examples

Before:

```
R / dept [n: #.  total: +. salary  avg: %. salary  top: >. salary]
```

After (auto-named):

```
R / dept [#.  +. salary  %. salary  >. salary]
```

yields: `dept | count | sum_salary | mean_salary | max_salary`

Mixed:

```
R / dept [#.  avg: %. salary  +. bonus]
```

yields: `dept | count | avg | sum_bonus`

Summarize-all works identically:

```
R /. [#.  +. salary]
```

yields: `count | sum_salary`

## Grammar Change

Current named-expr production:

```
named_expr := IDENT COLON computation_expr
```

New maybe-named-expr production:

```
maybe_named_expr := IDENT COLON computation_expr
                  | computation_expr
```

The parser distinguishes the two forms by looking at the next token:

- **Aggregate token** (`#.`, `+.`, `>.`, `<.`, `%.`): parse as unnamed, auto-generate name from the resulting `AggregateCall` node. If the parsed expression is not a bare `AggregateCall` (i.e., it became a `BinOp` due to arithmetic), raise a parse error requiring an explicit name.
- **IDENT followed by COLON**: parse as named (current behavior).
- **Anything else**: parse error.

Inside brackets, the loop termination is unchanged (`RBRACKET`). The boundary between consecutive unnamed computations is naturally handled because each aggregate token is distinct from the tokens that follow a computation expression.

## Implementation

### Parser

`_parse_named_expr_list` and `_parse_named_expr` change to support the unnamed form. After parsing, validate no duplicate names in the list.

### AST

`NamedExpr` is unchanged — the auto-generated name is filled in at parse time, so downstream code (executor, etc.) sees no difference.

### Name Generation

A helper function derives the name from an `AggregateCall`:

```python
_AGG_NAME_PREFIX = {
    "#.": "count",
    "+.": "sum",
    ">.": "max",
    "<.": "min",
    "%.": "mean",
}

def _auto_name(expr: AggregateCall) -> str:
    prefix = _AGG_NAME_PREFIX[expr.func]
    if expr.arg:
        return f"{prefix}_{expr.arg.name}"
    if expr.source and isinstance(expr.source, RelName):
        return f"{prefix}_{expr.source.name}"
    return prefix
```

### Executor

No changes. It already works with `NamedExpr.name` and `NamedExpr.expr`.

### Lexer

No changes.
