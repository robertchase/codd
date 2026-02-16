# Codd Prototype

A working interpreter for the relational algebra described in `documents/algebra.md`. Parses and executes queries against in-memory relations, with an interactive REPL for experimentation.

## How to run this

Install [uv](https://docs.astral.sh/uv/getting-started/installation/) if you don't have it:

```
curl -LsSf https://astral.sh/uv/install.sh | sh
```

From the `prototype/` directory, sync the environment (creates a virtualenv and installs dependencies automatically):

```
uv sync
```

Start the REPL with sample data pre-loaded:

```
uv run -m prototype.cli repl --load
```

Or evaluate a single expression:

```
uv run -m prototype.cli eval 'E ? salary > 50000 # [name salary]'
```

Run the tests:

```
uv run pytest
```

## The REPL

The REPL reads one expression per line, parses it, executes it, and prints the result as an ASCII table.

```
$ uv run -m prototype.cli repl
Codd prototype REPL
Commands: \load (load sample data), \env (show bindings), \quit (exit)

codd> \load
Loaded: E (Employee), D (Department), Phone, ContractorPay

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

codd> E * D ? dept_name = "Engineering" # [name salary]
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

- `\load` -- load the sample relations (E, D, Phone, ContractorPay)
- `\env` -- list all loaded relations with their tuple counts and attributes
- `\quit` -- exit

### Supported operators

```
?    filter            E ? salary > 50000
?!   negated filter    E ?! dept_id = 10
#    project           E # name  or  E # [name salary]
*    natural join      E * D
*:   nest join         E *: Phone > phones
@    rename            E @ [pay > salary]
+    extend            E + bonus: salary * 0.1
-    difference        A - (B)
|    union             A | (B)
&    intersect         A & (B)
/    summarize         E / dept_id [n: #.  avg: %. salary]
/.   summarize all     E /. [n: #.  total: +. salary]
/:   nest by           E /: dept_id > team
$    sort (terminal)   E $ salary-  or  E $ [salary- name]
^    take N            E $ salary- ^ 5
```

Expressions chain left-to-right. Each operator transforms the result of the previous step. `$` leaves the relational world (returns an ordered array); only `^` can follow it.
