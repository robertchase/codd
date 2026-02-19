"""Tests for workspace save/load (.codd files)."""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path

from prototype.data.workspace import (
    is_workspace_file,
    load_workspace,
    save_workspace,
)
from prototype.executor.environment import Environment
from prototype.model.relation import Relation
from prototype.model.types import Tuple_


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
        loaded = load_workspace(path)

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
        loaded = load_workspace(path)

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
        loaded = load_workspace(path)

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
        loaded = load_workspace(path)

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
        loaded = load_workspace(path)

        assert "empty" in loaded
        assert len(loaded["empty"]) == 0
        assert loaded["empty"].attributes == frozenset({"name", "age"})

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
        loaded = load_workspace(path)

        assert loaded["contacts"] == rel

    def test_empty_workspace(self, tmp_path: Path) -> None:
        """An environment with no relations produces a valid workspace."""
        env = Environment()
        path = tmp_path / "test.codd"
        save_workspace(env, path)
        loaded = load_workspace(path)
        assert loaded == {}


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
