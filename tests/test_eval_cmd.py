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


class TestFileEval:
    """Test -f (file evaluation) with --arg substitution."""

    def test_single_expression(self, tmp_path: Path) -> None:
        """A script with one expression prints its result."""
        script = tmp_path / "query.codd"
        script.write_text("E # name\n")

        runner = CliRunner()
        result = runner.invoke(main, ["--sample", "-f", str(script)])
        assert result.exit_code == 0
        assert "Alice" in result.output

    def test_assignments_and_final_expression(self, tmp_path: Path) -> None:
        """Assignments accumulate; last line's result is printed."""
        script = tmp_path / "query.codd"
        script.write_text("eng := E ? dept_id = 10\neng # name\n")

        runner = CliRunner()
        result = runner.invoke(main, ["--sample", "-f", str(script)])
        assert result.exit_code == 0
        assert "Alice" in result.output
        assert "Bob" in result.output
        # Carol is in dept 20, should not appear.
        assert "Carol" not in result.output

    def test_arg_substitution_numeric(self, tmp_path: Path) -> None:
        """--arg substitutes numeric values into {{placeholders}}."""
        script = tmp_path / "query.codd"
        script.write_text("E ? salary > {{min_sal}} # name\n")

        runner = CliRunner()
        result = runner.invoke(
            main, ["--sample", "-f", str(script), "--arg", "min_sal=70000"],
        )
        assert result.exit_code == 0
        assert "Alice" in result.output
        assert "Dave" in result.output
        assert "Eve" not in result.output

    def test_arg_substitution_string(self, tmp_path: Path) -> None:
        """--arg substitutes string values (quotes in the script)."""
        script = tmp_path / "query.codd"
        script.write_text('E ? role = "{{role}}" # name\n')

        runner = CliRunner()
        result = runner.invoke(
            main, ["--sample", "-f", str(script), "--arg", "role=manager"],
        )
        assert result.exit_code == 0
        assert "Bob" in result.output

    def test_missing_arg_error(self, tmp_path: Path) -> None:
        """Unresolved {{placeholder}} raises a clear error."""
        script = tmp_path / "query.codd"
        script.write_text("E ? salary > {{min_sal}}\n")

        runner = CliRunner()
        result = runner.invoke(main, ["--sample", "-f", str(script)])
        assert result.exit_code != 0
        assert "min_sal" in result.output

    def test_e_and_f_conflict(self, tmp_path: Path) -> None:
        """Using both -e and -f is an error."""
        script = tmp_path / "query.codd"
        script.write_text("E\n")

        runner = CliRunner()
        result = runner.invoke(
            main, ["--sample", "-e", "E", "-f", str(script)],
        )
        assert result.exit_code != 0
        assert "Cannot use both" in result.output

    def test_arg_without_f_error(self) -> None:
        """--arg without -f is an error."""
        runner = CliRunner()
        result = runner.invoke(
            main, ["--sample", "-e", "E", "--arg", "x=1"],
        )
        assert result.exit_code != 0
        assert "--arg requires -f" in result.output

    def test_comments_and_blank_lines(self, tmp_path: Path) -> None:
        """Comments (#) and blank lines are skipped."""
        script = tmp_path / "query.codd"
        script.write_text(
            "# This is a comment\n"
            "\n"
            "eng := E ? dept_id = 10\n"
            "# Another comment\n"
            "\n"
            "eng # name\n"
        )

        runner = CliRunner()
        result = runner.invoke(main, ["--sample", "-f", str(script)])
        assert result.exit_code == 0
        assert "Alice" in result.output

    def test_csv_output_with_file(self, tmp_path: Path) -> None:
        """--csv works with -f."""
        script = tmp_path / "query.codd"
        script.write_text("E # [name dept_id]\n")

        runner = CliRunner()
        result = runner.invoke(
            main, ["--sample", "--csv", "-f", str(script)],
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


class TestPerFileGenkey:
    """Test +key per-file genkey syntax."""

    def test_plus_key(self, tmp_path: Path) -> None:
        """file.csv+key adds {stem}_id column."""
        csv_file = tmp_path / "items.csv"
        csv_file.write_text("name,price\nApple,1.50\nBanana,0.75\n")

        runner = CliRunner()
        result = runner.invoke(
            main, [f"{csv_file}+key", "-e", "items # items_id"],
        )
        assert result.exit_code == 0
        assert "1" in result.output
        assert "2" in result.output

    def test_plus_key_custom_name(self, tmp_path: Path) -> None:
        """file.csv+key=oid names the column exactly 'oid'."""
        csv_file = tmp_path / "items.csv"
        csv_file.write_text("name,price\nApple,1.50\n")

        runner = CliRunner()
        result = runner.invoke(
            main, [f"{csv_file}+key=oid", "-e", "items # oid"],
        )
        assert result.exit_code == 0
        assert "1" in result.output

    def test_alias_plus_key(self, tmp_path: Path) -> None:
        """n=file.csv+key uses alias for key column name."""
        csv_file = tmp_path / "data.csv"
        csv_file.write_text("x\n1\n2\n")

        runner = CliRunner()
        result = runner.invoke(
            main, [f"R={csv_file}+key", "-e", "R # R_id"],
        )
        assert result.exit_code == 0
        assert "1" in result.output
        assert "2" in result.output

    def test_per_file_without_global(self, tmp_path: Path) -> None:
        """Only the +key file gets a key; other files don't."""
        csv_a = tmp_path / "a.csv"
        csv_a.write_text("x\n1\n")
        csv_b = tmp_path / "b.csv"
        csv_b.write_text("y\n2\n")

        runner = CliRunner()
        # Only a gets +key
        result = runner.invoke(
            main, [f"{csv_a}+key", str(csv_b), "-e", "a :: "],
        )
        assert result.exit_code == 0
        assert "a_id" in result.output

        # b should not have b_id
        result = runner.invoke(
            main, [f"{csv_a}+key", str(csv_b), "-e", "b :: "],
        )
        assert result.exit_code == 0
        assert "b_id" not in result.output
