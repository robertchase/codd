"""Integration tests: parse and execute examples from algebra.md.

Each test verifies the full pipeline: lex -> parse -> execute -> check results.
"""

import io
import tempfile
from decimal import Decimal

from prototype.data.loader import load_csv
from prototype.data.sample import load_sample_data
from prototype.executor.environment import Environment
from prototype.executor.executor import Executor
from prototype.lexer.lexer import Lexer
from prototype.model.relation import Relation
from prototype.model.types import Tuple_
from prototype.parser.parser import Parser


def _env() -> Environment:
    """Create environment with sample data."""
    env = Environment()
    load_sample_data(env)
    return env


def run(source: str) -> Relation | list[Tuple_]:
    """Lex, parse, execute an expression against sample data."""
    env = _env()
    tokens = Lexer(source).tokenize()
    tree = Parser(tokens).parse()
    return Executor(env).execute(tree)


class TestProjectExamples:
    """Test project examples from algebra.md."""

    def test_project_single(self) -> None:
        """E # name -> 5 distinct names."""
        result = run("E # name")
        assert isinstance(result, Relation)
        assert len(result) == 5
        names = {t["name"] for t in result}
        assert names == {"Alice", "Bob", "Carol", "Dave", "Eve"}

    def test_project_multiple(self) -> None:
        """E # [name salary] -> 5 tuples with name and salary."""
        result = run("E # [name salary]")
        assert isinstance(result, Relation)
        assert result.attributes == frozenset({"name", "salary"})
        assert len(result) == 5


class TestFilterExamples:
    """Test filter examples from algebra.md."""

    def test_filter_gt(self) -> None:
        """E ? salary > 50000 -> Alice, Bob, Carol, Dave (4 tuples)."""
        result = run("E ? salary > 50000")
        assert len(result) == 4
        names = {t["name"] for t in result}
        assert "Eve" not in names

    def test_filter_project_chain(self) -> None:
        """E ? salary > 50000 # [name salary] -> 4 tuples."""
        result = run("E ? salary > 50000 # [name salary]")
        assert len(result) == 4
        assert result.attributes == frozenset({"name", "salary"})

    def test_chained_filters(self) -> None:
        """E ? dept_id = 10 ? salary > 70000 -> Alice, Dave."""
        result = run("E ? dept_id = 10 ? salary > 70000")
        assert len(result) == 2
        names = {t["name"] for t in result}
        assert names == {"Alice", "Dave"}

    def test_or_filter(self) -> None:
        """E ? (dept_id = 20 | salary > 80000) -> Carol, Dave, Eve."""
        result = run("E ? (dept_id = 20 | salary > 80000)")
        assert len(result) == 3
        names = {t["name"] for t in result}
        assert names == {"Carol", "Dave", "Eve"}

    def test_negated_filter(self) -> None:
        """E ?! role = "engineer" -> Bob only."""
        result = run('E ?! role = "engineer"')
        assert len(result) == 1
        assert next(iter(result))["name"] == "Bob"


class TestJoinExamples:
    """Test join examples from algebra.md."""

    def test_natural_join(self) -> None:
        """E * D -> 5 tuples with dept_name."""
        result = run("E * D")
        assert len(result) == 5
        for t in result:
            if t["dept_id"] == 10:
                assert t["dept_name"] == "Engineering"
            else:
                assert t["dept_name"] == "Sales"

    def test_join_filter_project(self) -> None:
        """E * D ? dept_name = "Engineering" # [name salary] -> 3 tuples."""
        result = run('E * D ? dept_name = "Engineering" # [name salary]')
        assert len(result) == 3
        names = {t["name"] for t in result}
        assert names == {"Alice", "Bob", "Dave"}
        salaries = {t["name"]: t["salary"] for t in result}
        assert salaries == {"Alice": 80000, "Bob": 60000, "Dave": 90000}

    def test_nest_join(self) -> None:
        """E *: Phone > phones -> 5 tuples, nested phone relations."""
        result = run("E *: Phone > phones")
        assert len(result) == 5
        for t in result:
            phones = t["phones"]
            assert isinstance(phones, Relation)
            if t["emp_id"] == 1:
                assert len(phones) == 1
                phone_vals = {pt["phone"] for pt in phones}
                assert phone_vals == {"555-1234"}
            elif t["emp_id"] == 3:
                assert len(phones) == 2
                phone_vals = {pt["phone"] for pt in phones}
                assert phone_vals == {"555-5678", "555-9999"}
            else:
                # Bob, Dave, Eve have no phones
                assert len(phones) == 0


