# `/+` — Cumulative Aggregate

## Goal

Running totals, running max/min/count, and cumulative share — computed
*inside* the relational algebra, so the result keeps composing (filter on
the running total, join it, describe it).

Today this is inexpressible in codd: it needs either an inequality
self-join (joins are equality-only) or ordered iteration (which only
exists past `$`, where the relational world ends).

## Why it's relational

The admissibility test is the one `/^` (rank) established: an added
attribute is sound if it is a **deterministic function of the tuple's
values relative to the rest of the relation** — no dependence on
physical order.

`/+` uses **key-based (RANGE) semantics**: for tuple `t` with sort key
`k(t)`, the new attribute is

    AGG over { u ∈ R : k(u) ≤ k(t) }

i.e. the aggregate over the *prefix set* of tuples whose key sorts at or
before `t`'s key. Tied tuples have identical prefix sets, so they get
identical values — same tie rule as dense rank, and the reason this is a
set-in/set-out operator.

The row-positional variant ("each row adds exactly one row's value") is
**deliberately excluded**: with tied keys it has no deterministic answer.
If ever wanted, it belongs in the array world after `$`, not here.

## Syntax

Mirrors `/.` and `/*` (key first, then a named-aggregate list), except the
key uses **sort-key syntax** because direction matters:

    R /+ key [name: agg ...]           Single key, ascending
    R /+ key- [name: agg ...]          Descending
    R /+ [key1 key2-] [name: agg ...]  Composite key
    R /+ key agg                       Auto-named single aggregate
                                       (like /. and /*: +. amount → sum_amount)

The aggregate list accepts the same expression forms as `/.` (aggregate
calls, `~` precision, `.as` casts, arithmetic over aggregates). Aggregates
are evaluated with:

- group relation = the tuple's prefix set
- whole relation = all of R  (so `p.` = cumulative share of total)

Multiple aggregates compute in one pass:

    R /+ date [cum: +. amount  hi: >. amount  n: #.]

## Semantics

- **Ordering** is schema-aware, identical to `$`, `/^`, `/&`: key values
  are coerced per the source schema before comparison, `-` reverses.
- **Ties**: all tuples sharing a key value get the same cumulative value,
  and that value includes the entire tied group. (Document prominently —
  it is the RANGE/dense-rank rule, not "running row by row".)
- **Result**: all original attributes plus the new columns. Error if a
  new name collides with an existing attribute (as `/^`/`/&`).
- **Schema**: same inheritance as `/.` — `#.` is int, `%.`/`p.` float,
  `+.`/`>.`/`<.` inherit the column type, `.as` wins.
- **Empty relation** passes through empty (with the new attrs in the
  heading).
- **Descending key** means "prefix" runs from the top: with `amount-`,
  each tuple's value aggregates everything with amount ≥ its own.

## Examples

Data:

    Sales
    +------------+---------+--------+
    | date       | product | amount |
    +------------+---------+--------+
    | 2026-01-05 | a       | 10     |
    | 2026-01-12 | b       | 40     |
    | 2026-01-12 | c       | 20     |   ← tied date with b
    | 2026-01-19 | d       | 30     |
    +------------+---------+--------+

**Running total by date:**

    Sales /+ date [cum: +. amount]

    | date       | product | amount | cum |
    | 2026-01-05 | a       | 10     | 10  |
    | 2026-01-12 | b       | 40     | 70  |   ← ties share cum,
    | 2026-01-12 | c       | 20     | 70  |   ← includes both rows
    | 2026-01-19 | d       | 30     | 100 |

**Pareto / ABC analysis** — the composability payoff. Which products make
up the first 80% of revenue?

    Sales /+ amount- [share: p. amount] ? share <= 80

`p.` over the prefix (ordered by amount descending) divided by the whole
gives cumulative revenue share as a percent (0-100); the filter keeps
the head. Set in, set
out — join it back to a product dimension afterward if you like.

**Record-to-date (running max):**

    Temps /+ date [hi: >. temp] ? temp = hi     -- days that set a record

**Events so far (running count):**

    Events /+ date [n: #.]

**Remaining-to-go (descending prefix):**

    Sales /+ date- [left: +. amount]            -- sum from here to the end

**Weekly cumulative, using the ISO week key:**

    Sales +: wk: date .d "{iyy}{ww}" /+ wk [cum: +. amount]

**Auto-named:**

    Sales /+ date +. amount                     -- adds "sum_amount"

## Non-features

- **No partitioning in v1.** SQL's `PARTITION BY g ORDER BY k` (per-group
  running totals) is the obvious extension; the syntax slot is reserved
  (likely `R /+ key [aggs] by group` or a bracket variant) but deferred
  until the unpartitioned form proves out. There is no workaround today
  (ops can't run inside nested relations), so demand will be visible.
- **No row-positional frame.** See "Why it's relational".
- **No sliding windows** (last-N-rows / last-N-days). Different feature;
  the prefix frame here is always unbounded-preceding.

## Implementation sketch

1. **Lexer**: `SLASH_PLUS` digraph `/+`, added with the other `/` pairs.
   Same caveat as `/*` and friends: in an arithmetic expression,
   division by an aggregate needs a space (`a / +. b`, not `a/+.b`).
2. **AST**: `Cumulative(source, keys: tuple[SortKey,...],
   computations: tuple[NamedExpr,...])`. Auto-naming reuses
   `_parse_maybe_named_expr(allow_auto_name=True)`.
3. **Parser**: `_parse_cumulative` — `_parse_sort_key_list()` then the
   named-expr list; dispatch from `_parse_postfix_chain`.
4. **Executor** `_eval_cumulative`:
   - Validate names (no collisions), keys exist.
   - Coerce/group tuples by key (reuse the `/&` `coerced_values` /
     `sort_order_key` machinery), sort the distinct keys.
   - Walk keys in order, growing a prefix tuple-set; after adding each
     tied group, evaluate the aggregate list via `_eval_summarize_expr`
     with `group_rel=prefix`, `whole_rel=source`; assign the results to
     every tuple in that group.
   - Complexity O(k·n) with k distinct keys (each evaluation rescans the
     prefix). Acceptable at codd scale; incremental accumulators for
     `+. #. >. <. %.` are a straightforward later optimization if needed.
   - Schema via `_build_agg_schema` (unchanged).
5. **Docs**: `\ops` row in Relational next to `/*`, detail entry with the
   tie rule and the Pareto example.
6. **Tests**: running sum, ties share values, descending, composite key,
   `p.` cumulative share + Pareto filter, running max/count, auto-name,
   name collision error, unknown key error, empty relation, schema of
   result columns, schema-aware key ordering (str "10" vs "2").
