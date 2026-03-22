# Type System

## Overview

Every relation has a schema that defines the type of each column.
Types are enforced at boundaries (load, coercion, modify) and
the runtime is free to optimize internal representation.

## Rules

1. **No mixed types** — every value in a column conforms to the column's declared type.
2. **Expressions don't retype columns** — `date .d "week"` yields an int in expression context but does not change the `date` column's type.
3. **Representation may differ from declaration** — a `date` column may store `datetime.date` objects internally, but the column type is `date`. The value must behave according to the type's contract. This explicitly allows optimization (cf. APL's boolean compaction).

## Built-in Types

| Type | Description |
|------|-------------|
| `str` | String (default for CSV loads) |
| `int` | Integer |
| `float` | Floating point |
| `decimal` | Arbitrary precision decimal |
| `decimal(N)` | Decimal quantized to N places (ROUND_HALF_UP) |
| `date` | Calendar date (ISO 8601) |
| `bool` | Boolean (true/false) |

Future: custom types.

## Schema as a Relation

A schema is a regular two-column relation with attributes `attr` and `type`:

```
Orders := {attr type; date date; amount int; status str}
```

This means schemas can be composed, filtered, and inspected using
standard relational operators:

```
-- extend a base schema
Base := {attr type; id int; created date}
OrderSchema := Base |. {attr type; amount decimal; status str}

-- inspect
OrderSchema # type
```

## Applying a Schema

### At load time

```
\load orders.csv :: Orders o
```

Loads `orders.csv`, coerces columns through the `Orders` schema
relation, binds the result as `o`. Columns not in the schema stay
as-is. Columns in the schema but missing from the CSV are an error.

Without `::`, loading works as today (all strings, with numeric
auto-promotion).

### Inline coercion

```
R :: S
```

Applies schema relation `S` to relation `R`. Coerces each column
named in `S` to the declared type. Returns a new relation with
typed values. Columns in `R` not mentioned in `S` are unchanged.

### Every relation has a schema

Even untyped relations have an implicit schema (all `str` for CSV
loads, inferred from values for literals and expressions). The
schema can be extracted:

```
R ::
```

With no RHS, `::` returns the schema relation for `R`.

## Coercion Rules

When applying a schema, each value is coerced to the target type:

| From | To | Rule |
|------|----|------|
| str | int | Parse as integer, error if invalid |
| str | float | Parse as float, error if invalid |
| str | decimal | Parse as Decimal, error if invalid |
| str | date | Parse as ISO date (or "today"), error if invalid |
| str | bool | "true"→true, "false"→false, error otherwise |
| int | float | Widen |
| int | decimal | Widen |
| float | decimal | Convert via string to preserve digits |
| date | str | ISO format |
| * | str | `str()` conversion |

## Referential Constraints — `in(Relation, attr)`

A type string can reference another relation, constraining the column
to values that exist in that relation's attribute:

```
Statuses := {name desc; "open" "Open"; "closed" "Closed"; "pending" "Pending"}
Schema := {attr type; "status" "in(Statuses, name)"; "amount" "int"}
Orders :: Schema
```

### Semantics

- **Coercion**: the constrained column takes the type of the referenced
  column.  If `Statuses` has a schema saying `name` is `str`, then
  `Orders.status` is coerced to `str`.
- **Validation**: every value in `Orders.status` must exist in
  `Statuses.name`.  Violations raise a coercion error.
- **Environment lookup**: the referenced relation is resolved from the
  environment at the time `::` is applied.  The type string
  `"in(Statuses, name)"` is metadata — inert until applied.

### Continuous enforcement

Once a relation has a schema (via `::` or `\load ::`), all operations
that produce or change values enforce it:

- **`+:` (extend)** — new column values are validated against the schema
- **`=:` (modify)** — changed values are validated against the schema
- **`|.` (union)**, **`|=` (insert)** — incoming values are validated
- **`::` re-application** — re-validates against current environment

Operations that don't introduce new values (project, filter, join,
sort, rename, difference, intersect) propagate the schema but don't
need to re-validate.

### Error messages

Violations produce clear messages:

```
value 'invalid' not in Statuses.name
```

## Type Enforcement Points

- **\load :: Schema** — coerce at CSV import
- **R :: S** — explicit coercion operator
- **=: (modify)** — new values validated against schema
- **+: (extend)** — new column values validated against schema
- **|. (union)**, **|= (insert)** — incoming values validated
- **{} literals** — column type inferred from values

## Future Directions

- Custom types: user-defined types with init/actions/serialization
- Decimal precision: `decimal(2)` for fixed-point
- Type constraints: `int > 0`, `str ~ /pattern/`
- Schema validation without coercion (check but don't convert)
- Mutation guarding: block changes to referenced relations that
  would orphan constrained values (cascading delete vs rejection)
