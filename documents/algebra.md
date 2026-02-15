# True Relational Algebra: Introduction

## Core Principles

### Sets, Not Bags
- Relations are sets of tuples — no duplicates, no implicit ordering
- Every operation returns a relation (closure property)
- No `DISTINCT` keyword needed because distinctness is inherent

### No NULLs
- NULLs break logic (three-valued logic is problematic)
- Use explicit union types or separate relations for optional data

### Strong Domains (Types)
- Not just `INTEGER` but `EmployeeId`, `Money`, `Email`
- You can't accidentally compare an `EmployeeId` to a `DeptId`
- Constraints are part of the type, not afterthought CHECK constraints

### Relation-Valued Attributes
- A tuple can contain a nested relation as an attribute value
- The empty set is a value, not NULL

### Named Perspective Everywhere
- Tuple = set of name-value pairs, not an ordered list
- No positional column references

---

## Sample Data

All examples use these relations.

**Employee (E):**

| emp_id | name  | salary | dept_id | role     |
|--------|-------|--------|---------|----------|
| 1      | Alice | 80000  | 10      | engineer |
| 2      | Bob   | 60000  | 10      | manager  |
| 3      | Carol | 55000  | 20      | engineer |
| 4      | Dave  | 90000  | 10      | engineer |
| 5      | Eve   | 45000  | 20      | engineer |

**Department (D):**

| dept_id | dept_name   |
|---------|-------------|
| 10      | Engineering |
| 20      | Sales       |

**EmployeePhone (Phone):**

| emp_id | phone    |
|--------|----------|
| 1      | 555-1234 |
| 3      | 555-5678 |
| 3      | 555-9999 |

**ContractorPay:**

| name  | pay   |
|-------|-------|
| Frank | 70000 |

---

## The Algebra

Expressions are read left-to-right. Each operator takes the relation produced by the previous step and returns a new relation. This is the closure property — relations in, relations out, all the way through.

### Project: `#`

`#` picks attributes from a relation, discarding the rest.

```
E # name
```

| Step | What happens |
|------|-------------|
| `E` | Start with the Employee relation (5 tuples, 5 attributes each) |
| `# name` | Keep only the `name` attribute, discard everything else |

Result:

| name  |
|-------|
| Alice |
| Bob   |
| Carol |
| Dave  |
| Eve   |

The result is a relation — a set of tuples, each with one attribute. Five employees, five distinct names, five tuples.

What if two employees shared the same name? The result would collapse them — relations are sets, and sets don't have duplicates. `# name` asks "what names exist?", not "how many of each?"

Multiple attributes use brackets:

```
E # [name salary]
```

| name  | salary |
|-------|--------|
| Alice | 80000  |
| Bob   | 60000  |
| Carol | 55000  |
| Dave  | 90000  |
| Eve   | 45000  |

Single attribute, no brackets. Multiple attributes, brackets. This rule applies to all operators.

### Filter: `?`

`?` keeps tuples matching a condition.

```
E ? salary > 50000
```

| Step | What happens |
|------|-------------|
| `E` | Start with Employee (5 tuples) |
| `? salary > 50000` | Keep only tuples where salary exceeds 50000 |

Result:

| emp_id | name  | salary | dept_id | role     |
|--------|-------|--------|---------|----------|
| 1      | Alice | 80000  | 10      | engineer |
| 2      | Bob   | 60000  | 10      | manager  |
| 3      | Carol | 55000  | 20      | engineer |
| 4      | Dave  | 90000  | 10      | engineer |

Eve (45000) is gone. All attributes are preserved — `?` narrows the tuples, not the attributes.

### Chaining: filter then project

Operators chain left-to-right. Each one transforms the result of the previous step.

```
E ? salary > 50000 # [name salary]
```

| Step | What happens |
|------|-------------|
| `E` | Start with Employee (5 tuples) |
| `? salary > 50000` | Keep tuples where salary > 50000 (4 tuples remain) |
| `# [name salary]` | Keep only name and salary |

Result:

| name  | salary |
|-------|--------|
| Alice | 80000  |
| Bob   | 60000  |
| Carol | 55000  |
| Dave  | 90000  |

### Multiple filters: chained `?` = AND

Each `?` narrows further. Chaining is implicit AND.

```
E ? dept_id = 10 ? salary > 70000
```

