# Data Loading and Workspace

## Goal

Make codd a practical tool for working with real data files. Two modes:

1. **CLI mode** — awk-like one-liners against files and stdin
2. **REPL mode** — an APL-style workspace for interactive exploration

The expression language is identical in both modes. The REPL adds assignment, workspace persistence, and interactive data loading.

## CLI Mode

### Basic usage

```
codd 'expr' file.csv
codd 'expr' file1.csv file2.json
cat data.csv | codd 'expr'
ps aux | codd 'expr'
```

File names (minus extension) become relation names:

```
codd 'users ? age > 30' users.csv
codd 'users * orders # [name total]' users.csv orders.csv
```

### Options

```
--as name=file.csv        # explicit relation name
--key=attr                # key hint for decomposition (see below)
--key=[attr1 attr2]       # composite key
--genkey                  # generate synthetic {relation}_id key column
-f csv|tsv|json|ws        # input format (default: auto-detect)
-t table|csv|tsv|json     # output format (default: table)
--strict                  # error on missing values instead of decomposing
```

Stdin is bound to `stdin`:

```
ps aux | codd 'stdin ? cpu > 5.0 $ [-cpu] ^ 10'
```

## REPL Mode

### The workspace

The REPL environment is a workspace — a mutable collection of named relations. You can inspect it, add to it, save it, and restore it.

### Assignment

`:=` binds the result of an expression to a name:

```
codd> Engineers := users ? role = "engineer"
codd> Engineers
┌───────┬────────┬──────┐
│ name  │ salary │ role │
...
```

The bound relation is a first-class workspace member — it appears in `\env`, persists across `\save`/`\load`, and can be used in subsequent expressions.

### Slash commands

```
\load file.csv                    # load data file into workspace
\load file.csv --as=Users         # load with explicit name
\load file.csv --key=name         # key hint for decomposition
\load workspace.codd              # restore a saved workspace
\save                             # save workspace (to last-used path, or prompt)
\save mywork.codd                 # save workspace to path
\drop R                           # remove a relation from workspace
\env                              # list all relations (name, tuple count, attributes)
\quit                             # exit
```

`\load` sniffs the file to decide: workspace file or data file. Workspace files use a known format (see Persistence below). Everything else is treated as data.

### Example session

```
$ codd repl
codd> \load employees.csv --key=emp_id
Loaded 4 relations from employees.csv:
  employees       5 tuples  {emp_id, name, dept}
  employees_phone 3 tuples  {emp_id, phone}
  employees_email 4 tuples  {emp_id, email}
  employees_title 2 tuples  {emp_id, title}

codd> \load departments.csv
Loaded: departments  3 tuples  {dept_id, dept_name}

codd> employees * departments
┌────────┬───────┬─────────┬─────────────┐
│ emp_id │ name  │ dept_id │ dept_name   │
...

codd> BigTeams := employees / dept_id [n: #.] ? n > 2
codd> \env
  employees        5 tuples  {emp_id, name, dept_id}
  employees_phone  3 tuples  {emp_id, phone}
  employees_email  4 tuples  {emp_id, email}
  employees_title  2 tuples  {emp_id, title}
  departments      3 tuples  {dept_id, dept_name}
  BigTeams         1 tuple   {dept_id, n}

codd> \save analysis.codd
Saved 6 relations to analysis.codd
```

## Data Loading

### Format detection

Auto-detect by extension and content sniffing:

| Extension | Format |
|-----------|--------|
| `.csv`    | CSV (RFC 4180) |
| `.tsv`, `.tab` | TSV |
| `.json`   | JSON (array of objects) |
| none (stdin) | Sniff: try CSV, then TSV, then whitespace-delimited |

Whitespace-delimited (`ws`) handles command output like `ps aux`, `df -h`, `ls -l` — split on runs of whitespace, first line is headers.

### Type inference

Scan all values per column and infer:

| Priority | Type      | Rule |
|----------|-----------|------|
| 1        | `int`     | All non-empty values match `^-?[0-9]+$` |
| 2        | `Decimal` | All non-empty values parse as decimal numbers (but not all int) |
| 3        | `bool`    | All non-empty values are `true`/`false` (case-insensitive) |
| 4        | `str`     | Fallback |

