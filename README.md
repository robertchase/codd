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
| `--genkey` | Add synthetic `{name}_id` key column to each loaded file |
| `--ops` | Print language primitives reference and exit |

## The REPL

The REPL reads one expression per line, parses it, executes it, and prints the result as an ASCII table.

```
$ uv run -m codd.cli --sample
Sample data loaded: E, D, Phone, ContractorPay
Loaded: ContractorPay, D, E, Phone
Codd REPL
Commands: \load <file> [name], \save [file], \drop <name>, \env, \ops, \quit

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
| `@` | Rename | `E @ [pay -> salary]` |
| `|.` | Union | `A |. (B)` |
| `-.` | Difference | `A -. (B)` |
| `&.` | Intersect | `A &. (B)` |
| `/.` | Summarize | `E /. dept_id [n: #. avg: %. salary]` or `E /. [n: #.]` |
| `/:` | Nest by | `E /: dept_id -> team` |
| `$` | Sort | `E $ salary-` or `E $ [dept_id salary-]` |
| `$.` | Order columns | `E $. [salary name]` |
| `^` | Take | `E $ salary- ^ 3` |

Expressions chain left-to-right. Each operator transforms the result of the previous step. `$` and `$.` leave the relational world (returning an ordered list); only `^` and `$.` can follow them.

### Aggregates (used inside `/.`)

| Op | Name | Example |
|----|------|---------|
| `#.` | Count | `#.` |
| `+.` | Sum | `+. salary` |
| `>.` | Max | `>. salary` |
| `<.` | Min | `<. salary` |
| `%.` | Mean | `%. salary` |
| `n.` | Collect | `n. activity` |

### Expressions (used inside `+:` extend)

| Op | Name | Example |
|----|------|---------|
| `+ - * /` | Arithmetic | `salary * 0.1` |
| `~` | Precision | `%. salary ~ 2` |
| `?:` | Ternary | `?: dept_id = 10 "eng" "other"` |

Arithmetic follows standard precedence (`*`/`/` before `+`/`-`).

### Other

| Op | Name | Example |
|----|------|---------|
| `:=` | Assignment | `high := E ? salary > 70000` |