| Step | What happens |
|------|-------------|
| `E` | 5 tuples |
| `? dept_id = 10` | Keep dept 10 only → Alice, Bob, Dave |
| `? salary > 70000` | Keep salary > 70000 → Alice, Dave |

Result:

| emp_id | name  | salary | dept_id | role     |
|--------|-------|--------|---------|----------|
| 1      | Alice | 80000  | 10      | engineer |
| 4      | Dave  | 90000  | 10      | engineer |

For OR, use `|` inside parentheses:

```
E ? (dept_id = 20 | salary > 80000)
```

Result: Carol (dept 20), Eve (dept 20), and Dave (salary 90000).

### Natural join: `*`

`*` combines two relations on their shared attribute names. Both sides must match.

```
E * D
```

Employee and Department share `dept_id`. Every employee tuple is matched with its department tuple, and the attributes are merged:

| emp_id | name  | salary | dept_id | role     | dept_name   |
|--------|-------|--------|---------|----------|-------------|
| 1      | Alice | 80000  | 10      | engineer | Engineering |
| 2      | Bob   | 60000  | 10      | manager  | Engineering |
| 3      | Carol | 55000  | 20      | engineer | Sales       |
| 4      | Dave  | 90000  | 10      | engineer | Engineering |
| 5      | Eve   | 45000  | 20      | engineer | Sales       |

The result is a relation. You can keep chaining:

```
E * D ? dept_name = "Engineering" # [name salary]
```

| Step | What happens |
|------|-------------|
| `E * D` | Join on dept_id (5 tuples, now with dept_name) |
| `? dept_name = "Engineering"` | Keep engineering only → Alice, Bob, Dave |
| `# [name salary]` | Keep name and salary |

Result:

| name  | salary |
|-------|--------|
| Alice | 80000  |
| Bob   | 60000  |
| Dave  | 90000  |

### Nest join: `*:`

`*` drops tuples that don't match. `*:` keeps everything — unmatched tuples get an empty set instead of disappearing. The nested relation is named with `>`.

```
E *: Phone > phones
```

| Step | What happens |
|------|-------------|
| `E` | 5 tuples |
| `*: Phone > phones` | For each employee, nest matching Phone tuples into a `phones` attribute |

Result:

| emp_id | name  | salary | dept_id | role     | phones                           |
|--------|-------|--------|---------|----------|----------------------------------|
| 1      | Alice | 80000  | 10      | engineer | {(phone: 555-1234)}              |
| 2      | Bob   | 60000  | 10      | manager  | {}                               |
| 3      | Carol | 55000  | 20      | engineer | {(phone: 555-5678), (phone: 555-9999)} |
| 4      | Dave  | 90000  | 10      | engineer | {}                               |
| 5      | Eve   | 45000  | 20      | engineer | {}                               |

Nobody is lost. Bob, Dave, and Eve have no phone on file — their `phones` is the empty set, which is a value, not NULL. Carol has two phone numbers — her `phones` is a set of two tuples.

### Extend: `+`

`+` adds computed attributes to each tuple.

```
E + bonus: salary * 0.1 # [name salary bonus]
```

| Step | What happens |
|------|-------------|
| `E` | 5 tuples |
| `+ bonus: salary * 0.1` | Add a `bonus` attribute to every tuple |
| `# [name salary bonus]` | Keep only these three |

Result:

| name  | salary | bonus |
|-------|--------|-------|
| Alice | 80000  | 8000  |
| Bob   | 60000  | 6000  |
| Carol | 55000  | 5500  |
| Dave  | 90000  | 9000  |
| Eve   | 45000  | 4500  |

### Rename: `@`

`@` changes attribute names. Inside the brackets, `>` means "becomes."

```
ContractorPay @ [pay > salary]
```

| Step | What happens |
|------|-------------|
| `ContractorPay` | `{(name: "Frank", pay: 70000)}` |
| `@ [pay > salary]` | Rename `pay` to `salary` |

Result:

| name  | salary |
|-------|--------|
| Frank | 70000  |

This is useful for making two relations compatible for union. Union requires both sides to have the same attributes:

```
ContractorPay @ [pay > salary] | (E # [name salary])
```

Result: all 5 employees plus Frank, each with `{name, salary}`.

### Set difference: `-`

`-` returns tuples in the left side that aren't in the right side. The right side needs parentheses when it's a compound expression:

