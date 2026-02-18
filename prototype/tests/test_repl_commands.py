"""Tests for REPL slash commands."""

from __future__ import annotations

import io
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch

import pytest

from prototype.data.workspace import save_workspace
from prototype.executor.environment import Environment
from prototype.model.relation import Relation
from prototype.model.types import Tuple_
from prototype.repl import repl as repl_module
from prototype.repl.repl import _handle_command


@pytest.fixture(autouse=True)
def _reset_last_save_path() -> None:
    """Reset the module-level _last_save_path between tests."""
    repl_module._last_save_path = None


class TestEnvironmentUnbind:
    """Test Environment.unbind()."""

    def test_unbind_existing(self) -> None:
        env = Environment()
        env.bind("R", Relation(frozenset({Tuple_(x=1)})))
        env.unbind("R")
        assert "R" not in env

    def test_unbind_missing_raises(self) -> None:
        env = Environment()
        with pytest.raises(KeyError, match="Unknown relation"):
            env.unbind("nope")


class TestLoadCommand:
    """Test \\load with file arguments."""

    def test_load_no_args_loads_sample(self, capsys: pytest.CaptureFixture[str]) -> None:
        env = Environment()
        _handle_command("\\load", env)
        assert "E" in env
        assert "D" in env
        out = capsys.readouterr().out
        assert "Loaded:" in out

    def test_load_csv_file(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        csv_file = tmp_path / "users.csv"
        csv_file.write_text("name,age\nAlice,30\nBob,25\n")

        env = Environment()
        _handle_command(f"\\load {csv_file}", env)

        assert "users" in env
        rel = env.lookup("users")
        assert len(rel) == 2
        out = capsys.readouterr().out
        assert "Loaded users:" in out

    def test_load_csv_with_alias(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        csv_file = tmp_path / "data.csv"
        csv_file.write_text("x\n1\n2\n")

        env = Environment()
        _handle_command(f"\\load {csv_file} --as=MyData", env)

        assert "MyData" in env
        assert "data" not in env
        out = capsys.readouterr().out
        assert "Loaded MyData:" in out

    def test_load_missing_file(self, capsys: pytest.CaptureFixture[str]) -> None:
        env = Environment()
        _handle_command("\\load /nonexistent/file.csv", env)
        out = capsys.readouterr().out
        assert "file not found" in out

    def test_load_workspace_file(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        # Create a workspace file.
        src_env = Environment()
        src_env.bind("R", Relation(frozenset({Tuple_(val=42)})))
        ws_path = tmp_path / "test.codd"
        save_workspace(src_env, ws_path)

        env = Environment()
        _handle_command(f"\\load {ws_path}", env)

        assert "R" in env
        assert env.lookup("R") == src_env.lookup("R")
        out = capsys.readouterr().out
        assert "Loaded workspace:" in out

    def test_load_workspace_rejects_alias(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        ws_path = tmp_path / "test.codd"
        ws_path.write_text('{"version": 1, "relations": {}}')

        env = Environment()
        _handle_command(f"\\load {ws_path} --as=X", env)
        out = capsys.readouterr().out
        assert "--as cannot be used with workspace" in out


class TestSaveCommand:
    """Test \\save command."""

    def test_save_to_path(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        env = Environment()
        env.bind("T", Relation(frozenset({Tuple_(x=1)})))

        path = tmp_path / "out.codd"
        _handle_command(f"\\save {path}", env)

        assert path.exists()
        out = capsys.readouterr().out
        assert "Saved workspace" in out

    def test_save_no_args_without_prior(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        env = Environment()
        _handle_command("\\save", env)
        out = capsys.readouterr().out
        assert "requires a filename" in out

    def test_save_no_args_reuses_last(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        env = Environment()
        env.bind("T", Relation(frozenset({Tuple_(x=1)})))

        path = tmp_path / "out.codd"
        _handle_command(f"\\save {path}", env)
        capsys.readouterr()  # clear

        # Add another relation and re-save without path.
        env.bind("U", Relation(frozenset({Tuple_(y=2)})))
        _handle_command("\\save", env)
        out = capsys.readouterr().out
        assert "Saved workspace" in out

    def test_save_then_load_roundtrip(
        self, tmp_path: Path
    ) -> None:
        """Full roundtrip: save workspace, create new env, load it back."""
        env1 = Environment()
        env1.bind(
            "prices",
            Relation(
                frozenset(
                    {
                        Tuple_(item="Apple", price=Decimal("1.50")),
                        Tuple_(item="Banana", price=Decimal("0.75")),
                    }
                )
            ),
        )

        path = tmp_path / "prices.codd"
        _handle_command(f"\\save {path}", env1)

        env2 = Environment()
        _handle_command(f"\\load {path}", env2)

        assert env2.lookup("prices") == env1.lookup("prices")


class TestDropCommand:
    """Test \\drop command."""

    def test_drop_existing(self, capsys: pytest.CaptureFixture[str]) -> None:
        env = Environment()
        env.bind("R", Relation(frozenset({Tuple_(x=1)})))
        _handle_command("\\drop R", env)
        assert "R" not in env
        out = capsys.readouterr().out
        assert "Dropped R" in out

    def test_drop_missing(self, capsys: pytest.CaptureFixture[str]) -> None:
        env = Environment()
        _handle_command("\\drop nope", env)
        out = capsys.readouterr().out
        assert "unknown relation" in out

    def test_drop_no_args(self, capsys: pytest.CaptureFixture[str]) -> None:
        env = Environment()
        _handle_command("\\drop", env)
        out = capsys.readouterr().out
        assert "requires a relation name" in out


class TestEnvCommand:
    """Test \\env command."""

    def test_env_empty(self, capsys: pytest.CaptureFixture[str]) -> None:
        env = Environment()
        _handle_command("\\env", env)
        out = capsys.readouterr().out
        assert "no relations loaded" in out

    def test_env_with_relations(self, capsys: pytest.CaptureFixture[str]) -> None:
        env = Environment()
        env.bind("R", Relation(frozenset({Tuple_(x=1, y=2)})))
        _handle_command("\\env", env)
        out = capsys.readouterr().out
        assert "R:" in out
        assert "1 tuples" in out