class TestUnnestExamples:
    """Test unnest examples from algebra.md."""

    def test_nest_then_unnest_roundtrip(self) -> None:
        """E *: Phone > phones <: phones -> same shape as E * Phone."""
        unnested = run("E *: Phone > phones <: phones")
        joined = run("E * Phone")
        assert isinstance(unnested, Relation)
        assert isinstance(joined, Relation)
        assert len(unnested) == len(joined)
        assert unnested.attributes == joined.attributes
        assert unnested == joined

    def test_unnest_drops_empty_rvas(self) -> None:
        """Unnest drops tuples with empty RVAs (no phones)."""
        result = run("E *: Phone > phones <: phones")
        assert isinstance(result, Relation)
        # Only Alice (1 phone) and Carol (2 phones) survive
        names = {t["name"] for t in result}
        assert names == {"Alice", "Carol"}
        assert len(result) == 3


class TestExtendExamples:
    """Test extend examples from algebra.md."""

    def test_extend_bonus(self) -> None:
        """E + bonus: salary * 0.1 # [name salary bonus]."""
        result = run("E + bonus: salary * 0.1 # [name salary bonus]")
        assert len(result) == 5
        for t in result:
            expected_bonus = t["salary"] * 0.1
            assert t["bonus"] == expected_bonus


class TestRenameExamples:
    """Test rename examples from algebra.md."""

    def test_rename(self) -> None:
        """ContractorPay @ [pay > salary] -> (name: Frank, salary: 70000)."""
        result = run("ContractorPay @ [pay > salary]")
        assert len(result) == 1
        t = next(iter(result))
        assert t["name"] == "Frank"
        assert t["salary"] == 70000

    def test_rename_then_union(self) -> None:
        """ContractorPay @ [pay > salary] | (E # [name salary]) -> 6 tuples."""
        result = run("ContractorPay @ [pay > salary] | (E # [name salary])")
        assert len(result) == 6
        names = {t["name"] for t in result}
        assert "Frank" in names
        assert "Alice" in names


class TestSetOpExamples:
    """Test set operation examples from algebra.md."""

    def test_difference(self) -> None:
        """E # emp_id - (Phone # emp_id) -> emp_ids {2, 4, 5}."""
        result = run("E # emp_id - (Phone # emp_id)")
        assert len(result) == 3
        ids = {t["emp_id"] for t in result}
        assert ids == {2, 4, 5}

    def test_intersect(self) -> None:
        """(E # emp_id) & (Phone # emp_id) -> emp_ids {1, 3}."""
        result = run("(E # emp_id) & (Phone # emp_id)")
        assert len(result) == 2
        ids = {t["emp_id"] for t in result}
        assert ids == {1, 3}


class TestSummarizeExamples:
    """Test summarize examples from algebra.md."""

    def test_summarize_by_dept(self) -> None:
        """E / dept_id [n: #.  avg: %. salary].

        dept 10: n=3, avg=76666 (230000//3)
        dept 20: n=2, avg=50000
        """
        result = run("E / dept_id [n: #.  avg: %. salary]")
        assert len(result) == 2
        for t in result:
            if t["dept_id"] == 10:
                assert t["n"] == 3
                assert t["avg"] == 76666
            elif t["dept_id"] == 20:
                assert t["n"] == 2
                assert t["avg"] == 50000

    def test_summarize_all(self) -> None:
        """E /. [n: #.  total: +. salary] -> n=5, total=330000."""
        result = run("E /. [n: #.  total: +. salary]")
        assert len(result) == 1
        t = next(iter(result))
        assert t["n"] == 5
        assert t["total"] == 330000


