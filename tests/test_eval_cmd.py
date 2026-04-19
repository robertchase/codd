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


class TestScriptCommands:
    """Test backslash commands in -f scripts."""

    def test_load_in_script(self, tmp_path: Path) -> None:
        """\\load works inside a -f script."""
        csv_file = tmp_path / "data.csv"
        csv_file.write_text("x,y\n1,2\n3,4\n")

        script = tmp_path / "query.codd"
        script.write_text(f"\\load {csv_file} d\nd # x\n")

        runner = CliRunner()
        result = runner.invoke(main, ["-f", str(script)])
        assert result.exit_code == 0
        assert "1" in result.output
        assert "3" in result.output

    def test_export_in_script(self, tmp_path: Path) -> None:
        """\\export works inside a -f script."""
        out_file = tmp_path / "out.csv"

        script = tmp_path / "query.codd"
        script.write_text(f"\\export {out_file} E # name\n")

        runner = CliRunner()
        result = runner.invoke(main, ["--sample", "-f", str(script)])
        assert result.exit_code == 0
        assert out_file.exists()
        content = out_file.read_text()
        assert "Alice" in content

    def test_load_silent_in_script(self, tmp_path: Path) -> None:
        """\\load success messages are suppressed in -f scripts."""
        csv_file = tmp_path / "data.csv"
        csv_file.write_text("x\n1\n2\n")

        script = tmp_path / "query.codd"
        script.write_text(f"\\load {csv_file} d\nd\n")

        runner = CliRunner()
        result = runner.invoke(main, ["-f", str(script)])
        assert result.exit_code == 0
        assert "Loaded" not in result.output

    def test_export_silent_in_script(self, tmp_path: Path) -> None:
        """\\export success messages are suppressed in -f scripts."""
        out_file = tmp_path / "out.csv"

        script = tmp_path / "query.codd"
        script.write_text(f"\\export {out_file} E # name\n")

        runner = CliRunner()
        result = runner.invoke(main, ["--sample", "-f", str(script)])
        assert result.exit_code == 0
        assert "Exported" not in result.output

    def test_assignment_silent_in_script(self, tmp_path: Path) -> None:
        """Assignments produce no output when they are the last line in -f."""
        script = tmp_path / "query.codd"
        script.write_text("X := E ? dept_id = 10\n")

        runner = CliRunner()
        result = runner.invoke(main, ["--sample", "-f", str(script)])
        assert result.exit_code == 0
        assert result.output.strip() == ""

    def test_assignment_silent_in_eval(self) -> None:
        """Assignments produce no output in -e mode."""
        runner = CliRunner()
        result = runner.invoke(
            main, ["--sample", "-e", "X := E ? dept_id = 10"]
        )
        assert result.exit_code == 0
        assert result.output.strip() == ""


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


class TestExportWithEval:
    """Test \\export command used via -e."""

    def test_export_writes_file(self, tmp_path: Path) -> None:
        """\\export via -e writes CSV to the specified path."""
        out_file = tmp_path / "out.csv"
        runner = CliRunner()
        result = runner.invoke(
            main, ["--sample", "-e", f"\\export {out_file} E # name"]
        )
        assert result.exit_code == 0
        assert out_file.exists()
        content = out_file.read_text()
        assert "Alice" in content

    def test_export_reports_row_count(self, tmp_path: Path) -> None:
        """\\export via -e prints an 'Exported N rows' message."""
        out_file = tmp_path / "out.csv"
        runner = CliRunner()
        result = runner.invoke(
            main, ["--sample", "-e", f"\\export {out_file} E # name"]
        )
        assert result.exit_code == 0
        assert "Exported" in result.output
        assert str(out_file) in result.output

    def test_export_bad_expression_reports_error(self, tmp_path: Path) -> None:
        """\\export via -e with invalid expression prints an error."""
        out_file = tmp_path / "out.csv"
        runner = CliRunner()
        result = runner.invoke(
            main, ["--sample", "-e", f"\\export {out_file} NoSuchRelation"]
        )
        assert result.exit_code == 0  # error is printed, not raised
        assert not out_file.exists()


