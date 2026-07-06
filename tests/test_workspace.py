"""Tests for workspace save/load (.codd files)."""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path

from codd.data.workspace import (
    is_workspace_file,
    load_workspace,
    save_workspace,
)
from codd.executor.environment import Environment
from codd.model.relation import Relation
from codd.model.types import Tuple_


class TestSaveLoadRoundtrip:
    """Test that save → load produces identical relations."""

    def test_basic_roundtrip(self, tmp_path: Path) -> None:
        """Simple relation with str and int columns roundtrips."""
        env = Environment()
        rel = Relation(
            frozenset(
                {
                    Tuple_(name="Alice", age=30),
                    Tuple_(name="Bob", age=25),
                }
            )
        )
        env.bind("people", rel)

        path = tmp_path / "test.codd"
        save_workspace(env, path)
        loaded = load_workspace(path).relations

        assert "people" in loaded
        assert loaded["people"] == rel

    def test_decimal_roundtrip(self, tmp_path: Path) -> None:
        """Decimal values survive serialization as strings."""
        env = Environment()
        rel = Relation(
            frozenset(
                {
                    Tuple_(item="Apple", price=Decimal("1.50")),
                    Tuple_(item="Banana", price=Decimal("0.75")),
                }
            )
        )
        env.bind("products", rel)

        path = tmp_path / "test.codd"
        save_workspace(env, path)
        loaded = load_workspace(path).relations

        assert "products" in loaded
        for t in loaded["products"]:
            assert isinstance(t["price"], Decimal)
        assert loaded["products"] == rel

    def test_bool_roundtrip(self, tmp_path: Path) -> None:
        """Bool values roundtrip correctly (not confused with int)."""
        env = Environment()
        rel = Relation(
            frozenset(
                {
                    Tuple_(name="Alice", active=True),
                    Tuple_(name="Bob", active=False),
                }
            )
        )
        env.bind("users", rel)

        path = tmp_path / "test.codd"
        save_workspace(env, path)
        loaded = load_workspace(path).relations

        assert loaded["users"] == rel
        for t in loaded["users"]:
            assert isinstance(t["active"], bool)

    def test_multiple_relations(self, tmp_path: Path) -> None:
        """Multiple relations in the same workspace."""
        env = Environment()
        env.bind("A", Relation(frozenset({Tuple_(x=1)})))
        env.bind("B", Relation(frozenset({Tuple_(y="hello")})))

        path = tmp_path / "test.codd"
        save_workspace(env, path)
        loaded = load_workspace(path).relations

        assert set(loaded.keys()) == {"A", "B"}
        assert loaded["A"] == env.lookup("A")
        assert loaded["B"] == env.lookup("B")

    def test_empty_relation(self, tmp_path: Path) -> None:
        """An empty relation with attributes roundtrips."""
        env = Environment()
        rel = Relation(frozenset(), attributes=frozenset({"name", "age"}))
        env.bind("empty", rel)

        path = tmp_path / "test.codd"
        save_workspace(env, path)
        loaded = load_workspace(path).relations

        assert "empty" in loaded
        assert len(loaded["empty"]) == 0
        assert loaded["empty"].attributes == frozenset({"name", "age"})

    def test_float_roundtrip(self, tmp_path: Path) -> None:
        """Float values survive serialization and come back as floats."""
        env = Environment()
        rel = Relation(
            frozenset(
                {
                    Tuple_(name="Alice", ratio=0.333333),
                    Tuple_(name="Bob", ratio=1.5),
                }
            )
        )
        env.bind("data", rel)

        path = tmp_path / "test.codd"
        save_workspace(env, path)
        loaded = load_workspace(path).relations

        assert "data" in loaded
        for t in loaded["data"]:
            assert isinstance(t["ratio"], float)
        assert loaded["data"] == rel

    def test_decimal_with_empty_strings(self, tmp_path: Path) -> None:
        """Decimal columns with empty-string values (from CSV) roundtrip."""
        env = Environment()
        rel = Relation(
            frozenset(
                {
                    Tuple_(name="Alice", amount=Decimal("10.50")),
                    Tuple_(name="Bob", amount=""),
                }
            )
        )
        env.bind("mixed", rel)

        path = tmp_path / "test.codd"
        save_workspace(env, path)
        loaded = load_workspace(path).relations

        assert "mixed" in loaded
        for t in loaded["mixed"]:
            if t["name"] == "Alice":
                assert t["amount"] == Decimal("10.50")
            else:
                assert t["amount"] == ""

    def test_rva_roundtrip(self, tmp_path: Path) -> None:
        """Relation-valued attributes (nested relations) roundtrip."""
        phones = Relation(
            frozenset(
                {
                    Tuple_(phone="555-1234"),
                    Tuple_(phone="555-5678"),
                }
            )
        )
        env = Environment()
        rel = Relation(
            frozenset({Tuple_(name="Alice", phones=phones)})
        )
        env.bind("contacts", rel)

        path = tmp_path / "test.codd"
        save_workspace(env, path)
        loaded = load_workspace(path).relations

        assert loaded["contacts"] == rel

    def test_empty_workspace(self, tmp_path: Path) -> None:
        """An environment with no relations produces a valid workspace."""
        env = Environment()
        path = tmp_path / "test.codd"
        save_workspace(env, path)
        loaded = load_workspace(path).relations
        assert loaded == {}


