"""Tests for the executor."""

import pytest

from codd.executor.environment import Environment
from codd.executor.executor import Executor, ExecutionError
from codd.lexer.lexer import Lexer
from codd.model.relation import Relation
from codd.model.types import OrderedArray, Tuple_
from codd.parser.parser import Parser


def _make_env() -> Environment:
    """Create an environment with sample data."""
    env = Environment()
    env.bind(
        "E",
        Relation(
            frozenset(
                {
                    Tuple_(emp_id=1, name="Alice", salary=80000, dept_id=10, role="engineer"),
                    Tuple_(emp_id=2, name="Bob", salary=60000, dept_id=10, role="manager"),
                    Tuple_(emp_id=3, name="Carol", salary=55000, dept_id=20, role="engineer"),
                    Tuple_(emp_id=4, name="Dave", salary=90000, dept_id=10, role="engineer"),
                    Tuple_(emp_id=5, name="Eve", salary=45000, dept_id=20, role="engineer"),
                }
            )
        ),
    )
    env.bind(
        "D",
        Relation(
            frozenset(
                {
                    Tuple_(dept_id=10, dept_name="Engineering"),
                    Tuple_(dept_id=20, dept_name="Sales"),
                }
            )
        ),
    )
    env.bind(
        "Phone",
        Relation(
            frozenset(
                {
                    Tuple_(emp_id=1, phone="555-1234"),
                    Tuple_(emp_id=3, phone="555-5678"),
                    Tuple_(emp_id=3, phone="555-9999"),
                }
            )
        ),
    )
    env.bind(
        "ContractorPay",
        Relation(frozenset({Tuple_(name="Frank", pay=70000)})),
    )
    return env


def run(source: str, env: Environment | None = None) -> Relation | list[Tuple_]:
    """Helper: lex, parse, execute."""
    if env is None:
        env = _make_env()
    tokens = Lexer(source).tokenize()
    tree = Parser(tokens).parse()
    return Executor(env).execute(tree)


class TestProject:
    """Test # (project)."""

    def test_single_attr(self) -> None:
        """Project a single attribute from a relation."""
        result = run("E # name")
        assert isinstance(result, Relation)
        assert len(result) == 5
        names = {t["name"] for t in result}
        assert names == {"Alice", "Bob", "Carol", "Dave", "Eve"}

    def test_multiple_attrs(self) -> None:
        """Project multiple attributes using bracket syntax."""
        result = run("E # [name salary]")
        assert isinstance(result, Relation)
        assert result.attributes == frozenset({"name", "salary"})


class TestBacktickIdent:
    """Test backtick-quoted identifiers for column names with spaces."""

    def test_project(self) -> None:
        """Backtick idents work in project."""
        env = Environment()
        env.bind("T", Relation(frozenset({
            Tuple_({"Account Name": "Alice", "Amount": 100}),
            Tuple_({"Account Name": "Bob", "Amount": 200}),
        })))
        result = run("T # `Account Name`", env)
        assert isinstance(result, Relation)
        assert result.attributes == frozenset({"Account Name"})
        assert len(result) == 2

    def test_filter(self) -> None:
        """Backtick idents work in filter conditions."""
        env = Environment()
        env.bind("T", Relation(frozenset({
            Tuple_({"Account Name": "Alice", "Amount": 100}),
            Tuple_({"Account Name": "Bob", "Amount": 200}),
        })))
        result = run('T ? `Account Name` = "Alice"', env)
        assert isinstance(result, Relation)
        assert len(result) == 1

    def test_extend(self) -> None:
        """Backtick idents work in extend computations."""
        env = Environment()
        env.bind("T", Relation(frozenset({
            Tuple_({"Unit Price": 10, "Qty": 5}),
        })))
        result = run("T +: Total: `Unit Price` * Qty", env)
        assert isinstance(result, Relation)
        t = next(iter(result))
        assert t["Total"] == 50

    def test_rename(self) -> None:
        """Backtick idents work in rename."""
        env = Environment()
        env.bind("T", Relation(frozenset({
            Tuple_({"Account Name": "Alice"}),
        })))
        result = run("T @ `Account Name` name", env)
        assert isinstance(result, Relation)
        assert result.attributes == frozenset({"name"})


class TestRemove:
    """Test #! (remove)."""

    def test_single_attr(self) -> None:
        """Remove a single attribute keeps all others."""
        result = run("E #! salary")
        assert isinstance(result, Relation)
        assert "salary" not in result.attributes
        expected = {"emp_id", "name", "dept_id", "role"}
        assert result.attributes == frozenset(expected)
        assert len(result) == 5

    def test_chained_with_filter(self) -> None:
        """Remove multiple attrs then filter on a remaining attr."""
        result = run('E #! [emp_id dept_id] ? name = "Alice"')
        assert isinstance(result, Relation)
        assert "emp_id" not in result.attributes
        assert "dept_id" not in result.attributes
        assert len(result) == 1
        t = next(iter(result))
        assert t["name"] == "Alice"


class TestFilter:
    """Test ? (filter)."""

    def test_gt(self) -> None:
        """Filter rows where salary exceeds a threshold."""
        result = run("E ? salary > 50000")
        assert isinstance(result, Relation)
        assert len(result) == 4

    def test_eq_string(self) -> None:
        """Filter rows by string equality on name."""
        result = run('E ? name = "Alice"')
        assert len(result) == 1

    def test_negated(self) -> None:
        """Negated filter excludes matching rows."""
        result = run('E ?! role = "engineer"')
        assert len(result) == 1
        assert next(iter(result))["name"] == "Bob"

    def test_or_condition(self) -> None:
        """Filter with OR condition matches either branch."""
        result = run("E ? (dept_id = 20 | salary > 80000)")
        assert len(result) == 3
        names = {t["name"] for t in result}
        assert names == {"Carol", "Dave", "Eve"}

    def test_set_membership(self) -> None:
        """Filter by set membership using curly-brace syntax."""
        result = run("E ? dept_id = {10, 20}")
        assert len(result) == 5

    def test_chained_filters(self) -> None:
        """Chained filters apply sequentially as logical AND."""
        result = run("E ? dept_id = 10 ? salary > 70000")
        assert len(result) == 2
        names = {t["name"] for t in result}
        assert names == {"Alice", "Dave"}


class TestRegexFilter:
    """Test =~ and !=~ (regex match) in filters."""

    def test_match(self) -> None:
        """=~ matches rows where attribute matches regex."""
        result = run('E ? name =~ "^A"')
        assert isinstance(result, Relation)
        assert len(result) == 1
        assert next(iter(result))["name"] == "Alice"

    def test_non_match(self) -> None:
        """!=~ excludes rows where attribute matches regex."""
        result = run('E ? name !=~ "^A"')
        assert isinstance(result, Relation)
        assert len(result) == 4
        names = {t["name"] for t in result}
        assert "Alice" not in names

    def test_substring_match(self) -> None:
        """=~ uses re.search (substring match, not full-string)."""
        result = run('E ? name =~ "li"')
        assert isinstance(result, Relation)
        assert len(result) == 1
        assert next(iter(result))["name"] == "Alice"

    def test_case_insensitive(self) -> None:
        """(?i) flag enables case-insensitive matching."""
        result = run('E ? name =~ "(?i)alice"')
        assert isinstance(result, Relation)
        assert len(result) == 1

    def test_invalid_regex(self) -> None:
        """Invalid regex pattern raises an error."""
        import pytest
        from codd.executor.executor import ExecutionError

        with pytest.raises(ExecutionError, match="Invalid regex"):
            run('E ? name =~ "["')

    def test_anchored_full_match(self) -> None:
        """^ and $ anchors enforce full-string matching."""
        result = run('E ? name =~ "^Alice$"')
        assert len(result) == 1
        result = run('E ? name =~ "^Ali$"')
        assert len(result) == 0


class TestChaining:
    """Test chained operations."""

    def test_filter_project(self) -> None:
        """Filter then project retains only selected attributes."""
        result = run("E ? salary > 50000 # [name salary]")
        assert isinstance(result, Relation)
        assert len(result) == 4
        assert result.attributes == frozenset({"name", "salary"})


class TestJoin:
    """Test *. and *: (join)."""

    def test_natural_join(self) -> None:
        """Natural join matches on shared attribute dept_id."""
        result = run("E *. D")
        assert isinstance(result, Relation)
        assert len(result) == 5
        assert "dept_name" in result.attributes

    def test_join_filter_project(self) -> None:
        """Join, filter, and project compose correctly."""
        result = run('E *. D ? dept_name = "Engineering" # [name salary]')
        assert len(result) == 3
        names = {t["name"] for t in result}
        assert names == {"Alice", "Bob", "Dave"}

    def test_nest_join(self) -> None:
        """Nest join groups child tuples into a nested relation."""
        result = run("E *: Phone -> phones")
        assert isinstance(result, Relation)
        assert len(result) == 5
        for t in result:
            if t["emp_id"] == 1:
                assert len(t["phones"]) == 1
            elif t["emp_id"] == 3:
                assert len(t["phones"]) == 2
            else:
                assert len(t["phones"]) == 0


