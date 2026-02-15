# True Relational Data Interface Design

A conversation exploring what a relational data interface might look like if it followed Codd and Date's original vision rather than SQL.

## Core Principles

### Sets, Not Bags
- Relations are sets of tuples - no duplicates, no implicit ordering
- Every operation returns a relation (closure property)
- No `DISTINCT` keyword needed because distinctness is inherent
- Deduplication happens by definition at every step

### No NULLs
- NULLs break logic (three-valued logic is problematic)
- Use explicit union types (`Value | Missing | Unknown`) or separate relations for optional data
- Forces cleaner data modeling

### Strong Domains (Types)
- Not just `VARCHAR(50)` but `EmailAddress`, `Currency`, `ISBN`
- Operators respect domain semantics
- Domain constraints are part of the type, not afterthought CHECK constraints

### Relation-Valued Attributes
- Enables natural nesting without JSON escape hatches

### Named Perspective Everywhere
- No positional column references
- Tuple = set of name-value pairs, not ordered list
- Rename is a first-class operator

---

## "Always a Set" - Real-World Tensions

### Performance Cost
Deduplication requires hashing or sorting at every operation. SQL bags let you defer or skip this.

**Purist response:** Implementation concern, not model concern. Optimize lazily.

### Counting and Aggregation
```
Orders: {(order_id: 1, product: "widget"),
         (order_id: 2, product: "widget"),
         (order_id: 3, product: "gadget")}

PROJECT {product}  -- gives {"widget", "gadget"}
                   -- count information lost!
```

**Purist response:** The count is data - model it explicitly with SUMMARIZE:
```
Orders SUMMARIZE by {product} ADD {order_count: COUNT()}
-- yields {(product: "widget", order_count: 2),
--         (product: "gadget", order_count: 1)}
```

In our algebra, this is the difference between `#` (project) and `/` (summarize):

```
E: {(emp_id: 1, name: "Alice", salary: 80000),
    (emp_id: 2, name: "Alice", salary: 60000)}

E # [name]              → {(name: "Alice")}       -- one tuple, duplicates gone
E / name [n: #.]        → {(name: "Alice", n: 2)} -- count preserved explicitly
```

`# [name]` asks "what names exist?" — a set. `/` asks "how many of each?" — that's a different question. If distinguishing matters, the schema must capture it (via a key like `emp_id`). Projection to non-key attributes collapses duplicates by definition.

### Duplicates ARE the Data Sometimes
Shopping cart with 3 of the same item, event logs with repeated events.

**Purist response:** Each tuple needs identity or quantity:
```
-- Quantity attribute
CartItems: {(cart_id: 1, item: "apple", qty: 3)}

-- Or line item identity
CartItems: {(line_id: 1, cart_id: 1, item: "apple"),
            (line_id: 2, cart_id: 1, item: "apple"),
            (line_id: 3, cart_id: 1, item: "apple")}
```

### Ordering
Relations have no order. But humans need sorted output.

**Purist response:** ORDER produces an *array*, not a relation. It's a boundary operation for display:
```
Employee
  |> where .dept_id = 5
  |> project {name, salary}
  |> to_array(order_by: .salary desc)  -- leaves relational world
```

---

## Syntax: Layered Architecture

The key insight: separate the **algebra** (terse, precise, a compilation target) from the **surface syntax** (readable, translates down to the algebra). This matters more for DML than DDL — definitions are write-once-read-many and should always be readable.

This is the same pattern as LLVM IR below multiple languages, or Unix pipes as a terse algebra with higher-level tools on top.

### The Base Layer: ASCII Relational Algebra