`Decimal` (Python's `decimal.Decimal`) is used instead of `float` to avoid IEEE 754 rounding errors. This matters for financial data — `Decimal("9.19") + Decimal("11.07")` is exactly `20.26`, not `20.259999999999998`. String values in mixed-type columns are also promoted to `Decimal` (rather than `float`) during aggregation and arithmetic.

This requires a full scan of the data before building relations. Fine for the file sizes this tool targets.

### Missing-value decomposition

When a column has missing values (empty string in CSV, missing key in JSON, etc.), the loader decomposes the data into multiple NULL-free relations rather than introducing NULLs.

Given `employees.csv`:

```
emp_id,name,dept_id,phone,email,title
1,Alice,10,555-1234,alice@x.com,Senior
2,Bob,10,,bob@x.com,
3,Carol,20,555-5678,,
4,Dave,10,555-0000,dave@x.com,Lead
5,Eve,20,,,
```

With `\load employees.csv --key=emp_id`:

1. Identify the key column(s) — specified by `--key`, or inferred (see below)
2. Identify columns with any missing values: `phone`, `email`, `title`
3. Produce one base relation with the always-present columns:
   - `employees` — `{emp_id, name, dept_id}` (5 tuples)
4. Produce one relation per optional column, containing the key + that column, only for rows where the value is present:
   - `employees_phone` — `{emp_id, phone}` (3 tuples: Alice, Carol, Dave)
   - `employees_email` — `{emp_id, email}` (3 tuples: Alice, Bob, Dave)
   - `employees_title` — `{emp_id, title}` (2 tuples: Alice, Dave)

Now the user can work with clean, NULL-free relations. The algebra handles recombination naturally:

```
-- everyone with their phone (if they have one)
employees * employees_phone

-- everyone, with or without phone
employees *: employees_phone > phones

-- who's missing an email?
employees - (employees_email # emp_id) * employees
```

### Key: three options

**`--key=attr`** — Use an existing column as the key.

**`--genkey`** — Generate a synthetic key column named `{relation}_id` with values 1, 2, 3, ... This is the right choice when the data has no natural key (log files, command output, report dumps). Composes with `--as`:

```
codd 'procs ? cpu > 5.0' --as procs=data.csv --genkey
# key column is procs_id

ps aux | codd --genkey 'stdin ? cpu > 5.0'
# key column is stdin_id
```

**Neither** — Infer the key with heuristics:

1. Look for a column where every value is unique — prefer columns named `*_id`, `id`, `key`
2. If no single unique column, try the first column
3. If ambiguous, report what was chosen so the user can override

In all cases, the loader reports which key it used so there are no surprises.

In `--strict` mode, missing values are an error instead of triggering decomposition.

### Grouping optional columns

Columns that are always present/absent together should be grouped into a single relation rather than split. If `phone` and `phone_type` are both missing on exactly the same rows, produce `employees_phone {emp_id, phone, phone_type}` rather than two separate relations.

Algorithm: group optional columns by their "present on" row set. Columns with identical row sets share a relation.

## Workspace Persistence

### Format

A workspace file (`.codd`) is a JSON document:

```json
{
  "version": 1,
  "relations": {
    "employees": {
      "attributes": ["emp_id", "name", "dept_id"],
      "tuples": [
        {"emp_id": 1, "name": "Alice", "dept_id": 10},
        {"emp_id": 2, "name": "Bob", "dept_id": 10}
      ]
    },
    "BigTeams": {
      "attributes": ["dept_id", "n"],
      "tuples": [
        {"dept_id": 10, "n": 3}
      ]
    }
  }
}
```

JSON is inspectable, diffable, and good enough for the data sizes this tool targets. Relation-valued attributes are serialized as nested arrays of objects.

### Sniffing workspace vs data

`\load` checks: does the file parse as JSON with a top-level `"version"` and `"relations"` key? If yes, it's a workspace. Otherwise, treat it as data.

## Output Formats

CLI output format is controlled by `-t`:

| Flag | Format |
|------|--------|
| `-t table` | ASCII table (default for terminal) |
| `-t csv` | CSV |
| `-t tsv` | TSV |
| `-t json` | JSON array of objects |

Default: `table` when stdout is a TTY, `csv` when piped.

## Scope

### This design

- CSV, TSV, JSON, whitespace-delimited loading
- Type inference (int, Decimal, bool, str)
- Missing-value decomposition with `--key`
- Key inference heuristics
- Optional column grouping
- CLI file arguments and stdin
- REPL: `\load`, `\save`, `\drop`, `:=` assignment
- Workspace persistence as `.codd` JSON
- Output format selection (`-t`)

### Not in this design

- Streaming / large-file support (everything loads into memory)
- Export with NULL recomposition (`\export` that joins decomposed relations back)
- Custom type definitions (domains)
- Remote data sources
- Schema files / explicit type declarations