class TestWorkspaceV2:
    """Test v2 persistence: types and functions survive save/load."""

    def _run(self, src: str, env: Environment) -> object:
        from codd.executor.executor import Executor
        from codd.lexer.lexer import Lexer
        from codd.parser.parser import Parser

        return Executor(env).execute(Parser(Lexer(src).tokenize()).parse())

    def test_types_roundtrip(self, tmp_path: Path) -> None:
        """UDT aliases survive save/load."""
        env = Environment()
        self._run("Money := type decimal(2)", env)
        self._run("Age := type int", env)

        path = tmp_path / "ws.codd"
        save_workspace(env, path)

        env2 = Environment()
        load_workspace(path).bind_into(env2)
        assert env2.lookup_type("Money") == "decimal(2)"
        assert env2.lookup_type("Age") == "int"

    def test_functions_roundtrip(self, tmp_path: Path) -> None:
        """Functions (parameterless and parameterized) survive save/load."""
        env = Environment()
        self._run('active := fn ? status = "active"', env)
        self._run("top(n) := fn $ amount- ^ n", env)

        path = tmp_path / "ws.codd"
        save_workspace(env, path)

        env2 = Environment()
        load_workspace(path).bind_into(env2)
        assert env2.has_function("active")
        assert env2.has_function("top")
        # Reloaded functions actually run.
        env2.bind("R", Relation(frozenset({
            Tuple_(status="active", amount=5),
            Tuple_(status="idle", amount=9),
        })))
        result = self._run("R active", env2)
        assert len(result) == 1
        # Parameterized function still takes args.
        result = self._run("R top(1)", env2)
        assert len(result) == 1
        assert result[0]["amount"] == 9

    def test_v1_file_still_loads(self, tmp_path: Path) -> None:
        """A v1 workspace (relations only) loads without error."""
        path = tmp_path / "old.codd"
        path.write_text(
            '{"version": 1, "relations": {"A": '
            '{"attributes": {"x": "int"}, "tuples": [{"x": 1}]}}}'
        )
        ws = load_workspace(path)
        assert set(ws.relations) == {"A"}
        assert ws.types == {}
        assert ws.functions == {}

    def test_bad_function_body_errors_with_name(self, tmp_path: Path) -> None:
        """A function body that no longer parses names the function."""
        path = tmp_path / "ws.codd"
        path.write_text(
            '{"version": 2, "relations": {}, "types": {}, '
            '"functions": {"broken": {"params": [], "body": "? ("}}}'
        )
        try:
            load_workspace(path)
            assert False, "should have raised"
        except ValueError as e:
            assert "broken" in str(e)

    def test_save_is_atomic_no_tmp_left(self, tmp_path: Path) -> None:
        """save_workspace leaves no .tmp file behind."""
        env = Environment()
        env.bind("A", Relation(frozenset({Tuple_(x=1)})))
        path = tmp_path / "ws.codd"
        save_workspace(env, path)
        assert path.exists()
        assert not (tmp_path / "ws.codd.tmp").exists()


class TestIsWorkspaceFile:
    """Test workspace file sniffing."""

    def test_valid_workspace(self, tmp_path: Path) -> None:
        """Valid .codd JSON with version key is recognized."""
        path = tmp_path / "test.codd"
        path.write_text('{"version": 1, "relations": {}}')
        assert is_workspace_file(path) is True

    def test_csv_file(self, tmp_path: Path) -> None:
        """CSV file is not recognized as a workspace."""
        path = tmp_path / "test.csv"
        path.write_text("name,age\nAlice,30\n")
        assert is_workspace_file(path) is False

    def test_invalid_json(self, tmp_path: Path) -> None:
        """Non-JSON content is not recognized as a workspace."""
        path = tmp_path / "test.codd"
        path.write_text("not json at all")
        assert is_workspace_file(path) is False

    def test_json_without_version(self, tmp_path: Path) -> None:
        """JSON lacking a version key is not a workspace."""
        path = tmp_path / "test.json"
        path.write_text('{"data": [1, 2, 3]}')
        assert is_workspace_file(path) is False