Inspired by J (APL's successor), we use a terse symbolic language--ASCII-only digraphs. Single characters are primitives, `:` or `.` modifies them to create related operators.

```
Core operators:
  ?    where/filter
  ?!   where not (negated filter)
  #    project (pick attributes)
  *    natural join (both sides must match)
  *:   nest join (RVA — nothing lost, unmatched get empty sets)
  >    name a nested relation (used with *: and /:)
  @    rename
  +    extend (add new attributes)
  +:   modify (replace existing attributes)
  -    difference
  |    union
  &    intersect
  /    summarize by key (nest + collapse)
  /.   summarize all (collapse entire relation, no grouping key)
  /:   nest by (partition into RVA groups, no collapse)
  $    sort (terminal — leaves relational world, returns array)
  ^    take first N (from an array, follows $)

Filter comparisons (inside ?):
  =    equal (or set membership when right side is {values})
  !=   not equal
  >    greater than
  <    less than
  >=   greater or equal
  <=   less or equal
  ~    regex match
  !~   regex non-match
  ::   type check (union type variant)

Filter boolean logic (inside ? parens):
  &    AND        ? (salary > 50000 & dept_id = 10)
  |    OR         ? (salary > 50000 | dept_id = 10)
  Chained ? = AND:  ? salary > 50000 ? dept_id = 10

Sort syntax:
  $ salary          single key ascending (no brackets)
  $ salary-         single key descending (no brackets)
  $ [salary- name]  multi-key: salary desc primary, name asc secondary (brackets required)

Aggregate functions (used inside / brackets or on nested relations):
  #.   count
  +.   sum
  >.   max
  <.   min
  %.   mean

Assignment (mutation):
  :=   assign           E := <expr>
  |=   insert (union)   E |= {tuples}
  -=   delete (diff)    E -= E ? <cond>
  ?=   update           E ?= <cond> +: <modifications>
```

Everything returns a relation except `$` and `^`; everything takes a relation from the left except `^`. Operations chain left-to-right. In the following examples, `E` is an employee table, `D` is a department table:

```
-- Engineers (department 5) earning over 50k with their phones
E ? dept_id = 5 ? salary > 50000 *: Phone > phones # [name salary phones]

-- Aggregation: headcount per department
E / dept_id [n: #.  avg: %. salary  top: >. salary]

-- Extend with computed attribute, then project
E + [bonus: salary * 0.10] # [name bonus]

-- Join, filter, sort
E * D ? dept_name = "Engineering" # [name salary] $ salary-

-- Rename then union
ContractorPay @ [pay > salary] | (E # [name salary])

-- Set difference: employees with no phone on file
E # [emp_id] - (Phone # [emp_id])

-- OR condition
E ? (salary > 50000 | dept_id = 10)

-- Negated filter
E ?! dept_id = 10

-- Set membership
E ? dept_id = {10, 20, 30}

-- Regex match
E ? name ~ /^A/

-- Set membership via subquery
E ? dept_id = (E / dept_id [n: #.] ? n > 5 # [dept_id])

-- Type predicate
E ? salary :: Present

-- Top 5 by salary
E # [name salary] $ salary- ^ 5

-- Nest by, then compute from groups
E /: dept_id > team + [avg: %. team.salary  n: #. team] # [dept_id avg n]

-- Conditional aggregation
E /: dept_id > team + [eng: #. (team ? role = "engineer")] # [dept_id eng]

-- Whole-relation summary
E /. [payroll: +. salary  n: #.]
```

The `*` vs `*:` distinction carries real semantic weight. `*` is inner join (tuples can vanish). `*:` is nest join (everything preserved, unmatched get empty relations). One character of difference for one concept of difference.

#### Type boundary

`$` (sort) returns an array, not a relation. This is enforced:

```
E ? salary > 50000 # [name salary]    -- valid: relation in, relation out
E $ name ? salary > 50000              -- ERROR: ? expects relation, got array
```

`$` is always terminal. `^` (take N) follows `$` — it operates on arrays, not relations. The algebra makes the "leaving the relational world" boundary explicit.

#### Evaluation and parens

Evaluation is left-to-right. Postfix operators (`?`, `#`, `+`, `@`, `/`, `/:`, `$`, `^`) chain freely — each transforms the result of the previous step. Binary operators (`-`, `|`, `&`) combine two relations.

In a left-to-right chain, the left operand of a binary op is already fully formed. Only the right operand interrupts the chain, so **only the right operand needs parens** (when it's more than a bare relation name):

```
E # [emp_id] - (Phone # [emp_id])           -- parens on right operand
ContractorPay @ [pay > salary] | (E # [name salary])  -- same pattern
E * D ? dept_name = "Engineering"            -- * takes bare D, no parens needed
E *: Phone > phones # [name phones]          -- *: takes bare Phone, no parens needed
```

`*` and `*:` (join operators) are a special case: their right operand is always a bare relation name (plus `> alias` for `*:`), so they never need parens and read naturally in a postfix chain.

The rule: left side builds up freely, right side of binary ops gets parens when it's a compound expression. Inspired by APL's "parens when you need them" philosophy, adapted for left-to-right evaluation.

#### Bracket elision

Brackets group multiple items. Single items don't need them. This rule applies uniformly across all operators:

```
-- Project
E # name                             -- single attribute
E # [name salary]                    -- multiple attributes

-- Rename
E @ name > fullname                  -- single rename
E @ [name > fullname  dept > department]  -- multiple renames

-- Sort
E $ salary                           -- single key
E $ [salary- name]                   -- multiple keys

-- Extend
E + bonus: salary * 0.1              -- single computed attribute
E + [bonus: salary * 0.1  tax: salary * 0.3]  -- multiple
```

For `+` (extend), the single-item form works for simple expressions. Complex right-hand expressions may need brackets for the parser to know where the expression ends.

#### Summarize output

`/` produces a relation whose attributes are the **grouping key(s) plus the named aggregates**. The original attributes are gone — consumed by the aggregation:

```
E / dept_id [n: #.  avg: %. salary]              -- single grouping key, no brackets
→ attributes: {dept_id, n, avg}                   -- grouping key + aggregates

E / [dept_id quarter] [n: #.  total: +. salary]  -- multiple grouping keys, brackets
→ attributes: {dept_id, quarter, n, total}        -- both keys + aggregates
                                                   -- original attributes are gone
```

`/.` (summarize all) collapses the entire relation into a single-tuple result with only aggregate attributes — there's no grouping key to include.

#### Filter semantics

`?` keeps tuples matching a condition. `?!` keeps tuples NOT matching. Chained `?` is AND. For OR, use `|` inside parens:

```
E ? salary > 50000 ? dept_id = 10          -- AND (chained)
E ? (salary > 50000 | dept_id = 10)        -- OR (parens required)
E ? (salary > 50000 & dept_id = 10)        -- AND (explicit, same as chaining)
E ?! dept_id = 10                          -- NOT
```

`=` against a set literal `{values}` means set membership (no keyword needed):

```
E ? dept_id = {10, 20, 30}                 -- member of
E ?! dept_id = {10, 20, 30}               -- not member of
E ? dept_id = (subquery returning relation) -- membership via subquery
```

`~` is regex match, `!~` is non-match, `::` is type check:

```
E ? name ~ /^A/                            -- regex
E ? name !~ /^A/                           -- negated regex
```

:: is a variant check

```
E ? salary :: Present                      -- union type variant check
```

All filter syntax is symbolic — no keywords (`in`, `or`, `between`, `is`). `&` and `|` inside `?` parens are boolean operators on predicates, consistent with their meaning as set intersect/union on relations.

#### Mutation: insert, delete, update

Queries and mutations use the same algebra. A stored relation is a "relvar" (relation variable). Mutation is assigning a new value to the relvar — the right side is a relational expression.

**Assignment operators:**

```
:=   assign          E := <expr>
|=   insert (union)  E |= {tuples}
-=   delete (diff)   E -= E ? <cond>
?=   update          E ?= <cond> +: <modifications>
```

**Insert** — union with new tuples:

```
E |= {(emp_id: 42, name: "Alice", salary: 75000, dept_id: 10)}

E |= {(emp_id: 42, name: "Alice", salary: 75000, dept_id: 10),
      (emp_id: 43, name: "Frank", salary: 60000, dept_id: 20)}
```

**Delete** — remove matching tuples:

```
E -= E ? dept_id = 5           -- remove dept 5 employees
E := E ?! dept_id = 5          -- equivalent: keep everything NOT in dept 5
```

**Update** — modify attribute values in matching tuples. `+:` modifies existing attributes (vs `+` which extends with new ones):

```
-- Explicit: split, modify, union
E := (E ?! dept_id = 5) | (E ? dept_id = 5 +: salary: salary * 1.1)

-- Sugar: ?= applies +: to matching tuples
E ?= dept_id = 5 +: salary: salary * 1.1

-- Multiple modifications
E ?= dept_id = 5 +: [salary: salary * 1.1  status: "reviewed"]
```

Domain constraints, key constraints, and relation-spanning constraints are checked against the *result* — the new value of E. If anything is violated, the assignment fails. The relvar never holds an invalid value. With deferred constraints, this check happens at transaction commit.

#### Transactions

A transaction is a sequence of mutations that moves the database from one valid state to another. Intermediate states can violate constraints — constraints are checked at commit.

Transaction boundaries are structural, not data operations — so they use prose (like DDL), while the mutations inside use the algebra:

```
transaction
  Accounts ?= id = 1 +: balance: balance - 500
  Accounts ?= id = 2 +: balance: balance + 500
commit
```

A standalone mutation outside a `transaction`/`commit` block is an implicit single-statement transaction.

**Rollback** — explicit abort, or implicit if constraints fail at commit:

```
transaction
  Accounts ?= id = 1 +: balance: balance - 500
  -- oops, abort
rollback
```

**Nested transactions** — inner transactions are savepoints. Rolling back inner doesn't abort outer. Constraints checked at outermost commit:

```
transaction
  E |= {(emp_id: 42, name: "Alice", salary: 75000, dept_id: 10)}

  transaction
    E ?= emp_id = 42 +: salary: 80000
  commit

  E ?= emp_id = 42 +: dept_id: 20
commit
```

**Isolation** — serializable by default. Lower isolation levels are performance optimizations that introduce anomalies (dirty reads, phantom reads, write skew). Rather than SQL's opaque isolation levels, opt in to specific anomalies you're willing to tolerate:

```
transaction (allow: phantom-reads)
  ...
commit
```

Most transactions just use `transaction` / `commit` and get full serializability. Weaker isolation is an explicit, named trade-off — consistent with the "permissiveness defers pain" philosophy.

### The Prose Layer

Translates one-to-one down to base operators. Same semantics, different audience:

```
Prose                          Base
─────────────────────────────  ────
from R                         R
  where <cond>                 ? <cond>
  take [attrs]                 # [attrs]
  with S matched by <attr>     * S       (natural join)
  including S as <name>        *: S > <name>  (nest join)
  per <attr> [aggs]            / <attr> [aggs]
  group by <attr>              /: <attr>
  add [computed]               + [computed]
  rename <old> to <new>        @ [old > new]
  ordered by <attr>            $ <attr> / $ [multi-key]
  first N                      ^ N
  without S                    - S       (difference)
  also S                       | S       (union)
  overlap S                    & S       (intersect)
```

Equivalent expressions:

```
-- Prose
from Employee
  with Department matched by dept_id
  including EmployeePhone as phones
  where dept_name is "Engineering"
  take name, dept_name, phones
  ordered by name

-- Base
E * D *: Phone > phones ? dept_name = "Engineering" # [name dept_name phones] $ name
```

A beginner reads the prose. A power user writes the algebra. Either can be stored, either can be translated to the other.

### DDL Stays Readable

DDL doesn't benefit from terseness — it's read far more than it's written:

```
define Money as integer, at least 0
define Email as text, matching /^\S+@\S+\.\S+$/

relation Employee
  emp_id   EmployeeId, identifying
  name     Name
  salary   Money
  dept_id  DeptId

relation EmployeePhone
  emp_id   EmployeeId, identifying
  phone    Phone
```

### What This Enables

The terse base layer isn't just compact notation — it's a stable compilation target:

- **Multiple surface languages** can compile to it (prose, visual query builders, natural language)
- **Macros and abbreviations** are trivial — just expansions into base operators
- **Optimization** happens at the base layer once, benefiting all surfaces
- **Serialization** is simple — the base expressions are easy to parse and store
- **REPL exploration** in the terse syntax, production queries in prose

This is the same insight behind Unix (`ls | grep | sort` is a terse algebra) and behind SQL's original intent (a "user-friendly" layer over relational algebra) — except SQL baked in the wrong semantics at the algebra level.

### Earlier Syntax Sketches

For reference, other syntax styles explored before arriving at the layered architecture:

#### Tutorial D Style (Date/Darwen)
```
TYPE Money POSSREP {cents: Integer} CONSTRAINT cents >= 0;
VAR Employee REAL RELATION {
  emp_id: EmployeeId, name: Name, salary: Money, dept_id: DeptId
} KEY {emp_id};

(Employee WHERE salary > 50000) PROJECT {name, dept_id}
Employee JOIN Department
```

#### Set-Builder / Mathematical Style
```
{e.name, e.salary | e ∈ Employee, e.salary > 50000}
{e.name, d.dept_name | e ∈ Employee, d ∈ Department, e.dept_id = d.dept_id}
```

#### Pattern Matching / Logic Style (Datalog-influenced)
```
find {name, dept_name}
  from Employee {name, dept_id}
  from Department {dept_id, dept_name}

-- Named rules (reusable queries)
well_paid :: find {name, salary} from Employee where salary > 50000
```

---

## Design Philosophy

The parallel between SQL's permissiveness and NoSQL's schema-lessness:

| "Easy" choice | Disciplined choice | Trouble avoided |
|---------------|-------------------|-----------------|
| SQL bags | Relational sets | Ambiguous identity, duplicate anomalies |
| Schemaless NoSQL | Explicit schema | Data rot, inconsistent structure |
| NULLs everywhere | Explicit absence modeling | Three-valued logic bugs |
| Stringly-typed | Strong domains | Invalid data sneaking in |

**Permissiveness defers pain, it doesn't eliminate it.** You pay later with interest.

### Commitments for a "Pure" System
1. **Sets always** - model identity and quantity explicitly
2. **No NULLs** - use union types or separate relations
3. **Strong domains** - invalid values unrepresentable
4. **Explicit constraints** - database enforces invariants, not app code
5. **Closed operations** - every query returns a relation

This is the "pit of success" philosophy - make the right thing easy and the wrong thing hard.

---

## NULL Elimination Patterns

NULL conflates at least three distinct meanings:
- **Unknown** — the value exists but we don't know it (customer has a phone number, we just don't have it)
- **Inapplicable** — the attribute doesn't apply (a corporation doesn't have a birth date)
- **Absent** — no value has been provided yet