```
E # emp_id - (Phone # emp_id)
```

| Step | What happens |
|------|-------------|
| `E # emp_id` | Project to emp_id: `{1, 2, 3, 4, 5}` |
| `- (Phone # emp_id)` | Subtract Phone projected to emp_id: `{1, 3}` |

Result:

| emp_id |
|--------|
| 2      |
| 4      |
| 5      |

Employees with no phone on file. The left side builds up freely; only the right side of a binary operator needs parentheses.

### Summarize: `/`

`/` groups tuples by a key and collapses each group with aggregate functions.

```
E / dept_id [n: #.  avg: %. salary]
```

| Step | What happens |
|------|-------------|
| `E` | 5 tuples |
| `/ dept_id` | Group by dept_id: dept 10 (Alice, Bob, Dave) and dept 20 (Carol, Eve) |
| `[n: #.]` | Count tuples per group |
| `[avg: %. salary]` | Mean salary per group |

Result:

| dept_id | n | avg   |
|---------|---|-------|
| 10      | 3 | 76667 |
| 20      | 2 | 50000 |

The result has the grouping key(s) plus the named aggregates. The original attributes (name, salary, etc.) are gone — consumed by the aggregation.

Aggregate functions: `#.` (count), `+.` (sum), `>.` (max), `<.` (min), `%.` (mean).

### Summarize all: `/.`

`/.` collapses the entire relation into a single tuple — no grouping key.

```
E /. [n: #.  total: +. salary]
```

Result:

| n | total  |
|---|--------|
| 5 | 330000 |

### Nest by: `/:`

`/:` groups like `/` but doesn't collapse — it produces a nested relation you can operate on. Name it with `>`.

```
E /: dept_id > team + [top: >. team.salary] # [dept_id top]
```

| Step | What happens |
|------|-------------|
| `E /: dept_id > team` | Group by dept_id, nest each group into `team` |
| `+ [top: >. team.salary]` | For each group, compute the max salary from `team` |
| `# [dept_id top]` | Keep dept_id and top |

Result:

| dept_id | top   |
|---------|-------|
| 10      | 90000 |
| 20      | 55000 |

The difference from `/`: the intermediate state (with the `team` RVA) is a real relation you can filter, extend, or otherwise manipulate before collapsing.

### Sort: `$` and take: `^`

`$` sorts a relation. **This leaves the relational world** — the result is an array (ordered), not a relation (unordered set). No further relational operations can follow.

```
E # [name salary] $ salary-
```

| Step | What happens |
|------|-------------|
| `E # [name salary]` | Project to name and salary |
| `$ salary-` | Sort by salary descending → **array** |

Result (ordered):

| name  | salary |
|-------|--------|
| Dave  | 90000  |
| Alice | 80000  |
| Bob   | 60000  |
| Carol | 55000  |
| Eve   | 45000  |

`^` takes the first N from a sorted array:

```
E # [name salary] $ salary- ^ 3
```

Result: Dave, Alice, Bob — the top 3 earners.

Multi-key sort uses brackets:

```
E # [name salary dept_id] $ [dept_id salary-]
```

Sort by dept_id ascending (primary), then salary descending (secondary). A `-` suffix means descending; no suffix means ascending.

### Negated filter: `?!`

`?!` keeps tuples that do NOT match.

```
E ?! role = "engineer"
```

Result:

| emp_id | name | salary | dept_id | role    |
|--------|------|--------|---------|---------|
| 2      | Bob  | 60000  | 10      | manager |

---

## Quick Reference

```
?    filter            E ? salary > 50000
?!   negated filter    E ?! dept_id = 10
#    project           E # name  /  E # [name salary]
*    natural join      E * D
*:   nest join         E *: Phone > phones
@    rename            E @ [pay > salary]
+    extend            E + bonus: salary * 0.1
+:   modify            E +: salary: salary * 1.1
-    difference        E # emp_id - (Phone # emp_id)
|    union             (E # [name salary]) | (Contractors # [name salary])
&    intersect         (E # emp_id) & (Phone # emp_id)
/    summarize         E / dept_id [n: #.  avg: %. salary]
/.   summarize all     E /. [n: #.  total: +. salary]
/:   nest by           E /: dept_id > team
$    sort → array      E $ salary-  /  E $ [salary- name]
^    take N            E $ salary- ^ 5
```

