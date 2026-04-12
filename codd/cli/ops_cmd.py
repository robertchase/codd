"""Ops reference – display language primitives."""

from codd.repl.formatter import _build_table

_RELATIONAL = [
    ("?", "Filter", "E ? salary > 50000"),
    ("?!", "Negated filter", 'E ?! role = "engineer"'),
    ("#", "Project", "E # [name salary]"),
    ("#!", "Remove", "E #! emp_id"),
    ("*.", "Natural join", "E *. D"),
    ("*<", "Left join", "E *< D [col: 0]"),
    ("*:", "Nest join", "E *: Phone -> phones"),
    ("<:", "Unnest", "E <: phones"),
    ("+:", "Extend", "E +: bonus: salary * 0.1"),
    ("=:", "Modify", "E =: salary: salary * 1.1"),
    ("@", "Rename", "E @ [pay salary]"),
    ("|.", "Union", "E |. (D)"),
    ("-.", "Difference", "E -. (D)"),
    ("&.", "Intersect", "E &. (D)"),
    ("/.", "Summarize", "E /. dept_id [n: #. avg: %. salary]  or  E /. [n: #.]"),
    ("/*", "Broadcast agg", "E /* dept_id [avg: %. salary]  or  E /* [total: +. salary]"),
    ("/:", "Nest by", "E /: dept_id -> team  or  E /: [dept_id role] -> team"),
    ("$", "Sort", "E $ salary-"),
    ("$.", "Order columns", "E $. [salary name]"),
    ("^", "Take", "E $ salary- ^ 3"),
    ("r.", "Rotate", "E ? name = \"Alice\" r."),
    ("::", "Apply schema", "R :: S  or  R ::"),
    ("in.", "Membership test", "R ? status in. (Statuses # name)"),
]

_AGGREGATES = [
    ("#.", "Count", "#."),
    ("+.", "Sum", "+. salary"),
    (">.", "Max", ">. salary"),
    ("<.", "Min", "<. salary"),
    ("%.", "Mean", "%. salary"),
    ("n.", "Collect", "n. activity"),
    ("p.", "Percent", "p. salary ~ 1"),
]

_EXPRESSIONS = [
    ("+ - * / // %", "Arithmetic", "salary * 0.1  or  salary // 1000  or  i % 2"),
    ("= != < > <= >=", "Comparison", "salary > 50000  or  status != \"inactive\""),
    ("=~ !=~", "Regex match", 'name =~ "^A"  or  name !=~ "test"'),
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
    expr .s "trim"          Strip whitespace (both sides)
    expr .s "rtrim"         Strip whitespace (right)
    expr .s "ltrim"         Strip whitespace (left)
    expr .s "len"           Length (returns int)

    name .s "upper"         "Alice" → "ALICE"
    name .s "lower"         "Alice" → "alice"
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
}
_DETAIL["!=~"] = _DETAIL["=~"]
for _op in ("!=", "<", ">", "<=", ">="):
    _DETAIL[_op] = _DETAIL["="]
for _op in ("or", "not"):
    _DETAIL[_op] = _DETAIL["and"]


def ops_output() -> str:
    """Return formatted primitives reference as a string."""
    sections = [
        ("Sources", _SOURCES),
        ("Relational", _RELATIONAL),
        ("Aggregates", _AGGREGATES),
        ("Expressions", _EXPRESSIONS),
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