SQL mashes all three into one sentinel that poisons every expression it touches. `NULL = NULL` is not true. `NULL AND FALSE` is false but `NULL AND TRUE` is null. Aggregates silently skip NULLs.

### Pattern 1: Decomposition (6NF-style)

If an attribute is optional, it goes in its own relation:

```
-- Instead of nullable phone:
rel Employee {
  emp_id: EmployeeId @key
  name: Name
}

rel EmployeePhone {
  emp_id: EmployeeId @key
  phone: Phone
}
```

The absence of a tuple in `EmployeePhone` **is** the representation of "no phone." No sentinel needed.

**Tradeoff:** More relations to manage, but each one is fully defined — no tuple has a "hole" in it.

### Pattern 2: Explicit Union Types

```
domain MaybePhone = Present(Phone) | Missing | NotApplicable

rel Employee {
  emp_id: EmployeeId @key
  name: Name
  phone: MaybePhone
}
```

The type system forces you to handle every case:

```
Employee
  |> extend {display_phone: match .phone {
       Present(p) => format(p),
       Missing    => "(not on file)",
       NotApplicable => "(n/a)"
     }}
```

This is the `Maybe`/`Option` approach from Haskell and Rust. **Absence is data, not the absence of data.**

### Pattern 3: Specialization via Subtypes

