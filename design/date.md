# `.d` — Date Operator

## Problem

Codd has no date type. Date values are strings, which means no date arithmetic (add days, compute differences) and no component extraction (year, month, week number).
## Design

`.d` is a **dot-prefix scalar operator** (like `.s`). It serves three roles via a single syntax:

1. **Type promotion**: `expr .d` — convert string to Date
2. **Component extraction**: `expr .d 'week'` — extract integer component
3. **Formatting**: `expr .d '{dd} {mmm} {yyyy}'` — format as string

### Date type

A new `Date` type joins the `Value` union. Internally backed by Python `datetime.date`. Dates display as ISO format (`2026-03-17`) in table output.

### Type promotion

```
"2026-03-17" .d           → Date(2026, 3, 17)
hire_date .d              → promote string attribute to Date
"today" .d                → today's date (local time)
```

Accepts ISO format (`YYYY-MM-DD`) or `"today"`. Error on unparseable strings.

If the value is already a Date, `.d` is a no-op.

### Component extraction

```
expr .d "year"   → int     (2026)
expr .d "month"  → int     (3)
expr .d "day"    → int     (17)
expr .d "week"   → int     (ISO week number, 1-53)
expr .d "dow"    → int     (day of week, 1=Monday, 7=Sunday)
```

A bare keyword (no `{}` braces) returns an integer. The set of keywords is fixed.

### Formatting

```
expr .d "{yyyy}-{mm}-{dd}"     → "2026-03-17"
expr .d "{dd} {mmm} {yyyy}"    → "17 MAR 2026"
expr .d "{d}/{m}/{yy}"         → "17/3/26"
expr .d "{dd}{mmm}{yy}"        → "17MAR26"
```

A string containing `{` is a format pattern. Text outside braces is literal. Tokens inside braces:

| Token    | Example | Meaning               |
|----------|---------|-----------------------|
| `{d}`    | 7       | Day, no padding       |
| `{dd}`   | 07      | Day, zero-padded      |
| `{m}`    | 3       | Month number          |
| `{mm}`   | 03      | Month, zero-padded    |
| `{mmm}`  | MAR     | Month abbreviation    |
| `{yy}`   | 26      | 2-digit year          |
| `{yyyy}` | 2026    | 4-digit year          |
| `{week}` | 12      | ISO week number       |
| `{dow}`  | 2       | Day of week (1=Mon)   |
| `{ddd}`  | TUE     | Day abbreviation      |

Formatting always returns a string.

### Disambiguation

The `.d` RHS is always a string literal (quoted). The parser peeks after consuming `.d`:

- String literal → extraction or formatting (check for `{` to decide)
- Anything else → plain promotion (no RHS)

No ambiguity: a string literal would never directly follow a bare `.d` promotion in normal expression flow.

## Date arithmetic

`+` and `-` become type-aware for dates. The existing `_apply_binop` gains date cases:

| Expression        | Result type | Meaning              |
|-------------------|-------------|----------------------|
| `date + int`      | Date        | Add N days           |
| `int + date`      | Date        | Add N days           |
| `date - int`      | Date        | Subtract N days      |
| `date - date`     | int         | Difference in days   |
| `date + date`     | error       |                      |
| `date * anything` | error       |                      |
| `date / anything` | error       |                      |

This extends `_apply_binop` without changing its interface. The `_promote_numeric` step in `_eval_binop` must be updated to pass Date values through without coercion.

## Example: date range for 2026

```
i. day: 365 =: day: "2025-12-31" .d + day +: week: day .d "week" # [day week]
```

1. `i. day: 365` — generate {day} with 1..365
2. `=: day:` — modify day to a Date by adding offset to Dec 31
3. `+: week:` — extract ISO week number
4. `# [day week]` — project

## Grammar

`.d` participates in `_parse_left_to_right_expr` alongside `~` and `.s`:

```
left_to_right_expr := atom ( TILDE INTEGER
                            | S_DOT '[' ... ']'
                            | D_DOT [STRING]
                            | arith_op atom
                            )*
```

## AST

```python
@dataclass(frozen=True)
class DateOp:
    """Date operator: expr .d [format]."""
    expr: Expr
    fmt: str | None = None   # None = promotion, str = extraction/format
```

`DateOp` is added to the `Expr` union.

## Lexer

`.d` follows the same pattern as `.s` — dot-prefix digraph with lookahead to avoid matching `.dept`:

```
if ch == "." and ch2 == "d" and not (peek(2).isalnum() or peek(2) == "_"):
```

New token: `D_DOT`.

## Executor

- `_eval_expr` and `_eval_summarize_expr` gain `DateOp` handling
- `_apply_date_op(value, fmt)` dispatches on `fmt`:
  - `None` → promote to Date
  - Bare keyword → extract component as int
  - Contains `{` → format as string
- `_apply_binop` gains Date cases before the existing numeric logic
- `_promote_numeric` passes Date values through unchanged

## Type coercion

Dates coerce with strings in two contexts:

- **Filter comparisons** (`?`): `? date = "2026-01-05"` works even when `date` is a Date value — `_coerce_pair` promotes the string to a Date before comparing.
- **Natural join** (`*.`): `Tuple_.matches` uses `_values_equal` which promotes date-like strings when the other side is a Date. This allows joining a Date column against a string column containing ISO dates.