class TestInitFlag:
    """Test --init flag."""

    def test_init_runs_before_eval(self, tmp_path: Path) -> None:
        """--init file runs and binds in the environment before -e expression."""
        init = tmp_path / "setup.codd"
        init.write_text('X := {n; "alice"; "bob"}\n')

        runner = CliRunner()
        result = runner.invoke(main, ["--init", str(init), "-e", "X # n"])
        assert result.exit_code == 0, result.output
        assert "alice" in result.output
        assert "bob" in result.output

    def test_init_runs_before_positional_load(self, tmp_path: Path) -> None:
        """--init defines a relation before positional loads happen."""
        init = tmp_path / "setup.codd"
        init.write_text('Greeting := {g; "hello"}\n')

        csv = tmp_path / "data.csv"
        csv.write_text("n\nworld\n")

        runner = CliRunner()
        result = runner.invoke(
            main, ["--init", str(init), str(csv), "-e", "Greeting # g"]
        )
        assert result.exit_code == 0, result.output
        assert "hello" in result.output

    def test_init_multiple_runs_in_order(self, tmp_path: Path) -> None:
        """Multiple --init flags are run in the order given."""
        a = tmp_path / "a.codd"
        a.write_text('X := {n; "first"}\n')
        b = tmp_path / "b.codd"
        b.write_text("Y := X\n")  # references X defined in a

        runner = CliRunner()
        result = runner.invoke(
            main, ["--init", str(a), "--init", str(b), "-e", "Y # n"]
        )
        assert result.exit_code == 0, result.output
        assert "first" in result.output

    def test_init_error_halts(self, tmp_path: Path) -> None:
        """An error in --init halts before -e runs."""
        init = tmp_path / "bad.codd"
        init.write_text("NoSuch\n")  # unknown relation

        runner = CliRunner()
        result = runner.invoke(
            main, ["--init", str(init), "-e", '"ok"']
        )
        assert result.exit_code != 0
        assert "ok" not in result.output

    def test_init_no_other_args_enters_repl(self, tmp_path: Path) -> None:
        """--init alone (with nothing else) would drop to REPL.

        Smoke test only: CliRunner doesn't drive interactive REPLs well, so
        just verify that --init is accepted without erroring in combination
        with -e.
        """
        init = tmp_path / "setup.codd"
        init.write_text('X := {n; "a"}\n')
        runner = CliRunner()
        result = runner.invoke(
            main, ["--init", str(init), "-e", "X # n"]
        )
        assert result.exit_code == 0


class TestIncludeCommand:
    """Test \\include command."""

    def test_include_in_script(self, tmp_path: Path) -> None:
        """\\include pulls bindings from another file."""
        helpers = tmp_path / "helpers.codd"
        helpers.write_text('Greet := {g; "hi"}\n')

        main_script = tmp_path / "main.codd"
        main_script.write_text(
            f"\\include {helpers}\n"
            "Greet # g\n"
        )

        runner = CliRunner()
        result = runner.invoke(main, ["-f", str(main_script)])
        assert result.exit_code == 0, result.output
        assert "hi" in result.output

    def test_include_relative_to_including_file(self, tmp_path: Path) -> None:
        """\\include uses a bare filename resolved against the including file."""
        helpers = tmp_path / "helpers.codd"
        helpers.write_text('Greet := {g; "hi"}\n')

        main_script = tmp_path / "main.codd"
        main_script.write_text(
            "\\include helpers.codd\n"
            "Greet # g\n"
        )

        runner = CliRunner()
        result = runner.invoke(main, ["-f", str(main_script)])
        assert result.exit_code == 0, result.output
        assert "hi" in result.output

    def test_include_via_init(self, tmp_path: Path) -> None:
        """--init loads a file that \\includes another file."""
        helpers = tmp_path / "helpers.codd"
        helpers.write_text('Money := {v; 100}\n')

        setup = tmp_path / "setup.codd"
        setup.write_text("\\include helpers.codd\n")

        runner = CliRunner()
        result = runner.invoke(
            main, ["--init", str(setup), "-e", "Money # v"]
        )
        assert result.exit_code == 0, result.output
        assert "100" in result.output

    def test_include_cycle_detected(self, tmp_path: Path) -> None:
        """\\include of a file that would re-include the caller errors."""
        a = tmp_path / "a.codd"
        b = tmp_path / "b.codd"
        a.write_text("\\include b.codd\n")
        b.write_text("\\include a.codd\n")

        runner = CliRunner()
        result = runner.invoke(main, ["-f", str(a)])
        assert result.exit_code != 0
        assert "cycle" in result.output.lower()

    def test_include_missing_file_errors(self, tmp_path: Path) -> None:
        """\\include of a nonexistent file produces an error."""
        main_script = tmp_path / "main.codd"
        main_script.write_text("\\include does_not_exist.codd\n")

        runner = CliRunner()
        result = runner.invoke(main, ["-f", str(main_script)])
        assert result.exit_code != 0
        assert "cannot read" in result.output.lower() or \
               "include" in result.output.lower()
