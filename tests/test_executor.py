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


class TestRename:
    """Test @ (rename)."""

    def test_rename(self) -> None:
        """Rename changes an attribute name in the relation."""
        result = run("ContractorPay @ [pay -> salary]")
        assert isinstance(result, Relation)
        assert "salary" in result.attributes
        assert "pay" not in result.attributes


class TestSetOps:
    """Test |., -., &. (set operations)."""

    def test_union(self) -> None:
        """Union combines tuples from two compatible relations."""
        result = run("ContractorPay @ [pay -> salary] |. (E # [name salary])")
        assert isinstance(result, Relation)
        assert len(result) == 6

    def test_difference(self) -> None:
        """Difference removes tuples present in the right relation."""
        result = run("E # emp_id -. (Phone # emp_id)")
        assert isinstance(result, Relation)
        ids = {t["emp_id"] for t in result}
        assert ids == {2, 4, 5}

    def test_intersect(self) -> None:
        """Intersect keeps only tuples present in both relations."""
        result = run("(E # emp_id) &. (Phone # emp_id)")
        assert isinstance(result, Relation)
        ids = {t["emp_id"] for t in result}
        assert ids == {1, 3}


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
