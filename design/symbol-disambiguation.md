# Symbol Disambiguation

## Problem

Seven symbols currently have context-dependent meanings:

| Symbol | Chain level (relational) | Expression level (arithmetic/boolean) |
|--------|-------------------------|--------------------------------------|
| `+` | extend | addition |
| `-` | difference | subtraction |
| `*` | natural join | multiplication |
| `/` | summarize | division |
| `?` | filter | ternary (inside extend/summarize) |
| `|` | union | OR (inside filter conditions) |
| `&` | intersect | AND (inside filter conditions) |

The parser disambiguates by tracking whether it's at chain level or expression level. This creates three problems:

1. **Ambiguous operator boundaries.** `E / foo +. bar + bonus: x` — the parser can't tell where the summarize body ends and extend begins without brackets. The `+` could be arithmetic addition in the summarize expression or the start of an extend chain.

2. **Parser complexity.** The same token `*` dispatches to `_parse_natural_join` or multiplication depending on context state. Every operator boundary requires context awareness.

3. **Confusing error messages.** A misplaced `[` after `?` produces "Expected IDENT, got LBRACKET" instead of something more helpful, because the parser has already committed to a context-specific interpretation.

## Rule

**Each symbol (simple or compound) has exactly one meaning, regardless of context.**

Arithmetic operators `+ - * /` keep their universal mathematical meanings. Relational operators get compound symbols using an existing suffix convention.

## Suffix Convention

Three suffixes are already established in the language:

| Suffix | Meaning | Existing examples |
|--------|---------|-------------------|
| `.` | reduce / collapse / aggregate | `#.` count, `+.` sum, `>.` max, `<.` min, `%.` mean |
| `:` | restructure / reshape | `*:` nest join, `/:` nest by, `<:` unnest |
| `!` | negate / invert | `?!` negated filter, `#!` remove |

The `.` suffix extends naturally to relational operations that combine or reduce relations (join, set operations). The `:` suffix extends to operations that reshape tuple structure (extend).

## Proposed Symbol Table

### Arithmetic (unchanged)

`+` add, `-` subtract, `*` multiply, `/` divide

### Boolean connectives (unchanged)

`|` OR, `&` AND — used inside filter conditions `? (a = 1 | b = 2)`

### Aggregates (unchanged)

`#.` count, `+.` sum, `>.` max, `<.` min, `%.` mean

### Relational operators

| New | Was | Name | Example |
|-----|-----|------|---------|
| `?` | `?` | filter | `E ? salary > 50000` |
| `?!` | `?!` | negated filter | `E ?! role = "engineer"` |
| `#` | `#` | project | `E # [name salary]` |
| `#!` | `#!` | remove | `E #! emp_id` |
| `@` | `@` | rename | `E @ [pay -> salary]` |
| `+:` | `+` | extend | `E +: bonus: salary * 0.1` |
| `*.` | `*` | natural join | `E *. D` |
| `*:` | `*:` | nest join | `E *: Phone -> phones` |
| `<:` | `<:` | unnest | `E *: Phone -> phones <: phones` |
| `/.` | `/` | summarize | `E /. dept_id [n: #. avg: %. salary]` |
| `/:` | `/:` | nest by | `E /: dept_id -> team` |
| `-.` | `-` | difference | `E -. (E ? role = "engineer")` |
| `|.` | `|` | union | `A |. (B)` |
| `&.` | `&` | intersect | `A &. (B)` |
| `$` | `$` | sort | `E $ salary-` |
| `^` | `^` | take | `E $ salary- ^ 3` |
| `?:` | `?` (in extend) | ternary | `?: dept_id = 10 "eng" "other"` |

### Changes explained

**`+:` for extend.** The `:` suffix means "restructure" — adding computed columns reshapes the tuple. This reassigns `+:` from the deferred modify operator (not yet implemented). Modify needs a new symbol (see Open Questions).

**`/.` for summarize.** Currently `/.` is summarize-all (no grouping key). Under the new scheme, `/.` becomes the unified summarize operator. The presence or absence of a grouping key distinguishes the two forms:

```
E /. dept_id [n: #. avg: %. salary]   -- summarize by dept_id
E /. [n: #. total: +. salary]         -- summarize all (no key)
```

One operator, two forms. No separate `/.` vs `/` distinction needed.