When inapplicability is the issue, use relation subtypes:

```
rel Person {
  person_id: PersonId @key
  name: Name
}

rel NaturalPerson {
  person_id: PersonId @key
  birth_date: Date
  ssn: SSN
}

rel Corporation {
  person_id: PersonId @key
  ein: EIN
  incorporation_date: Date
}
```

A corporation never has a birth date — not because it's NULL, but because corporations aren't in the `NaturalPerson` relation. The schema makes the invalid state unrepresentable.

### Joins Without NULLs

The decomposition pattern raises a question: if you join Employee and EmployeePhone, what happens to employees without a phone?

**Natural join (inner) drops them:**

```
Employee:      {(emp_id: 1, name: "A"),
                (emp_id: 2, name: "B")}

EmployeePhone: {(emp_id: 1, phone: "555-1234")}

Employee JOIN EmployeePhone:
               {(emp_id: 1, name: "A", phone: "555-1234")}
-- B is gone
```

The result is rectangular, but incomplete. This is where SQL reaches for LEFT JOIN and hands you a NULL. The pure model uses **relation-valued attributes** instead:

```
Employee
  |> extend {phones: (EmployeePhone MATCHING {emp_id})}

→ {(emp_id: 1, name: "A", phones: {(phone: "555-1234")}),
   (emp_id: 2, name: "B", phones: {})}
```

