"""Ops reference – display language primitives."""

from codd.repl.formatter import _build_table

_RELATIONAL = [
    ("?", "Filter", "E ? salary > 50000"),
    ("?!", "Negated filter", 'E ?! role = "engineer"'),
    ("#", "Project", "E # [name salary]"),
    ("#!", "Remove", "E #! emp_id"),
    ("*.", "Natural join", "E *. D"),
    ("*<", "Left join", "E *< D [col: 0]"),
    ("+:", "Extend", "E +: bonus: salary * 0.1"),
    ("=:", "Modify", "E =: salary: salary * 1.1"),
    ("@", "Rename", "E @ [pay salary]"),
    ("|.", "Union", "E |. (D)"),
    ("-.", "Difference", "E -. (D)"),
    ("&.", "Intersect", "E &. (D)"),
    ("/.", "Summarize", "E /. dept_id [n: #. avg: %. salary]  or  E /. [n: #.]"),
    ("/*", "Broadcast agg", "E /* dept_id [avg: %. salary]  or  E /* [total: +. salary]"),
    ("/^", "Rank (dense)", "E /^ r: salary-"),
    ("/&", "Bucket (n-tile)", "E /& q: salary- 4"),
    ("/>", "Split (explode)", 'R /> tags ","  or  R /> [tag n]: tags ","'),
    ("::", "Apply schema", "R :: S  or  R ::"),
    ("?.", "Describe columns", 'R ?.  or  R ?. "full"'),
]

_NESTED = [
    ("*:", "Nest join", "E *: phones: Phone"),
    ("<:", "Unnest", "E <: phones"),
    ("/:", "Nest by", "E /: team: dept_id  or  E /: team: [dept_id role]"),
    ("n.", "Collect (aggregate)", "E /. dept_id [members: n. name]"),
]

_DISPLAY = [
    ("$", "Sort", "E $ salary-"),
    ("$.", "Order columns", "E $. [salary name]"),
    ("^", "Take", "E $ salary- ^ 3"),
    ("r.", "Rotate", "E ? name = \"Alice\" r."),
]

_AGGREGATES = [
    ("#.", "Count", "#."),
    ("+.", "Sum", "+. salary"),
    (">.", "Max", ">. salary"),
    ("<.", "Min", "<. salary"),
    ("%.", "Mean", "%. salary"),
    ("p.", "Percent", "p. salary ~ 1"),
]

_EXPRESSIONS = [
    ("+ - * / // %", "Arithmetic", "salary * 0.1  or  salary // 1000  or  i % 2"),
    ("= != < > <= >=", "Comparison", "salary > 50000  or  status != \"inactive\""),
    ("=~ !=~", "Regex match", 'name =~ "^A"  or  name !=~ "test"'),
    ("in.", "Membership", "status in. (Statuses # name)"),
    ("and or not", "Logical", "age > 18 and status = \"active\"  or  not flag"),
    ("~", "Precision", "%. salary ~ 2"),
    (".s", "String", 'name .s [1 3]  or  name .s "upper"'),
    (".d", "Date", "col .d  or  col .d 'year'  or  col .d '{dd}/{mm}/{yyyy}'"),
    (".f", "Format", '"{name} earns {salary}" .f  or  "{n:05d}" .f'),
    (".r", "Regex replace", 'val .r "[$ ,]" ""  or  name .r "(\\w+)" "[$1]"'),
    (".as", "Type cast", 'amount .as int  or  val .as float'),
    ("?:", "Ternary", '?: dept_id = 10 "eng" "other"'),
]

_SOURCES = [
    ("i.", "Iota (1-based)", "i. 5  or  i. month: 12"),
    ("I.", "Iota (0-based)", "I. 5  or  I. idx: 10"),
    ("{}", "Relation literal", '{name age; "Alice" 30; "Bob" 25}'),
]

_OTHER = [
    (":=", "Assignment", "high := E ? salary > 70000"),
    (":= type", "Type alias", 'Money := type decimal(2)  or  Status := type in(S, n)'),
]

_HEADERS = ["Primitive", "Name", "Example"]