class TestNestByExamples:
    """Test nest by examples from algebra.md."""

    def test_nest_by(self) -> None:
        """E /: dept_id > team -> 2 groups."""
        result = run("E /: dept_id > team")
        assert len(result) == 2
        for t in result:
            team = t["team"]
            assert isinstance(team, Relation)
            if t["dept_id"] == 10:
                assert len(team) == 3
            else:
                assert len(team) == 2

    def test_nest_by_with_aggregate(self) -> None:
        """E /: dept_id > team + [top: >. team.salary] # [dept_id top].

        dept 10: top=90000, dept 20: top=55000.
        """
        result = run("E /: dept_id > team + [top: >. team.salary] # [dept_id top]")
        assert len(result) == 2
        for t in result:
            if t["dept_id"] == 10:
                assert t["top"] == 90000
            elif t["dept_id"] == 20:
                assert t["top"] == 55000


class TestSortExamples:
    """Test sort and take examples from algebra.md."""

    def test_sort_descending(self) -> None:
        """E # [name salary] $ salary- -> ordered array."""
        result = run("E # [name salary] $ salary-")
        assert isinstance(result, list)
        assert len(result) == 5
        assert result[0]["name"] == "Dave"
        assert result[0]["salary"] == 90000
        assert result[1]["name"] == "Alice"
        assert result[1]["salary"] == 80000
        assert result[2]["name"] == "Bob"
        assert result[2]["salary"] == 60000
        assert result[3]["name"] == "Carol"
        assert result[3]["salary"] == 55000
        assert result[4]["name"] == "Eve"
        assert result[4]["salary"] == 45000

    def test_sort_take(self) -> None:
        """E # [name salary] $ salary- ^ 3 -> top 3 earners."""
        result = run("E # [name salary] $ salary- ^ 3")
        assert isinstance(result, list)
        assert len(result) == 3
        names = [t["name"] for t in result]
        assert names == ["Dave", "Alice", "Bob"]

    def test_multi_key_sort(self) -> None:
        """E # [name salary dept_id] $ [dept_id salary-] -> sorted by dept asc, salary desc."""
        result = run("E # [name salary dept_id] $ [dept_id salary-]")
        assert isinstance(result, list)
        # dept 10 first (ascending), within that salary descending
        assert result[0]["dept_id"] == 10
        assert result[0]["name"] == "Dave"  # 90000
        assert result[1]["dept_id"] == 10
        assert result[1]["name"] == "Alice"  # 80000
        assert result[2]["dept_id"] == 10
        assert result[2]["name"] == "Bob"  # 60000
        # Then dept 20
        assert result[3]["dept_id"] == 20
        assert result[3]["name"] == "Carol"  # 55000
        assert result[4]["dept_id"] == 20
        assert result[4]["name"] == "Eve"  # 45000


class TestComplexChains:
    """Test complex multi-operator chains from the design doc."""

    def test_join_filter_project_sort(self) -> None:
        """E * D ? dept_name = "Engineering" # [name salary] $ salary-."""
        result = run('E * D ? dept_name = "Engineering" # [name salary] $ salary-')
        assert isinstance(result, list)
        assert len(result) == 3
        assert result[0]["name"] == "Dave"
        assert result[1]["name"] == "Alice"
        assert result[2]["name"] == "Bob"

    def test_filter_nest_join_project(self) -> None:
        """E ? dept_id = 10 ? salary > 50000 *: Phone > phones # [name salary phones]."""
        result = run(
            "E ? dept_id = 10 ? salary > 50000 *: Phone > phones # [name salary phones]"
        )
        assert isinstance(result, Relation)
        assert len(result) == 3
        names = {t["name"] for t in result}
        assert names == {"Alice", "Bob", "Dave"}
        for t in result:
            phones = t["phones"]
            assert isinstance(phones, Relation)
            if t["name"] == "Alice":
                assert len(phones) == 1
            else:
                # Bob and Dave have no phones
                assert len(phones) == 0

    def test_set_membership_filter(self) -> None:
        """E ? dept_id = {10, 20} -> all 5 employees."""
        result = run("E ? dept_id = {10, 20}")
        assert len(result) == 5

    def test_aggregates_of_aggregates(self) -> None:
        """(E / dept_id [n: #.]) /. [avg_size: %. n] -> avg_size = 2.

        dept 10: 3, dept 20: 2. Mean = (3+2)//2 = 2.
        """
        result = run("(E / dept_id [n: #.]) /. [avg_size: %. n]")
        assert isinstance(result, Relation)
        assert len(result) == 1
        t = next(iter(result))
        assert t["avg_size"] == 2  # (3+2)//2 = 2 (integer floor division)