Still rectangular — every tuple has `{emp_id, name, phones}`. But B's `phones` is the empty relation, which is a valid set, not a hole. The empty set is a value.

### RVAs vs. Document Databases

Relation-valued attributes look like document nesting, but differ in a critical way:

- **Document model** (e.g., MongoDB): nesting is storage-level and fixed. An employee is *inside* a department. Querying across that boundary is awkward.
- **RVAs**: nesting is a query-time choice. The nested relation is a real relation — you can query into it, unnest it, join on it. You could just as easily nest departments inside employees if that's what the question requires.

It's sets all the way down, not trees. **The nesting is a lens, not a cage.**

### Flat vs. Nested: When to Use Which

- **Natural join (flat)**: both sides always match (e.g., Employee-Department when every employee has a department)
- **RVA (nested)**: one-to-many or optional relationships where you'd otherwise lose tuples or duplicate rows

---

## Strong Domains

SQL types are weak — `INTEGER` and `VARCHAR(50)` describe storage, not meaning. Strong domains carry semantic identity, built-in constraints, and restricted operations.

### Semantic Identity

An employee ID and a department ID might both be integers, but comparing them is nonsense:

```
define EmployeeId as integer
define DeptId as integer

E ? emp_id = dept_id   -- TYPE ERROR: EmployeeId ≠ DeptId
E ? dept_id = 5        -- OK: literal coerces to DeptId
```

This is the "newtype" pattern from Haskell/Rust. Zero runtime cost — same bits in memory — but the engine won't let you mix them up.

### Constraints Baked Into the Type

Not bolted on with CHECK constraints. The domain itself defines what values are representable:

```
define Money as integer, at least 0
define Email as text, matching /^\S+@\S+\.\S+$/
define Percentage as decimal, between 0 and 1
define USState as text, one of ["AL", "AK", "AZ", ...]
```

An invalid value can't exist. Not "we'll check on insert" but "the type literally cannot hold it." CHECK constraints are per-relation. Domains are universal — define `Email` once, use it in twenty relations, validation is guaranteed everywhere.

### Restricted and Typed Operations

Not every operation on the underlying representation makes sense for the domain:

```
Money / Quantity → UnitPrice    -- $100 / 5 items = $20/item
Money * Percentage → Money      -- $100 * 0.10 = $10
Money + Money → Money           -- $50 + $30 = $80
Money + Temperature → ERROR     -- meaningless
```