**`*.` for join.** The `.` suffix marks it as the relational (reducing) operation on the `*` base. `*:` remains nest join.

**`-.` `|.` `&.` for set operations.** Boolean `|` and `&` keep their bare forms for filter conditions (more frequent, universally understood). The set operations get `.` suffixes — consistent with "relational operation on this base."

**`?:` for ternary.** Mirrors C's `?:` syntax. Frees `?` to mean only "filter."

**`->` for rename/alias arrow.** Currently `>` means both "greater than" (comparison) and "becomes" (inside `@`, `*:`, `/:`). Under the new rule, the rename/alias arrow becomes `->`:

```
E @ [pay -> salary]
E *: Phone -> phones
E /: dept_id -> team
```

## Before and After

### Join then filter then project

```
-- before
E * D ? dept_name = "Engineering" # [name salary]

-- after
E *. D ? dept_name = "Engineering" # [name salary]
```

### Extend with ternary then summarize

```
-- before
E + grp: ? dept_id = 10 "eng" "other" / grp [n: #. avg: %. salary]

-- after
E +: grp: ?: dept_id = 10 "eng" "other" /. grp [n: #. avg: %. salary]
```

Every operator boundary is unambiguous. No context tracking needed.

### The bracket disambiguation problem (resolved)

```
-- before (ambiguous without brackets)
E / dept_id +. salary + bonus: salary * 0.1
-- parser can't tell: is + arithmetic (in summarize) or extend (in chain)?

-- before (brackets required to disambiguate)
E / dept_id [+. salary] + bonus: salary * 0.1

-- after (unambiguous, no brackets needed)
E /. dept_id +. salary +: bonus: salary * 0.1
-- /. = summarize, +. = sum aggregate, +: = extend, * = multiply
```

### Set operations

```
-- before
E # emp_id - (Phone # emp_id)
E ? (dept_id = 20 | salary > 80000)

-- after
E # emp_id -. (Phone # emp_id)
E ? (dept_id = 20 | salary > 80000)    -- unchanged, | is still OR
```

## Extensibility

The `.` suffix is not limited to punctuation bases. Any letter or digraph followed by `.` becomes an operator. The current aggregates (`#.`, `+.`, `>.`, `<.`, `%.`) demonstrate the pattern with punctuation; alphabetic bases open a large namespace for future operators.

Examples of what this enables:

| Operator | Meaning | Example |
|----------|---------|---------|
| `p.` | percentage of total | `R +: p. amount` → adds `pct_amount` column |
| `d.` | distinct count | `/. dept_id [n: d. role]` |
| `v.` | variance | `/. dept_id [v: v. salary]` |
| `s.` | standard deviation | `/. dept_id [s: s. salary]` |
| `m.` | median | `/. dept_id [m: m. salary]` |

The convention is self-documenting: a `.`-suffixed token is always a built-in reducing/aggregate operation. 26 single-letter slots are available, plus multi-letter bases (`cv.` for coefficient of variation, etc.) if needed.

The `:` suffix provides a separate namespace for user-defined operators. A user who defines a function called `p` would invoke it as `p:` — no collision with the built-in `p.` aggregate. The two suffixes give clean separation between the language's built-in operations and user extensions.

This makes the suffix convention not just a disambiguation mechanism but a growth strategy for the algebra.

## Open Questions

### Modify operator

`+:` was reserved for modify (update existing columns: `E +: salary: salary * 1.1`). With `+:` reassigned to extend, modify needs a new symbol. Candidates:

- `+!` — "overwrite" (stretches the `!` = negate meaning)
- `+=` — "update in place" (familiar from assignment operators)
- Defer the decision — modify is not yet implemented

### Bracket elision for extend

With `+:`, single-column extend becomes `E +: bonus: salary * 0.1` and multi-column becomes `E +: [bonus: salary * 0.1 tax: salary * 0.3]`. The double-colon in single-column form (`+: bonus:`) is visually busy but unambiguous. No grammar change needed — bracket elision works the same way.

### `>` strictness

The `>` overload (comparison vs rename arrow) causes zero practical ambiguity — the contexts never overlap syntactically. Changing to `->` is pure consistency. The cost is a new two-character token and longer rename/alias expressions. Worth doing for the principle, but low urgency.