class TestCsvLoading:
    """Test loading CSV files and querying them."""

    def test_load_and_filter(self) -> None:
        """Load a CSV, filter it, verify results."""
        csv_data = "name,age,city\nAlice,30,NYC\nBob,25,LA\nCarol,35,NYC\n"
        env = Environment()
        rel = load_csv(io.StringIO(csv_data), "people")
        env.bind("people", rel)

        tokens = Lexer("people ? age > 28").tokenize()
        tree = Parser(tokens).parse()
        result = Executor(env).execute(tree)
        assert isinstance(result, Relation)
        assert len(result) == 2
        names = {t["name"] for t in result}
        assert names == {"Alice", "Carol"}

    def test_load_and_project(self) -> None:
        """Load CSV, project columns."""
        csv_data = "id,name,score\n1,Alice,95.5\n2,Bob,87.0\n"
        env = Environment()
        rel = load_csv(io.StringIO(csv_data), "students")
        env.bind("students", rel)

        tokens = Lexer("students # [name score]").tokenize()
        tree = Parser(tokens).parse()
        result = Executor(env).execute(tree)
        assert result.attributes == frozenset({"name", "score"})
        for t in result:
            assert isinstance(t["score"], Decimal)

    def test_load_and_join(self) -> None:
        """Load two CSVs, join them."""
        emp_csv = "emp_id,name,dept_id\n1,Alice,10\n2,Bob,20\n"
        dept_csv = "dept_id,dept_name\n10,Engineering\n20,Sales\n"
        env = Environment()
        env.bind("emp", load_csv(io.StringIO(emp_csv), "emp"))
        env.bind("dept", load_csv(io.StringIO(dept_csv), "dept"))

        tokens = Lexer("emp * dept").tokenize()
        tree = Parser(tokens).parse()
        result = Executor(env).execute(tree)
        assert len(result) == 2
        assert "dept_name" in result.attributes
        for t in result:
            if t["name"] == "Alice":
                assert t["dept_name"] == "Engineering"

    def test_load_file_from_disk(self) -> None:
        """Write a CSV to a temp file, load it, query it."""
        csv_content = "product,price\nApple,1.50\nBanana,0.75\nCherry,2.00\n"
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".csv", delete=False
        ) as f:
            f.write(csv_content)
            f.flush()
            path = f.name

        env = Environment()
        with open(path) as fh:
            rel = load_csv(fh, "products")
        env.bind("products", rel)

        tokens = Lexer("products ? price > 1.0").tokenize()
        tree = Parser(tokens).parse()
        result = Executor(env).execute(tree)
        assert len(result) == 2
        names = {t["product"] for t in result}
        assert names == {"Apple", "Cherry"}


class TestAssignmentIntegration:
    """Test := assignment in full pipeline."""

    def test_assign_and_reuse(self) -> None:
        """Assign a filtered relation, then query it."""
        env = _env()
        tokens = Lexer("high := E ? salary > 70000").tokenize()
        tree = Parser(tokens).parse()
        Executor(env).execute(tree)

        tokens2 = Lexer("high # name").tokenize()
        tree2 = Parser(tokens2).parse()
        result = Executor(env).execute(tree2)
        assert isinstance(result, Relation)
        names = {t["name"] for t in result}
        assert names == {"Alice", "Dave"}

    def test_assign_with_csv_data(self) -> None:
        """Load CSV, assign a derived relation, query it."""
        csv_data = "name,age\nAlice,30\nBob,25\nCarol,35\n"
        env = Environment()
        env.bind("people", load_csv(io.StringIO(csv_data), "people"))

        tokens = Lexer("seniors := people ? age >= 30").tokenize()
        tree = Parser(tokens).parse()
        Executor(env).execute(tree)

        tokens2 = Lexer("seniors # name").tokenize()
        tree2 = Parser(tokens2).parse()
        result = Executor(env).execute(tree2)
        names = {t["name"] for t in result}
        assert names == {"Alice", "Carol"}