This is dimensional analysis — physics has done it for centuries. You can't add meters to seconds. Strong domains bring the same discipline to data.

### Composite Domains

Some domains have internal structure but aren't relations:

```
define Address as composite
  street: Text
  city: Text
  state: USState
  zip: ZipCode

define DateRange as composite
  start: Date
  end: Date
  constraint: start <= end
```

Whether `Address` should be a domain or a separate relation depends on usage. If you frequently filter by `state`, decompose. If you always treat the address as a unit, a composite domain keeps things cohesive.

### Domain Hierarchies

Domains can have subtype relationships derived from their constraints:

```
define PositiveInteger as integer, at least 1
define NaturalNumber as integer, at least 0
-- PositiveInteger is a subtype of NaturalNumber (every value fits)

define ContactInfo as union
  EmailContact(Email)
  PhoneContact(Phone)
  MailContact(Address)
```

A function that accepts `NaturalNumber` can take a `PositiveInteger`. But not the reverse. The subtyping isn't declared — it's derived from the constraints.

### How Much Belongs in the Database?

**Maximalist view (Date's position):** Everything. The database is the single source of truth about what data means. If `Email` is a domain, the database enforces it, no application can insert garbage.

**Pragmatic concern:** Complex domains (Luhn check for credit cards) make the database engine do work that application code might handle better. Domain evolution (adding a new `USState`) requires schema changes.

**Middle path:** The database enforces *structural* constraints (format, range, type compatibility). The application handles *semantic* validation (does this email actually receive mail?). The boundary: **can you check it by looking at the value alone?** If yes, domain constraint. If you need external state, application logic.

---

## Constraint Systems Beyond Foreign Keys

### The Problem with SQL's Constraint Model

SQL gives you a small, rigid toolkit:

- `NOT NULL` — eliminated entirely in our model
- `UNIQUE` / `PRIMARY KEY` — useful but limited
- `FOREIGN KEY` — referential integrity between two relations
- `CHECK` — per-row, per-table, **can't reference other relations**

That last limitation is the killer. Most real business rules span multiple relations: "Every department must have at least one employee." "A manager's salary must exceed every salary in their department." "An order's total must equal the sum of its line items." In SQL, these get pushed into triggers, application code, or stored procedures — scattered, unreliable, and invisible to the optimizer.

### Relation-Spanning Constraints

The database should let you declare constraints that reference any relation:

```
constraint every_dept_has_staff
  for each d in Department
  exists e in Employee
  where e.dept_id = d.dept_id

constraint manager_earns_most
  for each e in Employee
  for each m in Employee
  where e.dept_id = m.dept_id
    and m.emp_id = (Department ? dept_id = e.dept_id # [manager_id]).manager_id
  require m.salary >= e.salary

constraint order_total_consistent
  for each o in Order
  require o.total = sum(LineItem ? order_id = o.order_id # [amount])
```

Declarative — you say *what* must be true, not *how* to enforce it. The engine decides when to check.

### Transition Constraints

Rules about how data *changes*, not just its state:

```
constraint salary_never_decreases
  on update Employee
  require new.salary >= old.salary

constraint status_flow
  on update Order
  require (old.status, new.status) in
    {("pending", "confirmed"),
     ("confirmed", "shipped"),
     ("shipped", "delivered"),
     ("confirmed", "cancelled"),
     ("pending", "cancelled")}
```

SQL triggers can do this, but they're imperative (code that runs) rather than declarative (rules that hold). A declarative constraint can be reasoned about, composed, and potentially optimized. A trigger is a black box.

### Cardinality Constraints

Foreign keys say "this value must exist over there." They don't say how many:

```
constraint team_size
  for each d in Department
  require count(Employee ? dept_id = d.dept_id) between 3 and 15

constraint single_primary_phone
  for each e in Employee
  require count(EmployeePhone ? emp_id = e.emp_id ? is_primary = true) <= 1
```

### Database-Level Invariants

Constraints that span the entire database:

```
constraint total_salary_budget
  require sum(Employee # [salary]) <= Budget.annual_salary_cap

constraint no_circular_management
  for each chain in transitive_closure(Employee, manager_id -> emp_id)
  require no cycles
```

### When Are They Checked?

Three strategies:

- **Immediate:** After every operation. Safe but can make valid multi-step updates impossible (like swapping two unique values).
- **Deferred:** At transaction commit. More flexible — intermediate states can violate constraints as long as the final state is valid. SQL supports this with `DEFERRABLE` but almost nobody uses it.
- **Eventual:** For distributed systems. Violations flagged and repaired asynchronously.

A pure system probably wants deferred-by-default — the transaction is the unit of consistency, not the individual operation.

### Syntax

Constraints aren't DML — they're schema. They stay in the prose DDL:

```
relation Employee
  emp_id   EmployeeId, identifying
  name     Name
  salary   Money
  dept_id  DeptId
  constraint salary_positive: salary > 0

-- multi-relation constraints declared separately
constraint every_dept_staffed
  for each d in Department
  exists e in Employee where e.dept_id = d.dept_id
```

### The Philosophical Point

In SQL, the database is a dumb container. Business logic lives in the application. In the pure relational model, the database *understands the data*. Constraints are the mechanism — the database isn't just storing your data, it's guaranteeing its meaning. No application bug, no rogue script, no manual edit can put the data into an invalid state.

Domains make individual values correct. Constraints make the relationships between values correct. Together: **the database is the authority on what the data means**.

---

## Aggregation and SUMMARIZE

### The Problem with SQL's GROUP BY

GROUP BY silently changes what the entire query means. Before it, SELECT picks columns from rows. After it, SELECT picks grouped columns or aggregate functions — nothing else. The intermediate state (after grouping, before aggregating) has no name, can't be inspected, and can't be passed to another operation. Some databases silently pick arbitrary values for non-grouped columns (MySQL), others reject them (PostgreSQL).

GROUP BY fuses two distinct operations into one opaque step.

### Decomposing Aggregation: Nest, Then Collapse

The pure model separates what SQL conflates:

**Step 1: Partition** — group rows into nested relations using `/:` (nest by):

```
E /: dept_id > team

→ {(dept_id: 10, team: {(emp_id: 1, name: "Alice", salary: 80000),
                         (emp_id: 2, name: "Bob",   salary: 60000)}),
   (dept_id: 20, team: {(emp_id: 3, name: "Carol", salary: 55000)})}
```

This intermediate state is a real relation. Every tuple has `{dept_id, team}` where `team` is a relation-valued attribute you named with `>`. You can inspect it, filter it, pass it around.

**Step 2: Collapse** — apply aggregate functions to each nested relation using `+` (extend):

```
E /: dept_id > team + [avg: %. team.salary  n: #. team  top: >. team.salary]
                    # [dept_id avg n top]
```

**Shorthand:** `/` fuses both steps:

```
E / dept_id [n: #.  avg: %. salary  top: >. salary]
```

### Things That Fall Out Naturally

**Top-N per group** — filter/sort the nested relation directly:

```
E /: dept_id > team + [top2: team $ salary- ^ 2] # [dept_id top2]
```

**Conditional aggregation** — filter the group before counting:

```
E /: dept_id > team + [eng: #. (team ? role = "engineer")
                       mgr: #. (team ? role = "manager")]
                    # [dept_id eng mgr]
```

**Aggregates of aggregates** — summarize, then summarize again:

```
(E / dept_id [n: #.]) /. [avg_size: %. n]
```

**Whole-relation summary** — empty grouping key:

```
E /. [payroll: +. salary  n: #.]
→ {(payroll: 330000, n: 5)}
```

### Aggregate Functions and Strong Domains

Aggregate functions have typed signatures:

```
#.   Relation → NaturalNumber
+.   Relation{x: Money} → Money
%.   Relation{x: Money} → Money (or decimal variant)
>.   Relation{x: T} → T
<.   Relation{x: T} → T
```

Some results change domain: `Money / Quantity → UnitPrice`. The system needs rules for cases like `%.` on integer Money — does it return a decimal? Round? This is a real design decision that SQL dodges by being weakly typed.

### The NULL Advantage

SQL aggregates silently skip NULLs. `AVG(salary)` where three of ten values are NULL averages seven values. With no NULLs, this ambiguity vanishes — you can see exactly what set you're aggregating over:

```
-- Decomposed (6NF): only employees WITH a salary are in this relation
EmployeeSalary / dept_id [avg: %. salary]

-- Union type: the filter is visible in the query
E ? salary is Present / dept_id [avg: %. salary.value]
```

---

## Reading the Base Algebra: Detailed Walkthrough

Sample data for all examples:

```
E: {(emp_id: 1, name: "Alice", salary: 80000, dept_id: 10, status: "active",   role: "engineer"),
    (emp_id: 2, name: "Bob",   salary: 60000, dept_id: 10, status: "active",   role: "manager"),
    (emp_id: 3, name: "Carol", salary: 55000, dept_id: 20, status: "active",   role: "engineer"),
    (emp_id: 4, name: "Dave",  salary: 90000, dept_id: 10, status: "inactive", role: "engineer"),
    (emp_id: 5, name: "Eve",   salary: 45000, dept_id: 20, status: "active",   role: "engineer")}

D: {(dept_id: 10, dept_name: "Engineering"),
    (dept_id: 20, dept_name: "Sales")}

Phone: {(emp_id: 1, phone: "555-1234"),
        (emp_id: 3, phone: "555-5678")}

ContractorPay: {(name: "Frank", pay: 70000)}
```

### `E ? dept_id = 10 ? salary > 50000 *: Phone > phones # [name salary phones]`

"Show me the name, salary, and phone numbers of dept 10 employees earning over 50k."

| Step | Op | Result |
|------|-----|--------|
| `E` | start | 5 tuples |
| `? dept_id = 10` | filter | Alice, Bob, Dave (3 tuples) |
| `? salary > 50000` | filter again | Alice(80k), Bob(60k), Dave(90k) — all survive |
| `*: Phone > phones` | nest join | Each gets a `phones` RVA. Alice: `{(phone: "555-1234")}`. Bob, Dave: `{}` (empty set, not NULL) |
| `# [name salary phones]` | project | Drop emp_id, dept_id, etc. Keep name, salary, phones |

### `E / dept_id [n: #.  avg: %. salary  top: >. salary]`

"Per department: headcount, average salary, top salary."

| Step | Op | Result |
|------|-----|--------|
| `E` | start | 5 tuples |
| `/ dept_id` | group + collapse | Partition into dept 10 (Alice, Bob, Dave) and dept 20 (Carol, Eve) |
| `[n: #.]` | count per group | dept 10: 3, dept 20: 2 |
| `[avg: %. salary]` | mean per group | dept 10: 76667, dept 20: 50000 |
| `[top: >. salary]` | max per group | dept 10: 90000, dept 20: 55000 |

Result: `{(dept_id: 10, n: 3, avg: 76667, top: 90000), (dept_id: 20, n: 2, avg: 50000, top: 55000)}`

### `E + [bonus: salary * 0.10] # [name bonus]`

"Everyone's name and 10% bonus."

| Step | Op | Result |
|------|-----|--------|
| `E` | start | 5 tuples, all attributes |
| `+ [bonus: salary * 0.10]` | extend | Add `bonus` attribute to every tuple (Alice: 8000, Bob: 6000, ...) |
| `# [name bonus]` | project | Keep only name and bonus |

### `E * D ? dept_name = "Engineering" # [name salary] $ salary-`

"List engineering employees by salary, highest first."

| Step | Op | Result |
|------|-----|--------|
| `E * D` | natural join | Combine on shared `dept_id`. All 5 employees get their `dept_name` |
| `? dept_name = "Engineering"` | filter | Alice, Bob, Dave |
| `# [name salary]` | project | Just name and salary |
| `$ salary-` | sort descending | **Leaves relational world → array.** `[(Dave, 90000), (Alice, 80000), (Bob, 60000)]` |

### `ContractorPay @ [pay > salary] | (E # [name salary])`

"Combine employees and contractors into one compensation list."

| Step | Op | Result |
|------|-----|--------|
| `ContractorPay` | start | `{(name: "Frank", pay: 70000)}` |
| `@ [pay > salary]` | rename | `{(name: "Frank", salary: 70000)}` — now has same attributes as target |
| `\|` | union (binary) | Right operand in parens: `(E # [name salary])` → 5 tuples with `{name, salary}` |
| result | | All 6 combined. Both sides must have same attributes |

### `E # [emp_id] - (Phone # [emp_id])`

"Which employees have no phone on file?"

| Step | Op | Result |
|------|-----|--------|
| `E` | start | 5 tuples |
| `# [emp_id]` | project | `{1, 2, 3, 4, 5}` (as emp_id tuples) |
| `-` | difference (binary) | Right operand in parens: `(Phone # [emp_id])` → `{1, 3}` |
| result | | `{2, 4, 5}` — employees NOT in Phone |

### `E /: dept_id > team + [top2: team $ salary- ^ 2] # [dept_id top2]`

"Top 2 earners per department."

| Step | Op | Result |
|------|-----|--------|
| `E /: dept_id > team` | nest by | Each dept gets a `team` RVA (named via `>`) containing its employees |
| `team $ salary-` | sort each group | Sort each team by salary descending (→ array) |
| `^ 2` | take 2 | First 2 from each sorted array |
| `+ [top2: ...]` | extend | Attach as `top2` attribute |
| `# [dept_id top2]` | project | Dept 10: [(Dave, 90k), (Alice, 80k)]. Dept 20: [(Carol, 55k), (Eve, 45k)] |

### `(E / dept_id [n: #.]) /. [avg_size: %. n]`

"What's the average department size?"

| Step | Op | Result |
|------|-----|--------|
| `E / dept_id [n: #.]` | inner summarize | `{(dept_id: 10, n: 3), (dept_id: 20, n: 2)}` |
| `/.` | summarize all | Entire relation as one group, no grouping key in output |
| `[avg_size: %. n]` | mean of n | `{(avg_size: 2.5)}` — single-tuple relation |
