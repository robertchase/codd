"""Tests for the executor."""

from prototype.executor.environment import Environment
from prototype.executor.executor import Executor
from prototype.lexer.lexer import Lexer
from prototype.model.relation import Relation
from prototype.model.types import Tuple_
from prototype.parser.parser import Parser


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
        result = run("E # name")
        assert isinstance(result, Relation)
        assert len(result) == 5
        names = {t["name"] for t in result}
        assert names == {"Alice", "Bob", "Carol", "Dave", "Eve"}

    def test_multiple_attrs(self) -> None:
        result = run("E # [name salary]")
        assert isinstance(result, Relation)
        assert result.attributes == frozenset({"name", "salary"})


class TestFilter:
    """Test ? (filter)."""

    def test_gt(self) -> None:
        result = run("E ? salary > 50000")
        assert isinstance(result, Relation)
        assert len(result) == 4

    def test_eq_string(self) -> None:
        result = run('E ? name = "Alice"')
        assert len(result) == 1

    def test_negated(self) -> None:
        result = run('E ?! role = "engineer"')
        assert len(result) == 1
        assert next(iter(result))["name"] == "Bob"

    def test_or_condition(self) -> None:
        result = run("E ? (dept_id = 20 | salary > 80000)")
        assert len(result) == 3
        names = {t["name"] for t in result}
        assert names == {"Carol", "Dave", "Eve"}

    def test_set_membership(self) -> None:
        result = run("E ? dept_id = {10, 20}")
        assert len(result) == 5

    def test_chained_filters(self) -> None:
        result = run("E ? dept_id = 10 ? salary > 70000")
        assert len(result) == 2
        names = {t["name"] for t in result}
        assert names == {"Alice", "Dave"}


class TestChaining:
    """Test chained operations."""

    def test_filter_project(self) -> None:
        result = run("E ? salary > 50000 # [name salary]")
        assert isinstance(result, Relation)
        assert len(result) == 4
        assert result.attributes == frozenset({"name", "salary"})


class TestJoin:
    """Test * and *: (join)."""

    def test_natural_join(self) -> None:
        result = run("E * D")
        assert isinstance(result, Relation)
        assert len(result) == 5
        assert "dept_name" in result.attributes

    def test_join_filter_project(self) -> None:
        result = run('E * D ? dept_name = "Engineering" # [name salary]')
        assert len(result) == 3
        names = {t["name"] for t in result}
        assert names == {"Alice", "Bob", "Dave"}

    def test_nest_join(self) -> None:
        result = run("E *: Phone > phones")
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
        result = run("E *: Phone > phones <: phones")
        assert isinstance(result, Relation)
        # Alice has 1 phone, Carol has 2 -> 3 tuples
        assert len(result) == 3
        assert "phone" in result.attributes
        assert "phones" not in result.attributes
        names = {t["name"] for t in result}
        assert names == {"Alice", "Carol"}


class TestExtend:
    """Test + (extend)."""

    def test_single(self) -> None:
        result = run("E + bonus: salary * 0.1 # [name bonus]")
        assert isinstance(result, Relation)
        for t in result:
            if t["name"] == "Alice":
                assert t["bonus"] == 8000.0


class TestRename:
    """Test @ (rename)."""

    def test_rename(self) -> None:
        result = run("ContractorPay @ [pay > salary]")
        assert isinstance(result, Relation)
        assert "salary" in result.attributes
        assert "pay" not in result.attributes


class TestSetOps:
    """Test |, -, & (set operations)."""

    def test_union(self) -> None:
        result = run("ContractorPay @ [pay > salary] | (E # [name salary])")
        assert isinstance(result, Relation)
        assert len(result) == 6

    def test_difference(self) -> None:
        result = run("E # emp_id - (Phone # emp_id)")
        assert isinstance(result, Relation)
        ids = {t["emp_id"] for t in result}
        assert ids == {2, 4, 5}

    def test_intersect(self) -> None:
        result = run("(E # emp_id) & (Phone # emp_id)")
        assert isinstance(result, Relation)
        ids = {t["emp_id"] for t in result}
        assert ids == {1, 3}


class TestSummarize:
    """Test / and /. (summarize)."""

    def test_summarize_by_key(self) -> None:
        result = run("E / dept_id [n: #.  avg: %. salary]")
        assert isinstance(result, Relation)
        assert len(result) == 2
        for t in result:
            if t["dept_id"] == 10:
                assert t["n"] == 3
                assert t["avg"] == 76666  # (80000+60000+90000)//3
            else:
                assert t["n"] == 2
                assert t["avg"] == 50000

    def test_summarize_all(self) -> None:
        result = run("E /. [n: #.  total: +. salary]")
        assert isinstance(result, Relation)
        assert len(result) == 1
        t = next(iter(result))
        assert t["n"] == 5
        assert t["total"] == 330000


class TestNestBy:
    """Test /: (nest by)."""

    def test_nest_by(self) -> None:
        result = run("E /: dept_id > team")
        assert isinstance(result, Relation)
        assert len(result) == 2
        for t in result:
            team = t["team"]
            if t["dept_id"] == 10:
                assert len(team) == 3
            else:
                assert len(team) == 2


class TestSort:
    """Test $ and ^ (sort and take)."""

    def test_sort_desc(self) -> None:
        result = run("E # [name salary] $ salary-")
        assert isinstance(result, list)
        assert len(result) == 5
        assert result[0]["name"] == "Dave"
        assert result[-1]["name"] == "Eve"

    def test_sort_take(self) -> None:
        result = run("E # [name salary] $ salary- ^ 3")
        assert isinstance(result, list)
        assert len(result) == 3
        names = [t["name"] for t in result]
        assert names == ["Dave", "Alice", "Bob"]
