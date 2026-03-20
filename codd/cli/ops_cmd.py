"""Ops reference – display language primitives."""

from codd.repl.formatter import _build_table

_RELATIONAL = [
    ("?", "Filter", "E ? salary > 50000"),
    ("?!", "Negated filter", 'E ?! role = "engineer"'),
    ("#", "Project", "E # [name salary]"),
    ("#!", "Remove", "E #! emp_id"),
    ("*.", "Natural join", "E *. D"),
    ("*:", "Nest join", "E *: Phone -> phones"),
    ("<:", "Unnest", "E <: phones"),
    ("+:", "Extend", "E +: bonus: salary * 0.1"),
    ("=:", "Modify", "E =: salary: salary * 1.1"),
    ("@", "Rename", "E @ [pay salary]"),
    ("|.", "Union", "E |. (D)"),
    ("-.", "Difference", "E -. (D)"),
    ("&.", "Intersect", "E &. (D)"),
    ("/.", "Summarize", "E /. dept_id [n: #. avg: %. salary]  or  E /. [n: #.]"),
    ("/:", "Nest by", "E /: dept_id -> team  or  E /: [dept_id role] -> team"),
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
    ("n.", "Collect", "n. activity"),
    ("p.", "Percent", "p. salary ~ 1"),
]

_EXPRESSIONS = [
    ("+ - * / // %", "Arithmetic", "salary * 0.1  or  salary // 1000  or  i % 2"),
    ("~", "Precision", "%. salary ~ 2"),
    (".s", "Substring", "name .s [1 3]  or  name .s [-2]"),
    (".d", "Date", "col .d  or  col .d 'year'  or  col .d '{dd}/{mm}/{yyyy}'"),
    (".f", "Format", '"{name} earns {salary}" .f'),
    ("?:", "Ternary", '?: dept_id = 10 "eng" "other"'),
]

_SOURCES = [
    ("i.", "Iota (generate)", "i. 5  or  i. month: 12"),
    ("{}", "Relation literal", '{name age; "Alice" 30; "Bob" 25}'),
]

_OTHER = [
    (":=", "Assignment", "high := E ? salary > 70000"),
]

_HEADERS = ["Primitive", "Name", "Example"]


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
