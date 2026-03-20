# Codd

A working interpreter for the relational algebra described in `documents/algebra.md`. Parses and executes queries against in-memory relations, with an interactive REPL for experimentation.

## How to run this

Install [uv](https://docs.astral.sh/uv/getting-started/installation/) if you don't have it:

```
curl -LsSf https://astral.sh/uv/install.sh | sh
```

Sync the environment (creates a virtualenv and installs dependencies automatically):

```
uv sync
```

Run the tests:

```
uv run pytest
```

## Usage

```
uv run -m codd.cli [FILES...] [OPTIONS]
```

### Modes

**REPL** (default) -- interactive exploration:

```
uv run -m codd.cli --sample
uv run -m codd.cli prices.csv
```

**Eval** -- evaluate a single expression and exit:

```
uv run -m codd.cli --sample -e 'E ? salary > 50000 # [name salary]'
uv run -m codd.cli prices.csv -e 'prices ? price > 100'
```

**Script** -- evaluate expressions from a file:

```
uv run -m codd.cli --sample -f query.codd
uv run -m codd.cli data.csv -f report.codd --arg min_sal=70000
```

### Loading data

CSV files are loaded as positional arguments. The file stem becomes the relation name:

```
uv run -m codd.cli prices.csv                # loaded as "prices"
uv run -m codd.cli p=prices.csv s=sales.csv  # explicit names
cat data.csv | uv run -m codd.cli -           # stdin loaded as "stdin"
```

### Options

| Option | Description |
|--------|-------------|
| `-e EXPR` | Evaluate expression and exit |
| `-f FILE` | Evaluate expressions from a script file |
| `--arg NAME=VALUE` | Substitute `{{NAME}}` in `-f` scripts |
| `--sample` / `--load` | Load sample data (E, D, Phone, ContractorPay) |
| `--csv` | Output as CSV instead of ASCII table |
| `--no-header` | Omit header row from CSV output (implies `--csv`) |
| `--genkey` | Add synthetic `{name}_id` key column to each loaded file |
| `--ops` | Print language primitives reference and exit |
| `--version` | Print version and exit |

## The REPL

The REPL reads one expression per line, parses it, executes it, and prints the result as an ASCII table.

```
$ uv run -m codd.cli --sample
Sample data loaded: E, D, Phone, ContractorPay
Loaded: ContractorPay, D, E, Phone
Codd REPL v1.3.6
Commands: \load <file> [name], \save [file], \export <file> <expr>,
          \drop <name>, \env, \ops, \quit

codd> E # name
+-------+
| name  |
+-------+
| Alice |
| Bob   |
| Carol |
| Dave  |
| Eve   |
+-------+

codd> E ? salary > 50000 # [name salary]
+-------+--------+
| name  | salary |
+-------+--------+
| Alice | 80000  |
| Bob   | 60000  |
| Carol | 55000  |
| Dave  | 90000  |
+-------+--------+

codd> E *. D ? dept_name = "Engineering" # [name salary]
+-------+--------+
| name  | salary |
+-------+--------+
| Alice | 80000  |
| Bob   | 60000  |
| Dave  | 90000  |
+-------+--------+

codd> E /. [n: #.  total: +. salary]
+---+--------+
| n | total  |
+---+--------+
| 5 | 330000 |
+---+--------+

codd> E # [name salary] $ salary- ^ 3
+-------+--------+
| name  | salary |
+-------+--------+
| Dave  | 90000  |
| Alice | 80000  |
| Bob   | 60000  |
+-------+--------+
```

### REPL commands

| Command | Description |
|---------|-------------|
| `\load` | Load sample data (E, D, Phone, ContractorPay) |
| `\load file.csv` | Load a CSV file (stem becomes relation name) |
| `\load file.csv name` | Load a CSV file with an explicit name |
| `\save [file]` | Save workspace to a `.codd` file |
| `\export file expr` | Export expression result as CSV to a file |
| `\drop name` | Remove a relation from the environment |
| `\env` | List all loaded relations with tuple counts and attributes |
| `\ops` | Print language primitives reference |
| `\quit` | Exit |

## Scripts

Script files (`.codd`) contain one expression per line. Lines starting with `#` are comments. Assignments accumulate in the environment; the last expression's result is printed.

```
# report.codd -- summarize high earners by department
high := E ? salary > {{min_sal}}
high *. D /. dept_name [n: #.  avg: %. salary  total: +. salary]
```

```
uv run -m codd.cli --sample -f report.codd --arg min_sal=60000
```

Use `{{name}}` placeholders for parameters, supplied via `--arg name=value`. Values are substituted as raw text before parsing -- strings in the script need their own quotes: `? role = "{{role}}"`.

## Operators

### Sources

Sources produce relations. They appear at the start of an expression chain.

| Op | Name | Example |
|----|------|---------|
| `i.` | Iota (generate) | `i. 5` or `i. month: 12` |
| `{}` | Relation literal | `{name age; "Alice" 30; "Bob" 25}` |

`i.` generates a single-attribute relation of consecutive integers 1..N. An optional `name:` prefix sets the attribute name (default `i`).

Relation literals define a relation inline: header row first, then data rows separated by semicolons.

### Relational

| Op | Name | Example |
|----|------|---------|
| `?` | Filter | `E ? salary > 50000` |
| `?!` | Negated filter | `E ?! dept_id = 10` |
| `#` | Project | `E # name` or `E # [name salary]` |
| `#!` | Remove | `E #! salary` or `E #! [emp_id dept_id]` |
| `*.` | Natural join | `E *. D` |
| `*:` | Nest join | `E *: Phone -> phones` |
| `<:` | Unnest | `nested <: phones` |
| `+:` | Extend | `E +: bonus: salary * 0.1` |
| `=:` | Modify | `E =: salary: salary * 1.1` |
| `@` | Rename | `E @ [pay salary]` |
| `|.` | Union | `A |. (B)` |
| `-.` | Difference | `A -. (B)` |
| `&.` | Intersect | `A &. (B)` |
| `/.` | Summarize | `E /. dept_id [n: #. avg: %. salary]` or `E /. [n: #.]` |
| `/:` | Nest by | `E /: dept_id -> team` |
| `$` | Sort | `E $ salary-` or `E $ [dept_id salary-]` |
| `$.` | Order columns | `E $. [salary name]` |
| `^` | Take | `E $ salary- ^ 3` |
| `r.` | Rotate | `E ? name = "Alice" r.` |

Expressions chain left-to-right. Each operator transforms the result of the previous step. `$`, `$.`, and `r.` leave the relational world (returning display-oriented output); only `^` and `$.` can follow `$`.

### Aggregates (used inside `/.` and `+:`)

| Op | Name | Example |
|----|------|---------|
| `#.` | Count | `#.` |
| `+.` | Sum | `+. salary` |
| `>.` | Max | `>. salary` |
| `<.` | Min | `<. salary` |
| `%.` | Mean | `%. salary` |
| `n.` | Collect | `n. activity` |
| `p.` | Percent | `p. salary ~ 1` |

### Expressions (used inside `+:` and `=:`)

| Op | Name | Example |
|----|------|---------|
| `+ - * /` | Arithmetic | `salary * 0.1` |
| `// %` | Integer divide / remainder | `salary // 1000` or `i % 2` |
| `~` | Precision | `%. salary ~ 2` |
| `.s` | Substring | `name .s [1 3]` or `name .s [-2]` |
| `.d` | Date | `col .d` or `col .d "year"` |
| `?:` | Ternary | `?: dept_id = 10 "eng" "other"` |

All expression operators evaluate left-to-right with no precedence. Use parentheses to override.

### Other

| Op | Name | Example |
|----|------|---------|
| `:=` | Assignment | `high := E ? salary > 70000` |

## Dates

The `.d` operator introduces dates as a first-class type.

### Promotion

Convert a string to a Date value:

```
"2026-03-17" .d              -- ISO format (YYYY-MM-DD)
"today" .d                   -- today's date (local time)
hire_date .d                 -- promote a string attribute
```

Once promoted, dates carry their type through the pipeline. If a value is already a Date, `.d` is a no-op.

### Component extraction

Extract an integer component from a date:

```
date_col .d "year"           -- 2026
date_col .d "month"          -- 3
date_col .d "day"            -- 17
date_col .d "week"           -- ISO week number (1-53)
date_col .d "dow"            -- day of week (1=Monday, 7=Sunday)
```

### Formatting

Format a date as a string using `{token}` patterns:

```
date_col .d "{yyyy}-{mm}-{dd}"       -- "2026-03-17"
date_col .d "{dd} {mmm} {yyyy}"      -- "17 MAR 2026"
date_col .d "{d}/{m}/{yy}"           -- "17/3/26"
date_col .d "{dd}{mmm}{yy}"          -- "17MAR26"
date_col .d "{ddd}"                  -- "TUE"
```

| Token | Example | Meaning |
|-------|---------|---------|
| `{d}` | 7 | Day, no padding |
| `{dd}` | 07 | Day, zero-padded |
| `{m}` | 3 | Month number |
| `{mm}` | 03 | Month, zero-padded |
| `{mmm}` | MAR | Month abbreviation |
| `{yy}` | 26 | 2-digit year |
| `{yyyy}` | 2026 | 4-digit year |
| `{week}` | 12 | ISO week number |
| `{dow}` | 2 | Day of week (1=Mon) |
| `{ddd}` | TUE | Day abbreviation |

### Date arithmetic

Dates participate in arithmetic with `+` and `-`:

| Expression | Result | Meaning |
|------------|--------|---------|
| `date + int` | Date | Add N days |
| `date - int` | Date | Subtract N days |
| `date - date` | int | Difference in days |

When one operand is a Date and the other is a date-like string, the string is auto-promoted. This means `date_col - "2026-01-01"` works without explicit `.d` on the string.

### Date coercion

Dates coerce with strings in filters and joins:

- **Filter**: `? date_col = "2026-01-05"` works when `date_col` holds Date values
- **Join**: `*.` matches Date columns against string columns containing ISO dates
- **Scalar filter RHS**: `? date_col = ("today" .d - 14)` — parenthesized expressions as filter values

### Example: generate a week-number calendar

```
i. day: 365 =: day: "2025-12-31" .d + day +: week: day .d "week" # [day week]
```

## Identifiers

Standard identifiers are alphanumeric with underscores: `salary`, `dept_id`, `table2`.

For column names with spaces (common in CSV files), use backtick quoting:

```
T # [`Account Name` `Processed Date`]
T ? `Account Name` = "Alice"
T +: total: `Unit Price` * Qty
T @ `Account Name` name
```

Backtick-quoted identifiers work everywhere regular identifiers do.

## Substring

The `.s` operator extracts substrings with 1-based inclusive indexing:

```
name .s [1 3]           -- first 3 characters: "Alice" → "Ali"
name .s [3]             -- from position 3 to end: "Alice" → "ice"
name .s [-2]            -- last 2 characters: "Alice" → "ce"
name .s [-4 -2]         -- range from end: "Alice" → "lic"
```

Positive indices count from 1, negative from the end. Out-of-bounds indices are clamped silently.