class TestLeftJoin:
    """Test *< (left join)."""

    def test_all_match(self) -> None:
        """Left join where every left tuple has a match behaves like natural join."""
        result = run("E *< D")
        assert isinstance(result, Relation)
        assert len(result) == 5
        assert "dept_name" in result.attributes

    def test_unmatched_filled_with_default(self) -> None:
        """Left tuple with no right match gets right-only attrs filled from defaults."""
        env = _make_env()
        # Phone has 1 row for emp_id=1, 2 rows for emp_id=3, none for 2/4/5.
        # Left join produces: 1+2+1+1+1 = 6 rows (Carol appears twice).
        result = run("E *< Phone [phone: \"none\"]", env)
        assert isinstance(result, Relation)
        assert len(result) == 6
        filled = [t["phone"] for t in result if t["phone"] == "none"]
        assert len(filled) == 3  # Bob, Dave, Eve get the default

    def test_unmatched_no_default_raises(self) -> None:
        """Left join with unmatched tuple and no default raises ExecutionError."""
        with pytest.raises(ExecutionError, match="no default"):
            run("E *< Phone")

    def test_missing_weeks_pattern(self) -> None:
        """Average-per-week with missing weeks filled as zero."""
        env = Environment()
        env.bind(
            "Sales",
            Relation(
                frozenset({
                    Tuple_(cat="A", week=1, amount=10),
                    Tuple_(cat="A", week=2, amount=20),
                    Tuple_(cat="B", week=2, amount=30),
                })
            ),
        )
        # Grid: all cat × week combinations
        env.bind(
            "Grid",
            Relation(
                frozenset({
                    Tuple_(cat="A", week=1),
                    Tuple_(cat="A", week=2),
                    Tuple_(cat="B", week=1),
                    Tuple_(cat="B", week=2),
                })
            ),
        )
        weekly = run("Sales /. [cat week] [total: +. amount]", env)
        env.bind("Weekly", weekly)
        result = run("Grid *< Weekly [total: 0] /. cat [avg: %. total]", env)
        assert isinstance(result, Relation)
        assert len(result) == 2
        by_cat = {t["cat"]: t["avg"] for t in result}
        assert by_cat["A"] == 15.0   # (10 + 20) / 2
        assert by_cat["B"] == 15.0   # (0 + 30) / 2

    def test_left_join_chains(self) -> None:
        """Left join result can be further chained."""
        result = run('E *< D # [name dept_name]')
        assert isinstance(result, Relation)
        assert result.attributes == frozenset({"name", "dept_name"})
        assert len(result) == 5

    def test_coercion_str_int_join_key(self) -> None:
        """*< matches str and int join key values via coercion (like natural join)."""
        env = Environment()
        # Left has id as str (as CSV loader would produce with default schema).
        env.bind(
            "L",
            Relation(frozenset({
                Tuple_(id="1", name="Alice"),
                Tuple_(id="2", name="Bob"),
                Tuple_(id="3", name="Carol"),
            })),
        )
        # Right has id as int (numeric CSV column).
        env.bind(
            "R",
            Relation(frozenset({
                Tuple_(id=1, score=100),
                Tuple_(id=3, score=300),
            })),
        )
        result = run("L *< R [score: 0]", env)
        assert isinstance(result, Relation)
        assert len(result) == 3
        by_name = {t["name"]: t["score"] for t in result}
        assert by_name["Alice"] == 100
        assert by_name["Bob"] == 0    # unmatched, filled with default
        assert by_name["Carol"] == 300
        # Left side's type for the join key must be preserved (str, not int).
        ids = {t["id"] for t in result}
        assert all(isinstance(v, str) for v in ids), \
            "left join must preserve left side types for shared attrs"


class TestUnnest:
    """Test <: (unnest)."""

    def test_nest_then_unnest(self) -> None:
        """Unnest reverses a nest join, flattening nested tuples."""
        result = run("E *: Phone -> phones <: phones")
        assert isinstance(result, Relation)
        # Alice has 1 phone, Carol has 2 -> 3 tuples
        assert len(result) == 3
        assert "phone" in result.attributes
        assert "phones" not in result.attributes
        names = {t["name"] for t in result}
        assert names == {"Alice", "Carol"}


class TestExtend:
    """Test +: (extend)."""

    def test_single(self) -> None:
        """Extend adds a computed attribute to each tuple."""
        result = run("E +: bonus: salary * 0.1 # [name bonus]")
        assert isinstance(result, Relation)
        for t in result:
            if t["name"] == "Alice":
                assert t["bonus"] == 8000.0

    def test_extend_empty_relation_preserves_heading(self) -> None:
        """Extend on an empty relation still produces the correct heading.

        Previously the new column names were silently dropped when the
        source had no tuples, causing a subsequent project to fail with
        'unknown attributes'.
        """
        env = Environment()
        env.bind("Empty", Relation(frozenset(), attributes=frozenset({"x"})))
        result = run("Empty +: y: x # y", env)
        assert isinstance(result, Relation)
        assert "y" in result.attributes
        assert len(result) == 0


class TestModify:
    """Test =: (modify)."""

    def test_update_value(self) -> None:
        """Modify updates an existing attribute."""
        result = run("E =: salary: salary * 1.1 # [name salary]")
        assert isinstance(result, Relation)
        for t in result:
            if t["name"] == "Alice":
                assert t["salary"] == 88000.0

    def test_multiple(self) -> None:
        """Modify updates multiple existing attributes."""
        result = run('E =: [salary: salary * 2  role: "x"] # [name salary role]')
        assert isinstance(result, Relation)
        for t in result:
            if t["name"] == "Alice":
                assert t["salary"] == 160000
                assert t["role"] == "x"

    def test_unknown_attribute_error(self) -> None:
        """Modify rejects unknown attribute names."""
        import pytest

        with pytest.raises(Exception, match="unknown attributes"):
            run("E =: nonexistent: 1")

    def test_ternary(self) -> None:
        """Modify with ternary expression."""
        result = run('E =: role: ?: salary > 70000 "senior" role')
        assert isinstance(result, Relation)
        for t in result:
            if t["name"] == "Alice":
                assert t["role"] == "senior"


