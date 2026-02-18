"""Tests for the eval CLI subcommand."""

from __future__ import annotations

from pathlib import Path

from click.testing import CliRunner

from prototype.cli.eval_cmd import eval_cmd


class TestEvalGenkey:
    """Test --genkey flag on eval."""

    def test_genkey_flag(self, tmp_path: Path) -> None:
        """--genkey adds {stem}_id column."""
        csv_file = tmp_path / "items.csv"
        csv_file.write_text("name,price\nApple,1.50\nBanana,0.75\n")

        runner = CliRunner()
        result = runner.invoke(eval_cmd, ["--genkey", "items # items_id", str(csv_file)])

        assert result.exit_code == 0
        assert "1" in result.output
        assert "2" in result.output

    def test_genkey_prevents_dedup(self, tmp_path: Path) -> None:
        """Duplicate rows get distinct keys, preventing deduplication."""
        csv_file = tmp_path / "data.csv"
        csv_file.write_text("name\nAlice\nAlice\n")

        runner = CliRunner()
        result = runner.invoke(eval_cmd, ["--genkey", "data ^ 5", str(csv_file)])

        assert result.exit_code == 0
        # Both rows should be present (not deduped).
        assert "1" in result.output
        assert "2" in result.output

    def test_genkey_with_alias(self, tmp_path: Path) -> None:
        """--genkey with --as uses the alias for key name."""
        csv_file = tmp_path / "data.csv"
        csv_file.write_text("x\n1\n2\n")

        runner = CliRunner()
        result = runner.invoke(
            eval_cmd,
            ["--genkey", "--as", f"Stuff={csv_file}", "Stuff # Stuff_id"],
        )

        assert result.exit_code == 0
        assert "1" in result.output
        assert "2" in result.output

    def test_genkey_stdin(self, tmp_path: Path) -> None:
        """--genkey works with stdin input."""
        runner = CliRunner()
        result = runner.invoke(
            eval_cmd,
            ["--genkey", "stdin # stdin_id", "-"],
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
        result = runner.invoke(eval_cmd, ["data ^ 5", str(csv_file)])

        assert result.exit_code == 0
        # Only one Alice — set semantics.
        assert result.output.count("Alice") == 1
