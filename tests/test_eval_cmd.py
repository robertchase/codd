"""Tests for the eval CLI (codd -e)."""

from __future__ import annotations

from pathlib import Path

from click.testing import CliRunner

from codd.cli import main


class TestBashEscaping:
    """Test that bash history expansion escaping is handled."""

    def test_backslash_bang_stripped(self) -> None:
        """Bash escapes ?! to ?\\!, eval should strip the backslash."""
        runner = CliRunner()
        result = runner.invoke(
            main, ["--sample", "-e", 'E ?\\! role = "engineer" # name'],
        )
        assert result.exit_code == 0
        assert "Bob" in result.output


class TestEvalGenkey:
    """Test --genkey flag on eval."""

    def test_genkey_flag(self, tmp_path: Path) -> None:
        """--genkey adds {stem}_id column."""
        csv_file = tmp_path / "items.csv"
        csv_file.write_text("name,price\nApple,1.50\nBanana,0.75\n")

        runner = CliRunner()
        result = runner.invoke(
            main, [str(csv_file), "--genkey", "-e", "items # items_id"],
        )

        assert result.exit_code == 0
        assert "1" in result.output
        assert "2" in result.output

    def test_genkey_prevents_dedup(self, tmp_path: Path) -> None:
        """Duplicate rows get distinct keys, preventing deduplication."""
        csv_file = tmp_path / "data.csv"
        csv_file.write_text("name\nAlice\nAlice\n")

        runner = CliRunner()
        result = runner.invoke(
            main, [str(csv_file), "--genkey", "-e", "data ^ 5"],
        )

        assert result.exit_code == 0
        # Both rows should be present (not deduped).
        assert "1" in result.output
        assert "2" in result.output

    def test_genkey_with_alias(self, tmp_path: Path) -> None:
        """--genkey with name=path uses the name for key column."""
        csv_file = tmp_path / "data.csv"
        csv_file.write_text("x\n1\n2\n")

        runner = CliRunner()
        result = runner.invoke(
            main,
            [f"Stuff={csv_file}", "--genkey", "-e", "Stuff # Stuff_id"],
        )

        assert result.exit_code == 0
        assert "1" in result.output
        assert "2" in result.output

    def test_genkey_stdin(self, tmp_path: Path) -> None:
        """--genkey works with stdin input."""
        runner = CliRunner()
        result = runner.invoke(
            main,
            ["-", "--genkey", "-e", "stdin # stdin_id"],
            input="x\na\nb\n",
        )

        assert result.exit_code == 0
        assert "1" in result.output
        assert "2" in result.output

    def test_no_genkey_deduplicates(self, tmp_path: Path) -> None:
        """Without --genkey, duplicate rows are collapsed."""
        csv_file = tmp_path / "data.csv"
        csv_file.write_text("name\nAlice\nAlice\n")

        runner = CliRunner()
        result = runner.invoke(
            main, [str(csv_file), "-e", "data ^ 5"],
        )

        assert result.exit_code == 0
        # Only one Alice — set semantics.
        assert result.output.count("Alice") == 1


class TestCsvOutput:
    """Test --csv flag."""

    def test_csv_output(self) -> None:
        """--csv outputs CSV instead of table."""
        runner = CliRunner()
        result = runner.invoke(
            main, ["--sample", "--csv", "-e", "E # [name dept_id]"],
        )
        assert result.exit_code == 0
        assert "dept_id,name" in result.output
        assert "+-" not in result.output


class TestOpsFlag:
    """Test --ops flag."""

    def test_ops_prints_reference(self) -> None:
        """--ops prints the primitives reference."""
        runner = CliRunner()
        result = runner.invoke(main, ["--ops"])
        assert result.exit_code == 0
        assert "Relational" in result.output
        assert "#." in result.output