_DETAIL: dict[str, str] = {
    ".s": """\
.s — String operations

  Substring (bracket form):
    expr .s [start]         From position to end
    expr .s [start end]     From start to end (inclusive)

    1-based indexing. Negative indices count from end.
    Out-of-bounds indices are clamped silently.

    name .s [1 3]           "Alice" → "Ali"
    name .s [-2]            "Alice" → "ce"
    name .s [2 4]           "Alice" → "lic"

  Transforms (string form):
    expr .s "upper"         Uppercase
    expr .s "lower"         Lowercase
    expr .s "title"         Title case (each word capitalized)
    expr .s "cap"           Capitalize (first letter upper, rest lower)
    expr .s "trim"          Strip whitespace (both sides)
    expr .s "rtrim"         Strip whitespace (right)
    expr .s "ltrim"         Strip whitespace (left)
    expr .s "len"           Length (returns int)

    name .s "upper"         "Alice" → "ALICE"
    name .s "lower"         "Alice" → "alice"
    name .s "title"         "alice smith" → "Alice Smith"
    name .s "cap"           "alice smith" → "Alice smith"
    name .s "len"           "Alice" → 5""",
    ".d": """\
.d — Date operations

  Promotion (bare):
    expr .d                 String → date
    "2026-03-17" .d         date(2026, 3, 17)
    "today" .d              current date

  Extraction (keyword):
    expr .d "year"          → int (e.g. 2026)
    expr .d "month"         → int (1-12)
    expr .d "day"           → int (1-31)
    expr .d "week"          → int (ISO week number)
    expr .d "ww"            → str, zero-padded week (e.g. "05")
    expr .d "dow"           → int (1=Mon, 7=Sun)
    expr .d "q"             → int (1-4, quarter)
    expr .d "qq"            → str ("Q1"-"Q4")

  Formatting (pattern with {}):
    expr .d "{dd}/{mm}/{yyyy}"    → "17/03/2026"
    expr .d "{d} {mmm} {yyyy}"    → "17 MAR 2026"
    expr .d "{ddd}"               → "TUE"
    expr .d "{yyyy}-W{ww}"        → "2026-W05"
    expr .d "{yyyy}-{qq}"         → "2026-Q1"

    Tokens: {d} {dd} {m} {mm} {mmm} {yy} {yyyy} {week} {ww} {dow} {ddd} {q} {qq}

  Arithmetic:
    date + int              Add N days
    date - int              Subtract N days
    date - date             Difference in days (int)""",
    "=~": """\
=~ !=~ — Regex match / non-match

  Used in filter conditions. The RHS is a regex pattern (string).
  Uses substring matching (re.search), not full-string matching.
  Anchor with ^ and $ if needed.

  Syntax:
    R ? attr =~ "pattern"    Tuples where attr matches pattern
    R ? attr !=~ "pattern"   Tuples where attr does not match

  Examples:
    E ? name =~ "^A"         Names starting with A
    E ? name =~ "(?i)alice"  Case-insensitive match
    E ? email !=~ "@test"    Emails not containing @test
    E ? code =~ "^[A-Z]{3}$" Exactly 3 uppercase letters""",
    "*<": """\
*< — Left join

  Like *. (natural join) but keeps every tuple from the left relation.
  Where no matching right tuple exists, right-only attributes are filled
  from the defaults bracket.  An error is raised if an unmatched tuple
  exists and a required default is missing.

  Syntax:
    R *< S                     Left join, no defaults (error if unmatched)
    R *< S [col: expr ...]     Left join with fill values for right-only attrs

  Examples:
    grid *< sales [total: 0]   Fill missing weeks with 0
    E *< Dept [name: "?"]      Each employee keeps their dept name; unmatched get "?"

  The right-side expression must be a bare name or parenthesized expression.
  Defaults are evaluated as constants — attribute references are not in scope.""",
    "=": """\
= != < > <= >= — Comparison operators

  Used in filter predicates and expressions.  Both sides are expressions;
  comparisons are type-aware (int vs float vs str vs date).

  Operators:
    =     Equal
    !=    Not equal
    <     Less than
    >     Greater than
    <=    Less than or equal
    >=    Greater than or equal

  Examples:
    E ? salary > 50000
    E ? status != "inactive"
    E ? hired .d >= "2024-01-01" .d
    E +: senior: ?: age >= 40 1 0

  String comparisons use lexicographic order.
  Date comparisons require both sides to be date values (use .d to promote).""",
    "and": """\
and or not — Logical operators

  Combine boolean sub-expressions in filter predicates.
  Operator precedence (low → high):  or  →  and  →  not  →  comparison.
  Use parentheses to override.

  Operators:
    and    Both conditions must hold
    or     Either condition holds
    not    Negates a condition

  Examples:
    E ? age > 18 and status = "active"
    E ? dept = "eng" or dept = "ops"
    E ? not flag
    E ? (a > 1 or b > 1) and c = 0   Parens change precedence""",
    ":= type": """\
:= type — User-defined type alias

  Binds a name in the type namespace (separate from relations) to a
  canonical type string.  Use the name anywhere a built-in type is
  accepted: in .as casts, in schema relations, or as the target of
  another alias.

  Syntax:
    Name := type <target>

  Where <target> is:
    int, str, float, decimal, date, bool    Built-in
    decimal(N)                               Parameterised built-in
    in(Relation, attr)                       Membership constraint
    OtherUDT                                 Another defined UDT

  Examples:
    Money  := type decimal(2)
    Status := type in(Statuses, name)
    Age    := type int
    Price  := type Money                    Alias of an alias

  Usage:
    \\load rows.csv :: {attr type; "salary" "Money"; "age" "Age"}
    E +: net: amount .as Money
    E ? age .as Age > 18

  Cycles (A -> B -> A) raise an error when the alias is resolved.""",
    ".f": """\
.f — Format string

  Interpolates attribute values into a string template.
  Braces enclose an attribute name, optionally followed by a Python
  format spec after a colon.

  Syntax:
    "text {attr} text" .f
    "text {attr:spec} text" .f

  Basic examples:
    "{name} earns {salary}" .f       → "Alice earns 95000"
    "id={emp_id}" .f                 → "id=1"

  Format specs (Python mini-language):
    "{n:05d}" .f                     Zero-pad integer to width 5 → "00042"
    "{n:>10}" .f                     Right-align in field of 10  → "        42"
    "{n:<10}" .f                     Left-align in field of 10   → "42        "
    "{salary:.2f}" .f                Two decimal places          → "95000.00"
    "{ratio:.1%}" .f                 Percentage                  → "42.0%"

  Full Python format spec reference applies after the colon.""",
    "/>": """\
/> — Split (explode rows by a delimited string column)

  Splits the string value of a column in each tuple by a regex pattern
  and emits one tuple per piece.  The common case — "expand a CSV
  column into rows" — becomes a single postfix operation.

  Syntax:
    R /> col pattern                 Replace col with each split piece
    R /> new: col pattern            Add new column, keep col
    R /> [new pos]: col pattern      Named + 1-based position column
    R /> [col pos]: col pattern      In-place + position column

  The pattern is a regex (same flavour as =~ and .r).  To match a literal
  special char, escape it: "\\.", "\\(", etc.

  Examples:
    R /> tags ","                    Split comma-separated tags in place
    R /> tag: tags ","               Add "tag" column, keep tags string
    R /> word: text "\\s+"           Split on whitespace runs
    R /> tag: tags "," ?! tag = ""   Drop empty pieces
    R /> [tag n]: tags ","           Keep original order via n (1, 2, 3)
    R /> [tag n]: tags "," $ [id n]  Sort by original row then position

  Notes:
    - The source column must be a string; non-string values raise.
    - Empty strings between delimiters are kept (re.split semantics).
    - Named form: error if new already exists (unless new == col).
    - Position column is typed int; errors if it collides with any
      attribute other than the split source.""",
    "/^": """\
/^ — Dense rank

  Adds a new attribute whose value is the 1-based dense rank of each
  tuple in the sort order defined by the key(s).  Tied tuples get the
  same rank; there are no gaps (dense, not sparse).

  The result is still a set — the added attribute is a deterministic
  function of each tuple's values relative to the others.

  Syntax:
    R /^ name: key             Rank by a single key (ascending)
    R /^ name: key-            Descending
    R /^ name: [key1 key2-]    Composite key, key2 descending

  Examples:
    Sales /^ r: amount-        Highest amount gets r=1
    R /^ ord: [dept salary-]   Rank by dept then salary desc
    i. 5 /^ r: i               r = i (1..5)

  Notes:
    - The added column has schema type int.
    - Error if *name* collides with an existing attribute; remove
      first with #! if you want to replace.
    - An empty relation passes through unchanged (still empty).""",
    "/&": """\
/& — Bucket (equal-frequency n-tile)

  Sorts by the key(s), then assigns each tuple a bucket number 1..N.
  Tied tuples (sharing a dense rank) always go in the same bucket, so
  the operation is deterministic.

  Bucket 1 is at the "front" of the sort: with a descending key, the
  highest values land in bucket 1.

  Syntax:
    R /& name: key N             Single key (ascending)
    R /& name: key- N            Descending
    R /& name: [key1 key2-] N    Composite key

  Examples:
    Sales /& q: amount- 4        Quartiles of amount, q=1 is highest
    R /& d: salary 10            Deciles of salary (lowest in d=1)
    E /& tier: [dept salary-] 3  3 tiers per (dept, salary desc)

  Notes:
    - The added column has schema type int.
    - N must be a positive integer literal.
    - Bucket sizes are roughly equal but can vary because ties never
      cross bucket boundaries.
    - Error if *name* collides with an existing attribute.
    - Like /^, sort comparison respects the source's schema (use a
      typed column or .as for numeric vs lex ordering).""",
    "?.": """\
?. — Describe columns (column statistics)

  Returns a relation with one row per attribute in the source, summarising
  what's in each column.  The result is itself a relation, so it composes
  with the rest of the language — you can filter, sort, project the stats.

  Syntax:
    R ?.              Describe (str-inferred columns get blank min/max/sample)
    R ?. "full"       Populate min/max/sample for every column

  Result columns:
    attr      str   attribute name
    type      str   declared schema type
    inferred  str   narrowest type that fits all non-empty values
    distinct  int   number of distinct values
    pct       int   distinct as a percentage of row count (0-100)
    empty     int   count of empty-string ("") values (zeros and False
                    are real values, not empties)
    min       str   minimum value (formatted)
    max       str   maximum value (formatted)
    sample    str   one example value (formatted)

  Useful patterns:
    - "inferred" reveals columns whose declared type is "str" but whose
      values actually look numeric / dated / boolean (a CSV-loaded
      column that should be reschemed).
    - "pct" close to 100 means values are nearly all unique (key-like);
      a low pct suggests a categorical column.

  Examples:
    R ?.                                       All columns described
    R ?. "full"                                Include str min/max/sample
    R ?. $. [attr type inferred distinct pct empty min max sample]   Nice order
    R ?. ? type != inferred                    Columns worth retyping
    R ?. ? pct < 25                            Likely categorical columns
    R ?. ? empty > 0                           Columns with missing data
    R ?. # [attr distinct pct]                 Cardinality overview

  Notes:
    - Walks every tuple to compute stats.  Not free on large relations.
    - The output schema is fixed (int for distinct/empty, str for the rest)
      so all min/max are formatted as strings regardless of source type.""",
    "/*": """\
/* — Broadcast aggregate

  Like /. (summarize) but broadcasts aggregate values back to every
  original tuple instead of collapsing groups. Equivalent to SQL's
  window functions with PARTITION BY.

  Syntax:
    R /* key [name: agg_expr ...]       Partitioned by key
    R /* [key1 key2] [name: agg_expr]   Composite key
    R /* [name: agg_expr ...]           Over entire relation (no partition)
    R /* key agg_expr                   Auto-named single aggregate

  Examples:
    E /* dept_id [avg: %. salary]       Each employee gets dept average
    E /* dept_id [n: #.  total: +. salary]
    E /* [total: +. salary]             Same total on every tuple
    E /* dept_id #.                     Auto-names to "count"

  The result has all original attributes plus the new aggregate columns.
  Compare with /. which collapses groups to one row each.""",

    # --- Relational primitives ---
    "?": """\
? — Filter (restriction)

  Keeps tuples for which the condition is true.  The condition can be
  a simple comparison, or a parenthesised combination using & (and)
  and | (or).

  Syntax:
    R ? cond
    R ? (cond1 & cond2)
    R ? (cond1 | cond2)

  Examples:
    E ? salary > 50000
    E ? role = "engineer"
    E ? (dept_id = 10 & salary > 60000)
    E ? salary in. (Highpaid # salary)
    E ? name =~ "^A"

  Notes:
    - The condition is evaluated per tuple.
    - Parentheses are required around &/| combinations.""",
    "?!": """\
?! — Negated filter

  Like ? but keeps tuples for which the condition is false.  Useful
  when the positive form would be awkward to write.

  Syntax:
    R ?! cond
    R ?! (cond1 & cond2)

  Examples:
    E ?! role = "intern"          Everyone who is not an intern
    R ?! name in. (Banned # n)    Rows not on the banned list
    R ?! (a < 0 | b < 0)          Equivalent to a >= 0 & b >= 0""",
    "#": """\
# — Project (keep only listed attributes)

  Reduces a relation to a subset of its columns.  Returns a relation
  (the result is still a set, so duplicate tuples collapse).

  Syntax:
    R # col              Single column
    R # [col1 col2 ...]  Multiple columns

  Examples:
    E # name
    E # [name salary]
    E # dept_id          Distinct department ids

  See also #! (remove), the complementary operation.""",
    "#!": """\
#! — Remove (drop listed attributes)

  Complement of # (project): keeps everything *except* the listed
  attributes.  Useful when you only want to strip a small number of
  columns from a wide relation.

  Syntax:
    R #! col
    R #! [col1 col2 ...]

  Examples:
    E #! emp_id                   Drop the id, keep the rest
    E #! [emp_id created_at]      Drop multiple columns""",
    "*.": """\
*. — Natural join

  Combines two relations on their shared attributes.  Tuples with
  matching values on all shared attributes are merged.  Tuples that
  don't match are dropped from the result.

  Syntax:
    R *. S

  Examples:
    E *. D                          Join Employee with Department
    Orders *. Customers *. Items    Chain multiple joins

  Notes:
    - If R and S share no attributes, *. produces a Cartesian product.
    - For "keep all left tuples" behaviour, use *< (left join).
    - For "fan-out avoidance" use *: (nest join).""",
    "+:": """\
+: — Extend (add computed columns)

  Adds new attributes whose values are computed from each tuple's
  existing attributes.  Error if a new name collides with an existing
  attribute.

  Syntax:
    R +: name: expr
    R +: [name1: expr1  name2: expr2 ...]

  Examples:
    E +: bonus: salary * 0.1
    E +: [bonus: salary * 0.1  net: salary - tax]
    E +: full_name: "{first} {last}" .f
    E +: tier: ?: salary > 100000 "senior" "junior"
    E +: typed_id: id .as int       Cast inline (also updates schema)

  Notes:
    - Expressions can reference other source attributes, aggregates over
      the source, and subqueries.
    - .as in an extend propagates the declared type to the result schema.
    - To replace an existing attribute, use =: (modify) instead.""",
    "=:": """\
=: — Modify (replace existing column values)

  Updates one or more existing attributes per tuple.  Error if the
  named attribute doesn't exist (use +: to add new columns).

  Syntax:
    R =: name: expr
    R =: [name1: expr1  name2: expr2 ...]

  Examples:
    R =: salary: salary * 1.1
    R =: [salary: salary * 1.1  bonus: bonus + 1000]
    R =: name: name .s "upper"
    R =: amount: amount .as decimal   Reschema in place

  Notes:
    - Modify can change types; .as updates the column's schema type.
    - The whole relation is re-emitted with the new values; result-set
      semantics mean dedup can happen if rows become identical.""",
    "@": """\
@ — Rename (give attributes new names)

  Renames one or more attributes.  Source and target names are given
  as pairs.  Errors if any target name collides with an existing
  attribute that isn't being renamed away, or if two sources map to
  the same target.

  Syntax:
    R @ [old new]
    R @ [old1 new1  old2 new2 ...]

  Examples:
    ContractorPay @ [pay salary]              Single rename
    E @ [first_name fname  last_name lname]   Multiple renames
    R @ [a b  b a]                            Mutual swap (works)

  Notes:
    - Renaming preserves the schema entry's type.
    - Use parentheses to read the pair list as one logical operand.""",
    "|.": """\
|. — Union (set union)

  Combines two relations with the same heading into a relation of all
  distinct tuples that appear in either side.  Both sides must have
  identical attribute sets ("same heading").

  Syntax:
    R |. S
    R |. (some_subquery)

  Examples:
    Engineers |. Managers              All people in either role
    Active |. (Inactive ? days > 30)

  Notes:
    - The LHS schema prevails; RHS values are coerced to match before
      the set union.
    - Duplicates are removed (relations are sets).""",
    "-.": """\
-. — Difference (set subtraction)

  Returns tuples in R that are not in S.  Both sides must share the
  same heading.

  Syntax:
    R -. S
    R -. (subquery)

  Examples:
    AllUsers -. BannedUsers
    R -. (R ? expired = true)        Equivalent to R ?! expired = true

  Notes:
    - LHS schema prevails for coercion (same as |.).
    - For "rows in S not in R", flip the operands.""",
    "&.": """\
&. — Intersect (set intersection)

  Returns tuples appearing in both R and S.  Same-heading requirement
  as union and difference.

  Syntax:
    R &. S
    R &. (subquery)

  Examples:
    Engineers &. Senior              Senior engineers
    A &. (B |. C)                    A ∩ (B ∪ C)""",
    "/.": """\
/. — Summarize (group + aggregate)

  Groups tuples by one or more keys and computes aggregates per group.
  The result has one row per group with the group key(s) plus the
  named aggregate columns.

  Syntax:
    R /. key [name: agg_expr ...]       Partitioned by key
    R /. [key1 key2] [name: agg_expr]   Composite key
    R /. [name: agg_expr ...]           No grouping (one row out)
    R /. key agg_expr                   Auto-named single aggregate

  Examples:
    E /. dept_id [n: #.  avg: %. salary]
    E /. [dept_id role] [total: +. salary]
    E /. [n: #.]                        Just total count
    E /. dept_id #.                     Auto-names "count"

  See also /* (broadcast aggregate), which keeps every original tuple.""",
    "::": """\
:: — Apply or extract schema

  Two forms based on whether a RHS is present:
    - With RHS: coerce R's columns according to a schema relation.
    - Without RHS: extract R's current schema as a relation.

  Syntax:
    R :: SchemaRel             Apply schema
    R :: {attr type; "x" "int"; "y" "decimal(2)"}     Inline schema
    R ::                       Extract schema as {attr, type}

  Examples:
    Orders :: OrderSchema
    R :: {attr type; "id" "int"; "price" "Money"}
    R ::                                    See what the schema is

  Notes:
    - User-defined type aliases (Money, etc.) are resolved through the
      environment.
    - in(R, a) constraints reference a relation that must exist when
      coercion runs.""",

    # --- Aggregates ---
    "#.": """\
#. — Count

  Counts the tuples in a group.  Used inside /. or /* aggregate lists,
  or with explicit source as a scalar.

  Syntax:
    #.                  Inside /. — count per group
    #. R                Outside aggregate context — count of R

  Examples:
    E /. dept_id #.                Auto-names to "count"
    E /. dept_id [n: #.]
    E +: dept_size: #. (E ? dept_id = dept_id)

  Always returns int.""",
    "+.": """\
+. — Sum

  Sum of a numeric column over a group.

  Syntax:
    +. attr             Per-group sum (inside /. or /*)
    +. R attr           Sum of attr in relation R

  Examples:
    E /. dept_id [total: +. salary]
    Sales /. [grand_total: +. amount]

  Notes:
    - Output type follows the source column: int → int, decimal → decimal.
    - Empty group sums to 0.""",
    ">.": """\
>. — Maximum

  Largest value of a column over a group.

  Syntax:
    >. attr
    >. R attr

  Examples:
    E /. dept_id [top: >. salary]
    (Sales /. >. amount)              Scalar: max amount

  Notes:
    - Output type matches the source column.
    - Sort comparison respects the column's schema type.""",
    "<.": """\
<. — Minimum

  Smallest value of a column over a group.  Mirrors >. exactly.

  Syntax:
    <. attr
    <. R attr

  Examples:
    E /. dept_id [low: <. salary]
    (R /. <. created_at)""",
    "%.": """\
%. — Mean (average)

  Arithmetic mean of a numeric column.

  Syntax:
    %. attr
    %. R attr

  Examples:
    E /. dept_id [avg: %. salary]
    (E /. %. salary)                Overall average

  Always returns float regardless of source type.""",
    "p.": """\
p. — Percent (fraction of total)

  Value as a percentage of the column's whole-relation total.  Useful
  inside /* (broadcast) — each tuple shows its own value's share.

  Syntax:
    p. attr                Uses enclosing source as the "whole"
    p. R attr              Uses explicit relation R as the "whole"

  Examples:
    E /* [pct: p. salary]      Each row gets its share of total payroll
    E /. dept_id [pct: p. salary]
    E +: pct: p. salary

  Always returns float.""",

    # --- Sources ---
    "i.": """\
i. — Iota (1-based integer generator)

  Produces a single-column relation of consecutive integers 1..N.
  Useful for building grids and seed data.

  Syntax:
    i. N                    Default column name "i", values 1..N
    i. name: N              Custom column name
    i. name: (expr)         N derived from a scalar subquery

  Examples:
    i. 5                    {i; 1; 2; 3; 4; 5}
    i. day: 7
    i. week: (R /. >. week) Generates 1..max-week-in-R

  Notes:
    - N must evaluate to a positive integer at runtime.
    - See I. for 0-based.""",
    "I.": """\
I. — Iota (0-based integer generator)

  Like i. but produces 0..N-1.

  Syntax:
    I. N
    I. name: N

  Examples:
    I. 5                    {i; 0; 1; 2; 3; 4}
    I. idx: 10              Custom name, values 0..9""",
    "{}": """\
{} — Relation literal

  Inline relation with explicit heading and rows.  Headings are bare
  identifiers; row values use string/number/bool literals.

  Syntax:
    {attr1 attr2; v1a v1b; v2a v2b; ...}

  Examples:
    {name age; "Alice" 30; "Bob" 25}
    {dept}                              Just heading (empty relation)
    {n; 1; 2; 3}                        Single-column

  Notes:
    - Useful as inline schema relations for :: too.
    - The result is a Relation just like any loaded data.""",

    # --- Nested ---
    "*:": """\
*: — Nest join

  Like *. (natural join) but the matching right-side tuples are
  collected into a nested relation-valued attribute instead of fanning
  out into multiple result rows.

  Syntax:
    R *: name: S

  Examples:
    E *: phones: Phone           One row per employee, phones is a relation
    Cust *: orders: Orders

  Notes:
    - Tuples in R with no match in S still appear; their nested attribute
      is an empty relation.
    - <: reverses this — unpacks a nested attribute back into rows.""",
    "<:": """\
<: — Unnest (flatten a nested attribute)

  Takes a relation with a relation-valued attribute and emits one row
  for each tuple in each nested relation.  Inverse of *:.

  Syntax:
    R <: nest_attr

  Examples:
    E *: phones: Phone <: phones         Equivalent to E *. Phone
    R <: tags

  Notes:
    - The named attribute must contain relation values.
    - If a nested relation is empty, its parent tuple is dropped.""",
    "/:": """\
/: — Nest by (group into nested relations)

  Groups tuples by one or more keys; the matching rows for each group
  are collected as a nested relation-valued attribute.

  Syntax:
    R /: name: key
    R /: name: [key1 key2 ...]

  Examples:
    E /: team: dept_id              One row per dept_id, team is a relation
    E /: cohort: [dept role]

  Notes:
    - Conceptually: /. (summarize) collapses; /: nests instead.
    - The nested attribute contains the non-key columns.""",
    "n.": """\
n. — Collect (aggregate to a nested relation)

  Aggregate variant that gathers all values of a column into a nested
  single-column relation.  Used in /. or /*.

  Syntax:
    n. attr

  Examples:
    E /. dept_id [members: n. name]
    R /. cat [items: n. name]

  Notes:
    - The nested relation keeps the original attribute name.
    - Pair with <: later to re-flatten.""",

    # --- Expressions ---
    "+": """\
+ - * / // % — Arithmetic operators

  Standard arithmetic on numeric values.  Evaluated left-to-right with
  no operator precedence — use parentheses to override.

  Operators:
    +     Addition
    -     Subtraction
    *     Multiplication
    /     Division (float result)
    //    Integer division
    %     Modulo

  Examples:
    salary * 0.1
    salary // 1000
    i % 2
    (a + b) * c             Parens override left-to-right

  Notes:
    - Mixed numeric types promote: int + decimal → decimal, etc.
    - Date arithmetic: date + N = N days later; date - date = day count.""",
    "in.": """\
in. — Membership test

  Boolean operator: is the LHS value contained in the single-column
  relation on the RHS?  Used in filter conditions, ternary expressions,
  and anywhere a comparison is allowed.

  Syntax:
    expr in. rel_expr
    expr in. (subquery)

  Examples:
    R ? status in. (Statuses # name)
    R ? name .s "lower" in. (KnownNames # n)
    R +: flag: ?: dept_id in. (CoreDepts # id) "core" "other"

  Notes:
    - The RHS must produce a single-attribute relation.
    - Coercion-aware: matches "42" against 42 across types.
    - For set literals use = with {} : R ? x = {1, 2, 3}.""",
    "~": """\
~ — Precision (round to N decimal places)

  Postfix operator that rounds a numeric value.  N is a positive integer
  literal.

  Syntax:
    expr ~ N

  Examples:
    %. salary ~ 2            Mean salary, 2 decimal places
    price ~ 0                Round to integer
    rate ~ 4

  Notes:
    - Returns Decimal.
    - Distinct from =~ /!=~ which are regex match comparisons.""",
    ".r": """\
.r — Regex replace (substitution)

  Postfix operator applying Python's re.sub on a string value.

  Syntax:
    expr .r "pattern" "replacement"

  Examples:
    val .r "[$ ,]" ""             Strip $, spaces, commas
    val .r "^\\((.+)\\)$" "-\\1"   "(123.45)" → "-123.45"
    name .r "Mr\\. " ""

  Notes:
    - Pattern is a regex; escape special chars as needed.
    - Backreferences use \\1, \\2, etc. — use \\g<N> to disambiguate
      from following digits.""",
    ".as": """\
.as — Type cast

  Postfix operator coercing a value to a target type.  Type name is a
  bare identifier (built-in or a defined UDT alias).

  Syntax:
    expr .as type

  Examples:
    amount .as int
    val .as float
    code .as Money            UDT alias
    "3.14" .as decimal

  Notes:
    - Type names: str, int, float, decimal, date, bool, or any UDT.
    - In +: / =:, the cast type propagates to the result schema.
    - Cycle in alias chain raises an error at coercion time.""",
    "?:": """\
?: — Ternary (conditional value)

  Picks one of two expressions based on a condition.  The condition
  follows the same rules as ? filters (parens for & / |).

  Syntax:
    ?: cond true_expr false_expr
    ?: (c1 & c2) a b

  Examples:
    ?: salary > 100000 "senior" "junior"
    R +: tier: ?: dept = "eng" "tech" "ops"
    ?: (a > 0 & b > 0) (a + b) 0
    ?: ?: outer inner1 inner2 final_else   Nested ternaries

  Notes:
    - Each branch is one atom — use parens for arithmetic or chained
      operations.""",

    # --- Display ---
    "$": """\
$ — Sort

  Imposes an ordering on the relation, producing a list (no longer a
  relational value).  Sort respects the source schema: numeric keys
  sort numerically even if displayed as strings.

  Syntax:
    R $ key                Ascending
    R $ key-               Descending
    R $ [key1 key2-]       Composite, key2 descending

  Examples:
    E $ salary-
    E $ [dept_id salary-]   Group by dept, salary high-to-low
    R $ created_at $. [name created_at]    Sort then reorder columns

  Notes:
    - The result is an array, not a relation; further relational
      operations (e.g. # project) won't apply.
    - Chain with $. (order columns) for display order; chain with ^
      (take) to limit to N tuples.""",
    "$.": """\
$. — Order columns (for display)

  Reorders the displayed columns of a relation.  Listed columns appear
  first in the given order; unlisted columns are dropped (so $. also
  acts as a project that preserves order).

  Syntax:
    R $. col                Single column
    R $. [col1 col2 ...]    Multiple columns in display order

  Examples:
    E $. [name salary dept_id]
    R ?. $. [attr type inferred distinct pct empty min max sample]

  Notes:
    - Output is an ordered array; further relational ops won't apply.
    - Unlike #, $. controls *visual* order, not just which columns.""",
    "^": """\
^ — Take (limit to first N)

  Limits a sorted array to its first N tuples.  Usually follows $.

  Syntax:
    expr ^ N

  Examples:
    E $ salary- ^ 3                Top three by salary
    E $ created_at ^ 10            Ten oldest
    i. 100 ^ 5                     First 5 of an iota

  Notes:
    - Operates on arrays (post-$).
    - If N exceeds the array length, returns the whole array.""",
    "r.": """\
r. — Rotate (vertical display)

  Transposes a relation for display: each attribute becomes a row and
  each tuple becomes a column.  Useful for inspecting one or a few
  tuples with many attributes.

  Syntax:
    R r.
    R ? name = "Alice" r.

  Examples:
    E ? name = "Alice" r.       Show all Alice's attributes vertically
    R ^ 1 r.                    First tuple rotated

  Notes:
    - Affects display only; the underlying values are unchanged.
    - Best on a small number of rows (often 1).""",

    # --- Other ---
    ":=": """\
:= — Assignment (bind a name to a relation)

  Assigns the result of a relational expression to a name in the
  environment.  The name can then be used as a relation reference.

  Syntax:
    name := rel_expr

  Examples:
    senior := E ? salary > 100000
    eng_count := senior /. dept_id #.
    Mix := A *. B *. C

  Notes:
    - Assignments are silent in scripts (no output line).
    - Sort results (lists, from $) cannot be assigned — they're not
      relations.  Use without sort, or sort at the end.""",
    "type": """\
:= type — User-defined type alias

  Binds a name in the type namespace to an existing type string.
  Distinct from the relation namespace, so a type and a relation can
  share a name (common when the relation provides valid values for
  an in() constraint).

  Syntax:
    Name := type target

  Where target is one of:
    int, str, float, decimal, date, bool
    decimal(N)
    in(RelName, attr)
    AnotherUDT

  Examples:
    Money  := type decimal(2)
    Status := type in(Statuses, name)
    Age    := type int
    Price  := type Money              Alias of an alias

  Notes:
    - Resolution happens at coercion time (when :: applies a schema
      or .as casts a value); UDT references in schemas don't have to
      be defined before declaration, only before use.
    - Cycles (A → B → A) raise at resolution time.""",
}
_DETAIL["!=~"] = _DETAIL["=~"]
for _op in ("!=", "<", ">", "<=", ">="):
    _DETAIL[_op] = _DETAIL["="]
for _op in ("or", "not"):
    _DETAIL[_op] = _DETAIL["and"]
# Arithmetic ops share a single entry.
for _op in ("-", "*", "/", "//", "%"):
    _DETAIL[_op] = _DETAIL["+"]
# := type alias is reachable via either spelling.
_DETAIL[":= type"] = _DETAIL["type"]


def ops_output() -> str:
    """Return formatted primitives reference as a string."""
    sections = [
        ("Sources", _SOURCES),
        ("Relational", _RELATIONAL),
        ("Aggregates", _AGGREGATES),
        ("Nested", _NESTED),
        ("Expressions", _EXPRESSIONS),
        ("Display", _DISPLAY),
        ("Other", _OTHER),
    ]
    parts: list[str] = []
    for title, rows in sections:
        parts.append(title)
        parts.append(_build_table(_HEADERS, [list(r) for r in rows]))
    return "\n".join(parts)


def ops_detail(op: str) -> str | None:
    """Return detailed help for a specific operator, or None if not found."""
    return _DETAIL.get(op)