class TestLeftToRightArithmetic:
    """Test left-to-right arithmetic evaluation (no precedence)."""

    def test_divide_then_multiply(self) -> None:
        """salary / 1000 * 2 evaluates left-to-right as (salary / 1000) * 2."""
        result = run("E +: x: salary / 1000.0 * 2.0 # [name x]")
        assert isinstance(result, Relation)
        for t in result:
            if t["name"] == "Alice":
                assert t["x"] == 160.0

    def test_left_to_right(self) -> None:
        """salary + 1000 * 2 evaluates as (salary + 1000) * 2 (no precedence)."""
        result = run("E +: x: salary + 1000 * 2 # [name x]")
        assert isinstance(result, Relation)
        for t in result:
            if t["name"] == "Alice":
                assert t["x"] == 162000

    def test_parens_override(self) -> None:
        """salary + (1000 * 2) uses parens to get standard math order."""
        result = run("E +: x: salary + (1000 * 2) # [name x]")
        assert isinstance(result, Relation)
        for t in result:
            if t["name"] == "Alice":
                assert t["x"] == 82000

    def test_integer_divide(self) -> None:
        """salary // 1000 gives integer quotient."""
        result = run("E +: x: salary // 1000 # [name x]")
        assert isinstance(result, Relation)
        for t in result:
            if t["name"] == "Alice":
                assert t["x"] == 80
            elif t["name"] == "Eve":
                assert t["x"] == 45

    def test_remainder(self) -> None:
        """salary % 1000 gives remainder."""
        result = run("E +: x: salary % 7 # [name x]")
        assert isinstance(result, Relation)
        for t in result:
            if t["name"] == "Alice":
                # 80000 % 7 == 4
                assert t["x"] == 80000 % 7

    def test_integer_divide_chain(self) -> None:
        """i // 3 % 2 chains left-to-right."""
        result = run("i. 6 +: x: i // 3 % 2")
        assert isinstance(result, Relation)
        for t in result:
            assert t["x"] == (t["i"] // 3) % 2


class TestSubstring:
    """Test .s (substring)."""

    def test_positive_range(self) -> None:
        """name .s [1 3] extracts first 3 characters."""
        result = run("E +: sub: name .s [1 3] # [name sub]")
        assert isinstance(result, Relation)
        for t in result:
            if t["name"] == "Alice":
                assert t["sub"] == "Ali"
            elif t["name"] == "Bob":
                assert t["sub"] == "Bob"

    def test_from_position(self) -> None:
        """name .s [3] extracts from position 3 to end."""
        result = run("E +: sub: name .s [3] # [name sub]")
        assert isinstance(result, Relation)
        for t in result:
            if t["name"] == "Alice":
                assert t["sub"] == "ice"
            elif t["name"] == "Bob":
                assert t["sub"] == "b"

    def test_negative_single(self) -> None:
        """name .s [-2] extracts last 2 characters."""
        result = run("E +: sub: name .s [-2] # [name sub]")
        assert isinstance(result, Relation)
        for t in result:
            if t["name"] == "Alice":
                assert t["sub"] == "ce"
            elif t["name"] == "Carol":
                assert t["sub"] == "ol"

    def test_negative_range(self) -> None:
        """name .s [-4 -2] extracts a range from the end."""
        result = run("E +: sub: name .s [-4 -2] # [name sub]")
        assert isinstance(result, Relation)
        for t in result:
            if t["name"] == "Alice":
                assert t["sub"] == "lic"

    def test_clamp_out_of_bounds(self) -> None:
        """Out-of-bounds indices are clamped silently."""
        result = run("E +: sub: name .s [1 100] # [name sub]")
        assert isinstance(result, Relation)
        for t in result:
            if t["name"] == "Bob":
                assert t["sub"] == "Bob"

    def test_single_char(self) -> None:
        """name .s [1 1] extracts a single character."""
        result = run("E +: sub: name .s [1 1] # [name sub]")
        assert isinstance(result, Relation)
        for t in result:
            if t["name"] == "Alice":
                assert t["sub"] == "A"


class TestStringOp:
    """Test .s string transforms."""

    def test_upper(self) -> None:
        """name .s "upper" uppercases."""
        result = run('E +: u: name .s "upper" # [name u]')
        assert isinstance(result, Relation)
        for t in result:
            if t["name"] == "Alice":
                assert t["u"] == "ALICE"

    def test_lower(self) -> None:
        """name .s "lower" lowercases."""
        result = run('E +: l: name .s "lower" # [name l]')
        assert isinstance(result, Relation)
        for t in result:
            if t["name"] == "Alice":
                assert t["l"] == "alice"

    def test_trim(self) -> None:
        """Trim strips both sides."""
        result = run('{x; "  hi  "} +: t: x .s "trim" # t')
        assert isinstance(result, Relation)
        for t in result:
            assert t["t"] == "hi"

    def test_rtrim(self) -> None:
        """Rtrim strips the right side."""
        result = run('{x; "  hi  "} +: t: x .s "rtrim" # t')
        assert isinstance(result, Relation)
        for t in result:
            assert t["t"] == "  hi"

    def test_ltrim(self) -> None:
        """Ltrim strips the left side."""
        result = run('{x; "  hi  "} +: t: x .s "ltrim" # t')
        assert isinstance(result, Relation)
        for t in result:
            assert t["t"] == "hi  "

    def test_len(self) -> None:
        """Len returns an integer length."""
        result = run('E +: n: name .s "len" # [name n]')
        assert isinstance(result, Relation)
        for t in result:
            if t["name"] == "Alice":
                assert t["n"] == 5
            elif t["name"] == "Bob":
                assert t["n"] == 3

    def test_unknown_op_errors(self) -> None:
        """Unknown string op raises an error."""
        import pytest
        from codd.executor.executor import ExecutionError

        with pytest.raises(ExecutionError, match="Unknown string operation"):
            run('E +: x: name .s "bogus"')


class TestIota:
    """Test i. (iota)."""

    def test_basic(self) -> None:
        """i. 5 produces a 5-tuple relation with attribute 'i'."""
        result = run("i. 5")
        assert isinstance(result, Relation)
        assert result.attributes == frozenset({"i"})
        assert len(result) == 5
        values = {t["i"] for t in result}
        assert values == {1, 2, 3, 4, 5}

    def test_named(self) -> None:
        """i. month: 3 produces a relation with attribute 'month'."""
        result = run("i. month: 3")
        assert isinstance(result, Relation)
        assert result.attributes == frozenset({"month"})
        values = {t["month"] for t in result}
        assert values == {1, 2, 3}

    def test_chain_modify(self) -> None:
        """i. 5 =: i: i + 9 shifts values to 10..14."""
        result = run("i. 5 =: i: i + 9")
        assert isinstance(result, Relation)
        values = {t["i"] for t in result}
        assert values == {10, 11, 12, 13, 14}

    def test_chain_extend(self) -> None:
        """i. 3 +: sq: i * i adds a squared column."""
        result = run("i. 3 +: sq: i * i")
        assert isinstance(result, Relation)
        assert result.attributes == frozenset({"i", "sq"})
        for t in result:
            assert t["sq"] == t["i"] * t["i"]

    def test_chain_filter(self) -> None:
        """i. 10 ? i > 7 filters to 3 tuples."""
        result = run("i. 10 ? i > 7")
        assert isinstance(result, Relation)
        assert len(result) == 3
        values = {t["i"] for t in result}
        assert values == {8, 9, 10}

    def test_single(self) -> None:
        """i. 1 produces a single-tuple relation."""
        result = run("i. 1")
        assert isinstance(result, Relation)
        assert len(result) == 1
        t = next(iter(result))
        assert t["i"] == 1

    def test_dynamic_count_from_subquery(self) -> None:
        """i. week: (R /. >. week) derives count from a relation's max value."""
        from codd.executor.environment import Environment
        env = Environment()
        env.bind(
            "R",
            Relation(
                frozenset({
                    Tuple_(week=1),
                    Tuple_(week=3),
                    Tuple_(week=5),
                })
            ),
        )
        result = run("i. week: (R /. >. week)", env)
        assert isinstance(result, Relation)
        assert result.attributes == frozenset({"week"})
        assert len(result) == 5
        assert {t["week"] for t in result} == {1, 2, 3, 4, 5}

    def test_dynamic_count_non_integer_raises(self) -> None:
        """i. count expression that evaluates to non-integer raises ExecutionError."""
        with pytest.raises(ExecutionError, match="integer"):
            run('i. ({x; "hello"} /. >. x)')


class TestIotaZero:
    """Test I. (zero-based iota)."""

    def test_basic(self) -> None:
        """I. 5 produces a 5-tuple relation with values 0..4."""
        result = run("I. 5")
        assert isinstance(result, Relation)
        assert result.attributes == frozenset({"i"})
        assert len(result) == 5
        assert {t["i"] for t in result} == {0, 1, 2, 3, 4}

    def test_named(self) -> None:
        """I. idx: 3 produces a relation with attribute 'idx' and values 0..2."""
        result = run("I. idx: 3")
        assert isinstance(result, Relation)
        assert result.attributes == frozenset({"idx"})
        assert {t["idx"] for t in result} == {0, 1, 2}

    def test_single(self) -> None:
        """I. 1 produces a single tuple with value 0."""
        result = run("I. 1")
        assert isinstance(result, Relation)
        assert len(result) == 1
        assert next(iter(result))["i"] == 0

    def test_zero_count_raises(self) -> None:
        """I. 0 raises ExecutionError."""
        with pytest.raises(ExecutionError, match="positive"):
            run("I. 0")


class TestRotate:
    """Test r. (rotate)."""

    def test_returns_rotated_array(self) -> None:
        """r. returns a RotatedArray."""
        from codd.model.types import RotatedArray

        result = run("E ? name = \"Alice\" r.")
        assert isinstance(result, RotatedArray)
        assert len(result) == 1
        assert result[0]["name"] == "Alice"

    def test_multi_tuple(self) -> None:
        """r. on multiple tuples returns all of them."""
        from codd.model.types import RotatedArray

        result = run("E ? dept_id = 10 r.")
        assert isinstance(result, RotatedArray)
        assert len(result) == 3

    def test_preserves_data(self) -> None:
        """r. preserves all attribute values."""
        from codd.model.types import RotatedArray

        result = run("i. 3 r.")
        assert isinstance(result, RotatedArray)
        values = {t["i"] for t in result}
        assert values == {1, 2, 3}


class TestRelationLiteral:
    """Test {} (relation literal)."""

    def test_basic(self) -> None:
        """Two-column relation with mixed types."""
        result = run('{name age; "Alice" 30; "Bob" 25}')
        assert isinstance(result, Relation)
        assert result.attributes == frozenset({"name", "age"})
        assert len(result) == 2
        for t in result:
            if t["name"] == "Alice":
                assert t["age"] == 30
            elif t["name"] == "Bob":
                assert t["age"] == 25

    def test_single_column(self) -> None:
        """Single-column relation."""
        result = run("{x; 1; 2; 3}")
        assert isinstance(result, Relation)
        assert len(result) == 3
        values = {t["x"] for t in result}
        assert values == {1, 2, 3}

    def test_chain_filter(self) -> None:
        """Filter on a relation literal."""
        result = run("{x; 1; 2; 3; 4; 5} ? x > 3")
        assert isinstance(result, Relation)
        assert len(result) == 2
        values = {t["x"] for t in result}
        assert values == {4, 5}

    def test_chain_extend(self) -> None:
        """Extend a relation literal."""
        result = run("{x; 10; 20} +: y: x * 2")
        assert isinstance(result, Relation)
        for t in result:
            assert t["y"] == t["x"] * 2

    def test_join_inline(self) -> None:
        """Join a relation literal with an existing relation."""
        result = run('{dept_id label; 10 "eng"; 20 "sales"} *. E # [name label]')
        assert isinstance(result, Relation)
        for t in result:
            if t["name"] == "Alice":
                assert t["label"] == "eng"
            elif t["name"] == "Carol":
                assert t["label"] == "sales"

    def test_empty_rows(self) -> None:
        """Header with no data rows produces an empty relation."""
        result = run("{x}")
        assert isinstance(result, Relation)
        assert len(result) == 0
        assert result.attributes == frozenset({"x"})

    def test_negative_values(self) -> None:
        """Negative numbers work."""
        result = run("{x; -5; -10}")
        assert isinstance(result, Relation)
        values = {t["x"] for t in result}
        assert values == {-5, -10}


class TestDateOp:
    """Test .d (date) operator."""

    def test_promotion(self) -> None:
        """String .d promotes to datetime.date."""
        import datetime

        result = run('E +: d: "2026-03-17" .d # [name d]')
        assert isinstance(result, Relation)
        for t in result:
            assert t["d"] == datetime.date(2026, 3, 17)

    def test_extract_year(self) -> None:
        """.d "year" extracts year as int."""
        result = run('E +: y: "2026-03-17" .d "year" # [name y]')
        assert isinstance(result, Relation)
        for t in result:
            assert t["y"] == 2026

    def test_extract_month(self) -> None:
        """.d "month" extracts month as int."""
        result = run('E +: m: "2026-03-17" .d "month" # [name m]')
        assert isinstance(result, Relation)
        for t in result:
            assert t["m"] == 3

    def test_extract_day(self) -> None:
        """.d "day" extracts day as int."""
        result = run('E +: d: "2026-03-17" .d "day" # [name d]')
        assert isinstance(result, Relation)
        for t in result:
            assert t["d"] == 17

    def test_extract_week(self) -> None:
        """.d "week" extracts ISO week number."""
        result = run('E +: w: "2026-01-05" .d "week" # [name w]')
        assert isinstance(result, Relation)
        for t in result:
            assert t["w"] == 2

    def test_extract_ww(self) -> None:
        """.d "ww" returns zero-padded two-digit week string."""
        # 2026-01-05 is ISO week 2
        result = run('E +: w: "2026-01-05" .d "ww" # [name w]')
        assert isinstance(result, Relation)
        for t in result:
            assert t["w"] == "02"

    def test_extract_ww_double_digit(self) -> None:
        """.d "ww" pads single-digit weeks to two characters."""
        # 2026-02-23 is ISO week 9
        result = run('E +: w: "2026-02-23" .d "ww" # [name w]')
        assert isinstance(result, Relation)
        for t in result:
            assert t["w"] == "09"

    def test_format_week_ww(self) -> None:
        """.d "{yyyy}-W{ww}" produces sortable ISO week string."""
        result = run('E +: f: "2026-01-05" .d "{yyyy}-W{ww}" # [name f]')
        assert isinstance(result, Relation)
        for t in result:
            assert t["f"] == "2026-W02"

    def test_extract_dow(self) -> None:
        """.d "dow" extracts day of week (1=Mon)."""
        # 2026-03-17 is a Tuesday
        result = run('E +: d: "2026-03-17" .d "dow" # [name d]')
        assert isinstance(result, Relation)
        for t in result:
            assert t["d"] == 2

    def test_format_iso(self) -> None:
        """.d "{yyyy}-{mm}-{dd}" formats as ISO string."""
        result = run('E +: f: "2026-03-17" .d "{yyyy}-{mm}-{dd}" # [name f]')
        assert isinstance(result, Relation)
        for t in result:
            assert t["f"] == "2026-03-17"

    def test_format_dmy(self) -> None:
        """.d "{dd} {mmm} {yyyy}" formats day-month-year."""
        result = run('E +: f: "2026-03-17" .d "{dd} {mmm} {yyyy}" # [name f]')
        assert isinstance(result, Relation)
        for t in result:
            assert t["f"] == "17 MAR 2026"

    def test_format_compact(self) -> None:
        """.d "{dd}{mmm}{yy}" formats compact."""
        result = run('E +: f: "2026-01-01" .d "{dd}{mmm}{yy}" # [name f]')
        assert isinstance(result, Relation)
        for t in result:
            assert t["f"] == "01JAN26"

    def test_format_no_padding(self) -> None:
        """.d "{d}/{m}/{yy}" uses unpadded values."""
        result = run('E +: f: "2026-03-07" .d "{d}/{m}/{yy}" # [name f]')
        assert isinstance(result, Relation)
        for t in result:
            assert t["f"] == "7/3/26"

    def test_format_day_name(self) -> None:
        """.d "{ddd}" formats day abbreviation."""
        result = run('E +: f: "2026-03-17" .d "{ddd}" # [name f]')
        assert isinstance(result, Relation)
        for t in result:
            assert t["f"] == "TUE"

    def test_add_days(self) -> None:
        """date + int adds days."""
        import datetime

        result = run('E +: d: "2026-03-17" .d + 5 # [name d]')
        assert isinstance(result, Relation)
        for t in result:
            assert t["d"] == datetime.date(2026, 3, 22)

    def test_subtract_days(self) -> None:
        """date - int subtracts days."""
        import datetime

        result = run('E +: d: "2026-03-17" .d - 10 # [name d]')
        assert isinstance(result, Relation)
        for t in result:
            assert t["d"] == datetime.date(2026, 3, 7)

    def test_date_difference(self) -> None:
        """date - date gives int days (parens for left-to-right)."""
        result = run('E +: diff: "2026-03-17" .d - ("2026-03-10" .d) # [name diff]')
        assert isinstance(result, Relation)
        for t in result:
            assert t["diff"] == 7

    def test_iota_date_range(self) -> None:
        """i. with .d builds a date range."""
        import datetime

        result = run('i. 3 =: i: "2025-12-31" .d + i')
        assert isinstance(result, Relation)
        assert len(result) == 3
        values = {t["i"] for t in result}
        assert values == {
            datetime.date(2026, 1, 1),
            datetime.date(2026, 1, 2),
            datetime.date(2026, 1, 3),
        }

    def test_already_date_noop(self) -> None:
        """.d on a date value is a no-op."""
        import datetime

        result = run('E +: d: "2026-03-17" .d .d # [name d]')
        assert isinstance(result, Relation)
        for t in result:
            assert t["d"] == datetime.date(2026, 3, 17)

    def test_bad_date_string(self) -> None:
        """Non-date string .d raises error."""
        with pytest.raises(ExecutionError, match="Cannot parse date"):
            run('E +: d: "not-a-date" .d # [name d]')

    def test_today(self) -> None:
        """"today" .d returns today's date."""
        import datetime

        result = run('i. 1 +: d: "today" .d')
        assert isinstance(result, Relation)
        t = next(iter(result))
        assert t["d"] == datetime.date.today()

    def test_today_extraction(self) -> None:
        """"today" .d "year" extracts year directly."""
        import datetime

        result = run('i. 1 +: y: "today" .d "year"')
        assert isinstance(result, Relation)
        t = next(iter(result))
        assert t["y"] == datetime.date.today().year

    def test_filter_date_vs_string(self) -> None:
        """Filter matches date values against date-like strings."""
        result = run('i. date: 10 =: date: "2025-12-31" .d + date ? date = "2026-01-05"')
        assert isinstance(result, Relation)
        assert len(result) == 1


class TestFormatStr:
    """Test .f (format string)."""

    def test_basic(self) -> None:
        """Simple attribute interpolation."""
        result = run('E +: lbl: "{name} in {dept_id}" .f # [name lbl]')
        assert isinstance(result, Relation)
        for t in result:
            if t["name"] == "Alice":
                assert t["lbl"] == "Alice in 10"

    def test_multiple_attrs(self) -> None:
        """Multiple attributes in one template."""
        result = run('E +: lbl: "{name}/{role}/{salary}" .f # [name lbl]')
        assert isinstance(result, Relation)
        for t in result:
            if t["name"] == "Bob":
                assert t["lbl"] == "Bob/manager/60000"

    def test_literal_text(self) -> None:
        """Text without braces passes through."""
        result = run('E +: lbl: "hello world" .f # [name lbl]')
        assert isinstance(result, Relation)
        for t in result:
            assert t["lbl"] == "hello world"

    def test_unknown_attr_error(self) -> None:
        """Referencing unknown attribute raises error."""
        with pytest.raises(ExecutionError, match="Unknown attribute"):
            run('E +: lbl: "{nonexistent}" .f')

    def test_chain_with_substring(self) -> None:
        """.f result can be chained with .s."""
        result = run('E +: x: "{name}" .f .s [1 3] # [name x]')
        assert isinstance(result, Relation)
        for t in result:
            if t["name"] == "Alice":
                assert t["x"] == "Ali"

    def test_date_value_formatting(self) -> None:
        """Date values in .f display as ISO strings."""
        result = run('E +: d: "2026-03-17" .d +: lbl: "date={d}" .f # [name lbl]')
        assert isinstance(result, Relation)
        for t in result:
            assert t["lbl"] == "date=2026-03-17"

    def test_format_spec_zero_pad(self) -> None:
        """{attr:05d} zero-pads an integer to width 5."""
        result = run('i. n: 3 +: lbl: "{n:03d}" .f')
        assert isinstance(result, Relation)
        values = {t["lbl"] for t in result}
        assert values == {"001", "002", "003"}

    def test_format_spec_float(self) -> None:
        """{attr:.2f} formats a float to 2 decimal places."""
        result = run('E +: lbl: "{salary:.2f}" .f # [name lbl]')
        assert isinstance(result, Relation)
        for t in result:
            assert "." in t["lbl"]
            assert len(t["lbl"].split(".")[1]) == 2

    def test_format_spec_width(self) -> None:
        """{attr:>10} right-aligns a value in a field of width 10."""
        result = run('i. n: 1 +: lbl: "{n:>5}" .f')
        val = next(iter(result))["lbl"]
        assert val == "    1"

    def test_format_spec_invalid_raises(self) -> None:
        """Invalid format spec raises ExecutionError."""
        with pytest.raises(ExecutionError, match="Invalid format spec"):
            run('i. n: 1 +: lbl: "{n:zzz}" .f')


class TestRename:
    """Test @ (rename)."""

    def test_rename(self) -> None:
        """Rename changes an attribute name in the relation."""
        result = run("ContractorPay @ [pay salary]")
        assert isinstance(result, Relation)
        assert "salary" in result.attributes
        assert "pay" not in result.attributes


class TestSetOps:
    """Test |., -., &. (set operations)."""

    def test_union(self) -> None:
        """Union combines tuples from two compatible relations."""
        result = run("ContractorPay @ [pay salary] |. (E # [name salary])")
        assert isinstance(result, Relation)
        assert len(result) == 6

    def test_difference(self) -> None:
        """Difference removes tuples present in the right relation.

        emp_id is stored as Python int but the default schema is str,
        so set operations normalize values to str before comparison.
        """
        result = run("E # emp_id -. (Phone # emp_id)")
        assert isinstance(result, Relation)
        ids = {t["emp_id"] for t in result}
        assert ids == {"2", "4", "5"}

    def test_intersect(self) -> None:
        """Intersect keeps only tuples present in both relations."""
        result = run("(E # emp_id) &. (Phone # emp_id)")
        assert isinstance(result, Relation)
        ids = {t["emp_id"] for t in result}
        assert ids == {"1", "3"}

    def test_difference_schema_coercion(self) -> None:
        """difference normalizes to schema types before set arithmetic.

        Both relations declare id: str but one stores Python ints internally.
        Without normalization, difference would return all rows of A instead
        of the expected 0.
        """
        env = Environment()
        # A stores id as Python int internally, schema says str.
        env.bind(
            "A",
            Relation(
                frozenset({Tuple_(id=1), Tuple_(id=2), Tuple_(id=3)}),
                schema={"id": "str"},
            ),
        )
        # B stores id as Python str, schema says str.
        env.bind(
            "B",
            Relation(
                frozenset({Tuple_(id="1"), Tuple_(id="2"), Tuple_(id="3")}),
                schema={"id": "str"},
            ),
        )
        result = run("A -. B", env)
        assert len(result) == 0

    def test_intersect_schema_coercion(self) -> None:
        """intersect normalizes to schema types before set arithmetic."""
        env = Environment()
        env.bind(
            "A",
            Relation(
                frozenset({Tuple_(id=1), Tuple_(id=2)}),
                schema={"id": "str"},
            ),
        )
        env.bind(
            "B",
            Relation(
                frozenset({Tuple_(id="2"), Tuple_(id="3")}),
                schema={"id": "str"},
            ),
        )
        result = run("A &. B", env)
        assert len(result) == 1
        assert next(iter(result))["id"] == "2"


class TestSummarize:
    """Test /. (summarize)."""

    def test_summarize_by_key(self) -> None:
        """Summarize groups by key with count and mean aggregates."""
        result = run("E /. dept_id [n: #.  avg: %. salary]")
        assert isinstance(result, Relation)
        assert len(result) == 2
        for t in result:
            if t["dept_id"] == 10:
                assert t["n"] == 3
                assert t["avg"] == pytest.approx(76666.67, abs=0.01)
            else:
                assert t["n"] == 2
                assert t["avg"] == 50000.0

    def test_summarize_multi_key(self) -> None:
        """Summarize groups by multiple keys."""
        result = run("E /. [dept_id role] [n: #.  total: +. salary]")
        assert isinstance(result, Relation)
        assert len(result) == 3
        for t in result:
            if t["dept_id"] == 10 and t["role"] == "engineer":
                assert t["n"] == 2
                assert t["total"] == 170000  # Alice 80k + Dave 90k
            elif t["dept_id"] == 10 and t["role"] == "manager":
                assert t["n"] == 1
                assert t["total"] == 60000  # Bob
            elif t["dept_id"] == 20 and t["role"] == "engineer":
                assert t["n"] == 2
                assert t["total"] == 100000  # Carol 55k + Eve 45k
            else:
                pytest.fail(f"Unexpected group: dept_id={t['dept_id']}, role={t['role']}")

    def test_summarize_all(self) -> None:
        """Summarize-all aggregates the entire relation."""
        result = run("E /. [n: #.  total: +. salary]")
        assert isinstance(result, Relation)
        assert len(result) == 1
        t = next(iter(result))
        assert t["n"] == 5
        assert t["total"] == 330000

    def test_summarize_inherits_schema(self) -> None:
        """Summarize propagates source column types to aggregate output."""
        from decimal import Decimal

        env = Environment()
        env.bind(
            "R",
            Relation(
                frozenset({
                    Tuple_(cat="A", amount=Decimal("10.50")),
                    Tuple_(cat="A", amount=Decimal("20.30")),
                    Tuple_(cat="B", amount=Decimal("5.00")),
                }),
                schema={"cat": "str", "amount": "decimal(2)"},
            ),
        )
        result = run("R /. cat [total: +. amount]", env)
        assert isinstance(result, Relation)
        assert result.schema["cat"] == "str"
        assert result.schema["total"] == "decimal(2)"

    def test_summarize_all_inherits_schema(self) -> None:
        """Summarize-all propagates source column types to aggregate output."""
        from decimal import Decimal

        env = Environment()
        env.bind(
            "R",
            Relation(
                frozenset({
                    Tuple_(amount=Decimal("10.50")),
                    Tuple_(amount=Decimal("20.30")),
                }),
                schema={"amount": "decimal(2)"},
            ),
        )
        result = run("R /. [total: +. amount]", env)
        assert isinstance(result, Relation)
        assert result.schema["total"] == "decimal(2)"


class TestNestBy:
    """Test /: (nest by)."""

    def test_nest_by(self) -> None:
        """Nest-by groups tuples into nested relations by key."""
        result = run("E /: dept_id -> team")
        assert isinstance(result, Relation)
        assert len(result) == 2
        for t in result:
            team = t["team"]
            if t["dept_id"] == 10:
                assert len(team) == 3
            else:
                assert len(team) == 2

    def test_nest_by_multi_key(self) -> None:
        """Nest-by groups by multiple keys."""
        result = run("E /: [dept_id role] -> team")
        assert isinstance(result, Relation)
        assert len(result) == 3
        for t in result:
            team = t["team"]
            if t["dept_id"] == 10 and t["role"] == "engineer":
                assert len(team) == 2  # Alice, Dave
            elif t["dept_id"] == 10 and t["role"] == "manager":
                assert len(team) == 1  # Bob
            elif t["dept_id"] == 20 and t["role"] == "engineer":
                assert len(team) == 2  # Carol, Eve
            else:
                pytest.fail(f"Unexpected group: dept_id={t['dept_id']}, role={t['role']}")


class TestSort:
    """Test $ and ^ (sort and take)."""

    def test_sort_desc(self) -> None:
        """Sort descending orders tuples by attribute value."""
        result = run("E # [name salary] $ salary-")
        assert isinstance(result, list)
        assert len(result) == 5
        assert result[0]["name"] == "Dave"
        assert result[-1]["name"] == "Eve"

    def test_sort_take(self) -> None:
        """Sort then take returns the top N tuples."""
        result = run("E # [name salary] $ salary- ^ 3")
        assert isinstance(result, list)
        assert len(result) == 3
        names = [t["name"] for t in result]
        assert names == ["Dave", "Alice", "Bob"]

    def test_take_from_relation(self) -> None:
        """Take N tuples directly from a relation (no sort required)."""
        result = run("E ^ 3")
        assert isinstance(result, list)
        assert len(result) == 3

    def test_take_from_relation_more_than_available(self) -> None:
        """Taking more than available returns all tuples."""
        result = run("E ^ 100")
        assert isinstance(result, list)
        assert len(result) == 5


class TestOrderColumns:
    """Test $. (order columns)."""

    def test_order_columns_from_relation(self) -> None:
        """$. projects and orders columns from a relation."""
        result = run("E $. [salary name]")
        assert isinstance(result, OrderedArray)
        assert result.column_order == ("salary", "name")
        assert len(result) == 5
        # Each tuple should only have the two columns.
        assert result[0].attributes() == frozenset({"salary", "name"})

    def test_order_columns_single(self) -> None:
        """$. with a single column name."""
        result = run("E $. name")
        assert isinstance(result, OrderedArray)
        assert result.column_order == ("name",)
        assert all(t.attributes() == frozenset({"name"}) for t in result)

    def test_order_columns_from_sorted_list(self) -> None:
        """$. works on a sorted list (from $)."""
        result = run("E $ salary- $. [name salary]")
        assert isinstance(result, OrderedArray)
        assert result.column_order == ("name", "salary")
        # Tuple order should be preserved from the sort.
        assert result[0]["name"] == "Dave"

    def test_order_columns_unknown_attr(self) -> None:
        """$. with an unknown column raises an error."""
        with pytest.raises(ExecutionError, match="unknown attribute.*bogus"):
            run("E $. bogus")

    def test_order_columns_empty_relation(self) -> None:
        """$. on an empty relation preserves the heading and returns empty OrderedArray."""
        env = Environment()
        env.bind("Empty", Relation(frozenset(), attributes=frozenset({"name", "salary"})))
        result = run("Empty $. [salary name]", env)
        assert isinstance(result, OrderedArray)
        assert result.column_order == ("salary", "name")
        assert len(result) == 0

    def test_order_columns_empty_sorted_list(self) -> None:
        """$. on an empty sorted list returns an empty OrderedArray without error."""
        env = Environment()
        env.bind("Empty", Relation(frozenset(), attributes=frozenset({"name", "salary"})))
        result = run("Empty $ salary- $. [salary name]", env)
        assert isinstance(result, OrderedArray)
        assert result.column_order == ("salary", "name")
        assert len(result) == 0


class TestAssignment:
    """Test := (assignment)."""

    def test_simple_assignment(self) -> None:
        """Assignment binds a query result to a name in the environment."""
        env = _make_env()
        result = run("high := E ? salary > 70000", env)
        assert isinstance(result, Relation)
        assert len(result) == 2
        # Verify it was bound in the environment
        assert "high" in env
        assert env.lookup("high") == result

    def test_assignment_then_use(self) -> None:
        """Assigned name can be used in subsequent queries."""
        env = _make_env()
        run("eng := E ? dept_id = 10", env)
        result = run("eng # name", env)
        assert isinstance(result, Relation)
        names = {t["name"] for t in result}
        assert names == {"Alice", "Bob", "Dave"}

    def test_assignment_overwrites(self) -> None:
        """Re-assignment overwrites the previously bound value."""
        env = _make_env()
        run("x := E ? salary > 80000", env)
        assert len(env.lookup("x")) == 1
        run("x := E ? salary > 50000", env)
        assert len(env.lookup("x")) == 4


class TestNumericPromotion:
    """Test string-to-number promotion in arithmetic and comparisons."""

    def _make_mixed_env(self) -> Environment:
        """Create env with a relation where 'val' is str (mixed source)."""
        env = Environment()
        # Simulates a CSV column inferred as str due to mixed values,
        # then filtered down to numeric-only rows.
        env.bind(
            "data",
            Relation(
                frozenset(
                    {
                        Tuple_(name="a", val="10"),
                        Tuple_(name="b", val="20"),
                        Tuple_(name="c", val="30"),
                    }
                )
            ),
        )
        return env

    def test_arithmetic_on_str_values(self) -> None:
        """Extend with arithmetic on string values that are numeric."""
        env = self._make_mixed_env()
        result = run("data +: doubled: val * 2", env)
        assert isinstance(result, Relation)
        for t in result:
            assert isinstance(t["doubled"], int)
            assert t["doubled"] == int(t["val"]) * 2

    def test_comparison_str_vs_int_literal(self) -> None:
        """Filter with numeric comparison on string-typed column."""
        env = self._make_mixed_env()
        result = run("data ? val > 15", env)
        assert isinstance(result, Relation)
        names = {t["name"] for t in result}
        assert names == {"b", "c"}

    def test_comparison_str_vs_float_literal(self) -> None:
        """Filter with float comparison on string-typed column."""
        env = Environment()
        env.bind(
            "data",
            Relation(
                frozenset(
                    {
                        Tuple_(name="a", val="1.5"),
                        Tuple_(name="b", val="2.5"),
                    }
                )
            ),
        )
        result = run("data ? val > 2.0", env)
        names = {t["name"] for t in result}
        assert names == {"b"}

    def test_promotion_non_numeric_stays_str(self) -> None:
        """Non-numeric strings are not promoted — arithmetic fails clearly."""
        env = Environment()
        env.bind(
            "data",
            Relation(frozenset({Tuple_(name="a", val="hello")})),
        )
        with pytest.raises(ExecutionError):
            run("data +: doubled: val * 2", env)

    def test_filter_then_arithmetic(self) -> None:
        """The user's scenario: mixed column, filter to numeric, do math."""
        env = Environment()
        env.bind(
            "data",
            Relation(
                frozenset(
                    {
                        Tuple_(kind="num", val="100"),
                        Tuple_(kind="num", val="200"),
                        Tuple_(kind="str", val="hello"),
                    }
                )
            ),
        )
        # Filter to numeric rows, then do arithmetic
        result = run('data ? kind = "num" +: doubled: val * 2', env)
        assert isinstance(result, Relation)
        assert len(result) == 2
        for t in result:
            assert isinstance(t["doubled"], int)
        vals = {t["doubled"] for t in result}
        assert vals == {200, 400}

    def test_aggregate_sum_on_str_values(self) -> None:
        """Summarize +. on string-typed numeric column promotes values."""
        env = Environment()
        env.bind(
            "R",
            Relation(
                frozenset(
                    {
                        Tuple_(amount="10.50", category="A", type="F"),
                        Tuple_(amount="20.00", category="A", type="F"),
                        Tuple_(amount="5.00", category="B", type="F"),
                        Tuple_(amount="not-a-number", category="X", type="X"),
                    }
                )
            ),
        )
        result = run(
            'R ? type = "F" /. category amt: +. amount', env
        )
        assert isinstance(result, Relation)
        assert len(result) == 2
        for t in result:
            if t["category"] == "A":
                assert t["amt"] == 30.5
            elif t["category"] == "B":
                assert t["amt"] == 5.0

    def test_aggregate_mean_on_str_values(self) -> None:
        """Summarize %. on string-typed numeric column promotes values."""
        env = Environment()
        env.bind(
            "data",
            Relation(
                frozenset(
                    {
                        Tuple_(val="10", grp="a"),
                        Tuple_(val="20", grp="a"),
                    }
                )
            ),
        )
        result = run("data /. grp avg: %. val", env)
        t = next(iter(result))
        assert t["avg"] == 15.0

    def test_aggregate_error_is_execution_error(self) -> None:
        """TypeError from aggregates becomes ExecutionError, not a stack trace."""
        env = Environment()
        env.bind(
            "data",
            Relation(
                frozenset(
                    {
                        Tuple_(val="hello", grp="a"),
                        Tuple_(val="world", grp="a"),
                    }
                )
            ),
        )
        with pytest.raises(ExecutionError):
            run("data /. grp total: +. val", env)


class TestTernary:
    """Test ?: (ternary/conditional) in extend computations."""

    def test_simple_remap(self) -> None:
        """Remap dept_id 10 to 'eng', others to 'other'."""
        result = run('E +: [grp: ?: dept_id = 10 "eng" "other"]')
        assert isinstance(result, Relation)
        for t in result:
            if t["dept_id"] == 10:
                assert t["grp"] == "eng"
            else:
                assert t["grp"] == "other"

    def test_numeric_threshold(self) -> None:
        """Bucket by salary threshold."""
        result = run("E +: [big: ?: salary > 70000 true false]")
        assert isinstance(result, Relation)
        for t in result:
            expected = t["salary"] > 70000
            assert t["big"] == expected

    def test_passthrough(self) -> None:
        """Cap salary at 80000."""
        result = run("E +: [capped: ?: salary > 80000 80000 salary]")
        assert isinstance(result, Relation)
        for t in result:
            if t["salary"] > 80000:
                assert t["capped"] == 80000
            else:
                assert t["capped"] == t["salary"]

    def test_nested_ternary(self) -> None:
        """Nested ternary for tier classification."""
        result = run(
            'E +: [tier: ?: salary >= 80000 "high" (?: salary >= 60000 "mid" "low")]'
        )
        assert isinstance(result, Relation)
        for t in result:
            if t["salary"] >= 80000:
                assert t["tier"] == "high"
            elif t["salary"] >= 60000:
                assert t["tier"] == "mid"
            else:
                assert t["tier"] == "low"

    def test_with_summarize(self) -> None:
        """Ternary followed by summarize."""
        result = run('E +: [grp: ?: dept_id = 10 "A" "B"] /. grp [n: #.]')
        assert isinstance(result, Relation)
        assert len(result) == 2
        for t in result:
            if t["grp"] == "A":
                assert t["n"] == 3  # dept_id=10: Alice, Bob, Dave
            else:
                assert t["n"] == 2  # dept_id=20: Carol, Eve

    def test_unknown_attr_in_branch(self) -> None:
        """Unknown attribute in ternary branch raises ExecutionError, not KeyError."""
        with pytest.raises(ExecutionError, match="Unknown attribute"):
            run('D +: x: ?: dept_id = 10 100 asdf')

    def test_negative_literal_in_branch(self) -> None:
        """Negative numeric literal in ternary branch."""
        result = run("D +: x: ?: dept_id = 10 100 -1")
        assert isinstance(result, Relation)
        for t in result:
            if t["dept_id"] == 10:
                assert t["x"] == 100
            else:
                assert t["x"] == -1

    def test_unbracketed_extend_then_summarize(self) -> None:
        """Unbracketed ternary extend followed by summarize (no bracket ambiguity)."""
        result = run('E +: grp: ?: dept_id = 10 "A" "B" /. grp n: #.')
        assert isinstance(result, Relation)
        assert len(result) == 2
        for t in result:
            if t["grp"] == "A":
                assert t["n"] == 3
            else:
                assert t["n"] == 2


class TestRound:
    """Test ~ (precision) in extend computations."""

    def test_round(self) -> None:
        """salary / 3.0 ~ 2 produces correctly rounded Decimal values."""
        from decimal import Decimal

        result = run("E +: bonus: salary / 3.0 ~ 2 # [name bonus]")
        assert isinstance(result, Relation)
        for t in result:
            if t["name"] == "Alice":
                assert t["bonus"] == Decimal("26666.67")
            elif t["name"] == "Eve":
                assert t["bonus"] == Decimal("15000.00")

    def test_round_decimal_precision(self) -> None:
        """~ preserves Decimal type for Decimal inputs."""
        from decimal import Decimal

        env = Environment()
        env.bind(
            "R",
            Relation(
                frozenset({Tuple_(val=Decimal("10.456"), tag="a")})
            ),
        )
        result = run("R +: r: val ~ 2", env)
        t = next(iter(result))
        assert t["r"] == Decimal("10.46")

    def test_float_decimal_arithmetic(self) -> None:
        """Mixing float (from %.) and Decimal (from ~) works in binop."""
        from decimal import Decimal

        env = Environment()
        env.bind(
            "R",
            Relation(
                frozenset(
                    {
                        Tuple_(a=1.5, b=Decimal("3.00")),
                    }
                )
            ),
        )
        # a (float) * b (Decimal) should not raise TypeError
        result = run("R +: c: a * b", env)
        t = next(iter(result))
        assert isinstance(t["c"], float)
        assert t["c"] == 4.5


class TestFilterAggregateLHS:
    """Test aggregate operators on the LHS of filter conditions."""

    def test_count_eq(self) -> None:
        """Filter by #. phones = 1 keeps employees with exactly one phone."""
        result = run("E *: Phone -> phones ? #. phones = 1")
        assert isinstance(result, Relation)
        names = {t["name"] for t in result}
        assert names == {"Alice"}

    def test_count_gt(self) -> None:
        """Filter by #. phones > 1 keeps employees with more than one phone."""
        result = run("E *: Phone -> phones ? #. phones > 1")
        assert isinstance(result, Relation)
        names = {t["name"] for t in result}
        assert names == {"Carol"}

    def test_count_zero(self) -> None:
        """Filter by #. phones = 0 keeps employees with no phones."""
        result = run("E *: Phone -> phones ? #. phones = 0")
        assert isinstance(result, Relation)
        names = {t["name"] for t in result}
        assert names == {"Bob", "Dave", "Eve"}

    def test_count_bool_combination(self) -> None:
        """Boolean AND of aggregate count conditions."""
        result = run("E *: Phone -> phones ? (#. phones >= 1 & #. phones <= 2)")
        assert isinstance(result, Relation)
        names = {t["name"] for t in result}
        assert names == {"Alice", "Carol"}


class TestBroadcastAggregate:
    """Test /* (broadcast aggregate)."""

    def test_partitioned(self) -> None:
        """Broadcast aggregate partitioned by key adds group values to each tuple."""
        result = run("E /* dept_id [avg: %. salary]")
        assert isinstance(result, Relation)
        # Every original tuple is preserved.
        assert len(result) == 5
        # Original attributes plus the new aggregate column.
        assert "avg" in result.attributes
        assert "name" in result.attributes
        # Tuples in the same dept share the same avg.
        dept10 = {t["avg"] for t in result if t["dept_id"] == 10}
        assert len(dept10) == 1  # all dept 10 employees have same avg

    def test_unpartitioned(self) -> None:
        """Broadcast aggregate without partitioning adds whole-relation aggs."""
        result = run("E /* [total: +. salary]")
        assert isinstance(result, Relation)
        assert len(result) == 5
        # All tuples get the same total.
        totals = {t["total"] for t in result}
        assert len(totals) == 1

    def test_multiple_aggregates(self) -> None:
        """Multiple aggregates in one broadcast."""
        result = run("E /* dept_id [n: #.  total: +. salary]")
        assert isinstance(result, Relation)
        assert len(result) == 5
        assert "n" in result.attributes
        assert "total" in result.attributes

    def test_auto_naming(self) -> None:
        """Auto-naming works like summarize."""
        result = run("E /* dept_id #.")
        assert isinstance(result, Relation)
        assert "count" in result.attributes
        assert len(result) == 5

    def test_preserves_all_attrs(self) -> None:
        """All original attributes are preserved."""
        result = run("E /* dept_id [avg: %. salary]")
        assert result.attributes >= {"name", "salary", "dept_id", "role", "avg"}

    def test_chainable(self) -> None:
        """Broadcast aggregate results can be filtered."""
        # Get employees whose salary is above their dept average.
        result = run("E /* dept_id [avg: %. salary] ? salary > avg")
        assert isinstance(result, Relation)
        # Every result tuple has salary > avg for their dept.
        for t in result:
            assert t["salary"] > t["avg"]


class TestSummarizeExpressions:
    """Test full expressions in summarize slots."""

    def test_summarize_with_round(self) -> None:
        """Summarize with ~ produces rounded Decimal values."""
        from decimal import Decimal

        result = run("E /. dept_id sum: +. salary ~ 2")
        assert isinstance(result, Relation)
        assert len(result) == 2
        for t in result:
            assert isinstance(t["sum"], Decimal)
            if t["dept_id"] == 10:
                assert t["sum"] == Decimal("230000.00")
            else:
                assert t["sum"] == Decimal("100000.00")

    def test_summarize_all_with_round(self) -> None:
        """Summarize-all with ~ works on the entire relation."""
        from decimal import Decimal

        result = run("E /. avg: %. salary ~ 2")
        assert isinstance(result, Relation)
        assert len(result) == 1
        t = next(iter(result))
        assert isinstance(t["avg"], Decimal)
        assert t["avg"] == Decimal("66000.00")

    def test_summarize_arithmetic_with_scalar_subquery(self) -> None:
        """Summarize with aggregate / scalar subquery gives per-group percentages.

        Uses * 1.0 to force float division (same as extend context).
        """
        result = run("E /. dept_id pct: +. salary * 1.0 / (E /. total: +. salary)")
        assert isinstance(result, Relation)
        assert len(result) == 2
        total = 330000
        for t in result:
            if t["dept_id"] == 10:
                expected = 230000 / total
                assert t["pct"] == pytest.approx(expected, rel=1e-6)
            else:
                expected = 100000 / total
                assert t["pct"] == pytest.approx(expected, rel=1e-6)

    def test_summarize_all_arithmetic(self) -> None:
        """Summarize-all with aggregate arithmetic computes manual average."""
        result = run("E /. avg: +. salary / #.")
        assert isinstance(result, Relation)
        assert len(result) == 1
        t = next(iter(result))
        assert t["avg"] == pytest.approx(66000.0, rel=1e-6)

    def test_summarize_subquery_not_1x1_error(self) -> None:
        """Scalar subquery that isn't 1x1 raises ExecutionError."""
        with pytest.raises(ExecutionError, match="exactly 1"):
            # E /. [a: #.  b: +. salary] returns 1 tuple with 2 attributes
            run("E /. dept_id x: (E /. [a: #.  b: +. salary])")

    # --- Auto-naming ---

    def test_summarize_auto_name_count(self) -> None:
        """Auto-named #. produces 'count' column."""
        result = run("E /. dept_id #.")
        assert isinstance(result, Relation)
        for t in result:
            if t["dept_id"] == 10:
                assert t["count"] == 3
            else:
                assert t["count"] == 2

    def test_summarize_auto_name_aggregates(self) -> None:
        """Multiple auto-named aggregates produce correctly named columns."""
        result = run("E /. dept_id [#.  +. salary  %. salary]")
        assert isinstance(result, Relation)
        for t in result:
            if t["dept_id"] == 10:
                assert t["count"] == 3
                assert t["sum_salary"] == 230000
                assert t["mean_salary"] == pytest.approx(76666.67, abs=0.01)
            else:
                assert t["count"] == 2
                assert t["sum_salary"] == 100000
                assert t["mean_salary"] == 50000.0

    def test_summarize_auto_name_mixed(self) -> None:
        """Mix of auto-named and explicitly named columns."""
        result = run("E /. dept_id [#.  avg: %. salary]")
        assert isinstance(result, Relation)
        for t in result:
            assert "count" in t
            assert "avg" in t

    def test_summarize_all_auto_name(self) -> None:
        """Auto-naming works with summarize-all."""
        result = run("E /. [#.  +. salary]")
        assert isinstance(result, Relation)
        t = next(iter(result))
        assert t["count"] == 5
        assert t["sum_salary"] == 330000


class TestCollectAggregate:
    """Test n. (collect) aggregate."""

    def test_collect_attr_in_summarize(self) -> None:
        """Collect a single attribute into a nested relation per group."""
        result = run("E /. dept_id [names: n. name]")
        assert isinstance(result, Relation)
        assert len(result) == 2
        for t in result:
            names_rel = t["names"]
            assert isinstance(names_rel, Relation)
            assert names_rel.attributes == frozenset({"name"})
            name_set = {nt["name"] for nt in names_rel}
            if t["dept_id"] == 10:
                assert name_set == {"Alice", "Bob", "Dave"}
            else:
                assert name_set == {"Carol", "Eve"}

    def test_collect_no_arg_in_summarize(self) -> None:
        """Collect entire group tuples into a nested relation."""
        result = run("E /. dept_id [team: n.]")
        assert isinstance(result, Relation)
        assert len(result) == 2
        for t in result:
            team = t["team"]
            assert isinstance(team, Relation)
            if t["dept_id"] == 10:
                assert len(team) == 3
            else:
                assert len(team) == 2

    def test_collect_mixed_with_scalar(self) -> None:
        """Collect mixed with scalar aggregates in the same summarize."""
        result = run("E /. dept_id [count: #.  names: n. name]")
        assert isinstance(result, Relation)
        assert len(result) == 2
        for t in result:
            assert isinstance(t["names"], Relation)
            if t["dept_id"] == 10:
                assert t["count"] == 3
                assert len(t["names"]) == 3
            else:
                assert t["count"] == 2
                assert len(t["names"]) == 2

    def test_collect_in_summarize_all(self) -> None:
        """Collect in summarize-all gathers all values."""
        result = run("E /. [names: n. name]")
        assert isinstance(result, Relation)
        assert len(result) == 1
        t = next(iter(result))
        names_rel = t["names"]
        assert isinstance(names_rel, Relation)
        name_set = {nt["name"] for nt in names_rel}
        assert name_set == {"Alice", "Bob", "Carol", "Dave", "Eve"}


class TestPercentAggregate:
    """Test p. (percent) aggregate."""

    def test_percent_in_summarize(self) -> None:
        """p. in summarize computes group percent of whole."""
        # Total salary = 80000+60000+55000+90000+45000 = 330000
        # Dept 10 = 230000 -> 230000/330000*100 ≈ 69.7%
        # Dept 20 = 100000 -> 100000/330000*100 ≈ 30.3%
        result = run("E /. dept_id [pct: p. salary ~ 1]")
        assert isinstance(result, Relation)
        assert len(result) == 2
        for t in result:
            from decimal import Decimal

            if t["dept_id"] == 10:
                assert t["pct"] == Decimal("69.7")
            else:
                assert t["pct"] == Decimal("30.3")

    def test_percent_in_summarize_all(self) -> None:
        """p. in summarize-all: whole over whole = 100%."""
        result = run("E /. [pct: p. salary ~ 1]")
        assert isinstance(result, Relation)
        t = next(iter(result))
        from decimal import Decimal

        assert t["pct"] == Decimal("100.0")

    def test_percent_in_extend(self) -> None:
        """p. in extend computes each tuple's percent of the whole."""
        # Alice salary=80000, total=330000 -> 80000/330000*100 ≈ 24.2%
        result = run("E +: pct: p. salary ~ 1")
        assert isinstance(result, Relation)
        from decimal import Decimal

        for t in result:
            if t["name"] == "Alice":
                assert t["pct"] == Decimal("24.2")
            elif t["name"] == "Eve":
                # 45000/330000*100 ≈ 13.6%
                assert t["pct"] == Decimal("13.6")

    def test_percent_in_extend_with_arithmetic(self) -> None:
        """p. participates in arithmetic expressions."""
        result = run("E +: pct: p. salary / 100 ~ 4")
        assert isinstance(result, Relation)
        for t in result:
            if t["name"] == "Alice":
                from decimal import Decimal

                # 80000/330000 * 100 / 100 = 80000/330000 ≈ 0.2424
                assert t["pct"] == Decimal("0.2424")


class TestSchemaOps:
    """Test :: (schema) operator."""

    def test_extract_schema(self) -> None:
        """R :: extracts schema as a relation of {attr, type} tuples."""
        result = run("E ::")
        assert isinstance(result, Relation)
        attrs = {t["attr"] for t in result}
        assert "name" in attrs
        assert "salary" in attrs

    def test_apply_schema_coerces(self) -> None:
        """R :: S coerces column values per the schema."""
        env = Environment()
        env.bind(
            "R",
            Relation(
                frozenset(
                    {
                        Tuple_(name="Alice", salary="80000"),
                        Tuple_(name="Bob", salary="60000"),
                    }
                )
            ),
        )
        env.bind(
            "S",
            Relation(
                frozenset(
                    {
                        Tuple_(attr="salary", type="int"),
                    }
                )
            ),
        )
        result = run("R :: S", env)
        assert isinstance(result, Relation)
        for t in result:
            assert isinstance(t["salary"], int)
        salaries = {t["salary"] for t in result}
        assert salaries == {80000, 60000}

    def test_apply_schema_with_inline_literal(self) -> None:
        """R :: {attr type; ...} with inline schema literal."""
        env = Environment()
        env.bind(
            "R",
            Relation(
                frozenset(
                    {
                        Tuple_(x="1", y="2.5"),
                    }
                )
            ),
        )
        result = run('R :: {attr type; "x" "int"; "y" "float"}', env)
        assert isinstance(result, Relation)
        for t in result:
            assert isinstance(t["x"], int)
            assert isinstance(t["y"], float)
            assert t["x"] == 1
            assert t["y"] == 2.5

    def test_extract_schema_after_coercion(self) -> None:
        """Schema survives coercion and is extractable."""
        env = Environment()
        env.bind(
            "R",
            Relation(
                frozenset({Tuple_(a="10", b="hello")}),
            ),
        )
        env.bind(
            "S",
            Relation(frozenset({Tuple_(attr="a", type="int")})),
        )
        # Apply schema, then extract it
        result = run("R :: S ::", env)
        assert isinstance(result, Relation)
        schema_dict = {t["attr"]: t["type"] for t in result}
        assert schema_dict["a"] == "int"
        assert schema_dict["b"] == "str"

    def test_apply_schema_unknown_attr_error(self) -> None:
        """Applying schema with unknown attribute raises ExecutionError."""
        env = Environment()
        env.bind("R", Relation(frozenset({Tuple_(a="1")})))
        env.bind(
            "S",
            Relation(frozenset({Tuple_(attr="nonexistent", type="int")})),
        )
        with pytest.raises(ExecutionError):
            run("R :: S", env)

    def test_apply_schema_bad_coercion_error(self) -> None:
        """Coercion failure raises ExecutionError."""
        env = Environment()
        env.bind("R", Relation(frozenset({Tuple_(a="not_a_number")})))
        env.bind(
            "S",
            Relation(frozenset({Tuple_(attr="a", type="int")})),
        )
        with pytest.raises(ExecutionError):
            run("R :: S", env)

    def test_apply_decimal_precision(self) -> None:
        """R :: S with decimal(2) quantizes values."""
        env = Environment()
        env.bind(
            "R",
            Relation(frozenset({Tuple_(price="11.599"), Tuple_(price="3.7")})),
        )
        result = run('R :: {attr type; "price" "decimal(2)"}', env)
        assert isinstance(result, Relation)
        from decimal import Decimal

        prices = {t["price"] for t in result}
        assert prices == {Decimal("11.60"), Decimal("3.70")}

    def test_apply_in_constraint(self) -> None:
        """R :: S with in() constraint validates membership."""
        env = Environment()
        env.bind(
            "Status",
            Relation(frozenset({Tuple_(name="open"), Tuple_(name="closed")})),
        )
        env.bind(
            "R",
            Relation(frozenset({Tuple_(status="open")})),
        )
        env.bind(
            "S",
            Relation(
                frozenset({Tuple_(attr="status", type='in(Status, name)')})
            ),
        )
        result = run("R :: S", env)
        assert len(result) == 1
        assert result.schema["status"] == "in(Status, name)"

    def test_apply_in_constraint_rejects_invalid(self) -> None:
        """in() constraint rejects values not in referenced relation."""
        env = Environment()
        env.bind(
            "Status",
            Relation(frozenset({Tuple_(name="open")})),
        )
        env.bind(
            "R",
            Relation(frozenset({Tuple_(status="invalid")})),
        )
        env.bind(
            "S",
            Relation(
                frozenset({Tuple_(attr="status", type='in(Status, name)')})
            ),
        )
        with pytest.raises(ExecutionError, match="not in Status.name"):
            run("R :: S", env)


class TestMembershipOp:
    """Test in. (membership) operator."""

    def test_filter_by_membership(self) -> None:
        """Filter rows where attr value is in another relation."""
        env = Environment()
        env.bind(
            "R",
            Relation(
                frozenset({
                    Tuple_(name="Alice", dept="eng"),
                    Tuple_(name="Bob", dept="sales"),
                    Tuple_(name="Carol", dept="eng"),
                    Tuple_(name="Dave", dept="hr"),
                })
            ),
        )
        env.bind(
            "Valid",
            Relation(
                frozenset({Tuple_(dept="eng"), Tuple_(dept="sales")})
            ),
        )
        result = run("R ? dept in. (Valid # dept)", env)
        assert isinstance(result, Relation)
        assert len(result) == 3
        names = {t["name"] for t in result}
        assert names == {"Alice", "Bob", "Carol"}

    def test_filter_by_membership_excludes(self) -> None:
        """Rows not in the membership set are excluded."""
        env = Environment()
        env.bind(
            "R",
            Relation(frozenset({Tuple_(x=1), Tuple_(x=2), Tuple_(x=3)})),
        )
        env.bind(
            "S",
            Relation(frozenset({Tuple_(v=1), Tuple_(v=3)})),
        )
        result = run("R ? x in. (S # v)", env)
        assert len(result) == 2
        assert {t["x"] for t in result} == {1, 3}

    def test_literal_in_relation(self) -> None:
        """Literal value membership check."""
        env = Environment()
        env.bind(
            "R",
            Relation(frozenset({Tuple_(a=1), Tuple_(a=2)})),
        )
        env.bind(
            "S",
            Relation(frozenset({Tuple_(v="abc"), Tuple_(v="def")})),
        )
        # "abc" is in S#v, so all rows pass
        result = run('R ? "abc" in. (S # v)', env)
        assert len(result) == 2

    def test_literal_not_in_relation(self) -> None:
        """Literal value not in set filters all rows."""
        env = Environment()
        env.bind(
            "R",
            Relation(frozenset({Tuple_(a=1), Tuple_(a=2)})),
        )
        env.bind(
            "S",
            Relation(frozenset({Tuple_(v="abc")})),
        )
        result = run('R ? "xyz" in. (S # v)', env)
        assert len(result) == 0

    def test_in_with_ternary(self) -> None:
        """in. works in ternary expressions."""
        env = Environment()
        env.bind(
            "R",
            Relation(
                frozenset({
                    Tuple_(name="Alice", dept="eng"),
                    Tuple_(name="Bob", dept="hr"),
                })
            ),
        )
        env.bind(
            "CoreDepts",
            Relation(frozenset({Tuple_(d="eng"), Tuple_(d="sales")})),
        )
        result = run(
            'R +: core: ?: dept in. (CoreDepts # d) "yes" "no"', env
        )
        assert isinstance(result, Relation)
        for t in result:
            if t["name"] == "Alice":
                assert t["core"] == "yes"
            elif t["name"] == "Bob":
                assert t["core"] == "no"

    def test_in_multi_column_error(self) -> None:
        """in. with multi-column RHS raises error."""
        env = Environment()
        env.bind("R", Relation(frozenset({Tuple_(x=1)})))
        env.bind(
            "S",
            Relation(frozenset({Tuple_(a=1, b=2)})),
        )
        with pytest.raises(ExecutionError, match="single-column"):
            run("R ? x in. S", env)

    def test_in_with_boolean_combination(self) -> None:
        """in. works with & and | in conditions."""
        env = Environment()
        env.bind(
            "R",
            Relation(
                frozenset({
                    Tuple_(name="Alice", dept="eng", active=True),
                    Tuple_(name="Bob", dept="eng", active=False),
                    Tuple_(name="Carol", dept="hr", active=True),
                })
            ),
        )
        env.bind(
            "CoreDepts",
            Relation(frozenset({Tuple_(d="eng")})),
        )
        result = run(
            "R ? (dept in. (CoreDepts # d) & active = true)", env
        )
        assert len(result) == 1
        assert next(iter(result))["name"] == "Alice"

    def test_in_coercion_str_vs_int(self) -> None:
        """in. matches string LHS against integer RHS via coercion (and vice versa).

        This mirrors the natural join coercion behaviour: if the CSV loader
        stored an id as int in one relation and str in another, in. should
        still find the match.
        """
        env = Environment()
        # LHS relation: id stored as string (as CSV loader often does)
        env.bind(
            "L",
            Relation(frozenset({
                Tuple_(id="42", name="Alice"),
                Tuple_(id="99", name="Bob"),
            })),
        )
        # RHS relation: id stored as integer
        env.bind(
            "Keys",
            Relation(frozenset({Tuple_(id=42)})),
        )
        result = run("L ? id in. (Keys # id)", env)
        assert len(result) == 1
        assert next(iter(result))["name"] == "Alice"

    def test_expr_lhs_in(self) -> None:
        """in. accepts a transformed LHS expression like name .s 'lower'."""
        env = Environment()
        env.bind(
            "R",
            Relation(
                frozenset({
                    Tuple_(name="Alice"),
                    Tuple_(name="BOB"),
                    Tuple_(name="carol"),
                })
            ),
        )
        env.bind(
            "Valid",
            Relation(frozenset({Tuple_(v="alice"), Tuple_(v="carol")})),
        )
        result = run('R ? name .s "lower" in. (Valid # v)', env)
        assert len(result) == 2
        assert {t["name"] for t in result} == {"Alice", "carol"}

    def test_expr_lhs_comparison(self) -> None:
        """Comparison LHS accepts .s 'lower' for case-insensitive equality."""
        env = Environment()
        env.bind(
            "R",
            Relation(
                frozenset({
                    Tuple_(name="Alice"),
                    Tuple_(name="ALICE"),
                    Tuple_(name="Bob"),
                })
            ),
        )
        result = run('R ? name .s "lower" = "alice"', env)
        assert len(result) == 2
        assert {t["name"] for t in result} == {"Alice", "ALICE"}

    def test_modify_enforces_schema(self) -> None:
        """=: on a schema-carrying relation enforces type."""
        env = Environment()
        env.bind(
            "R",
            Relation(
                frozenset({Tuple_(a=1, b="hello")}),
                schema={"a": "int", "b": "str"},
            ),
        )
        # Modifying b to a string should work fine
        result = run('R =: b: "world"', env)
        assert isinstance(result, Relation)
        for t in result:
            assert t["b"] == "world"

    def test_modify_enforces_in_constraint(self) -> None:
        """=: rejects values violating in() constraint."""
        env = Environment()
        env.bind(
            "Status",
            Relation(frozenset({Tuple_(name="open"), Tuple_(name="closed")})),
        )
        env.bind(
            "R",
            Relation(
                frozenset({Tuple_(status="open")}),
                schema={"status": "in(Status, name)"},
            ),
        )
        with pytest.raises(ExecutionError, match="not in Status.name"):
            run('R =: status: "invalid"', env)

    def test_union_enforces_schema(self) -> None:
        """|. on a schema-carrying relation validates incoming values."""
        env = Environment()
        env.bind(
            "Status",
            Relation(frozenset({Tuple_(name="open"), Tuple_(name="closed")})),
        )
        env.bind(
            "R",
            Relation(
                frozenset({Tuple_(status="open")}),
                schema={"status": "in(Status, name)"},
            ),
        )
        # Union with a valid value should work
        env.bind(
            "R2",
            Relation(frozenset({Tuple_(status="closed")})),
        )
        result = run("R |. R2", env)
        assert len(result) == 2

    def test_union_enforces_in_constraint_rejects(self) -> None:
        """|. rejects union when incoming values violate in() constraint."""
        env = Environment()
        env.bind(
            "Status",
            Relation(frozenset({Tuple_(name="open")})),
        )
        env.bind(
            "R",
            Relation(
                frozenset({Tuple_(status="open")}),
                schema={"status": "in(Status, name)"},
            ),
        )
        env.bind(
            "R2",
            Relation(frozenset({Tuple_(status="invalid")})),
        )
        with pytest.raises(ExecutionError, match="not in Status.name"):
            run("R |. R2", env)
