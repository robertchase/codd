"""Tests for line continuation."""

from __future__ import annotations

from pathlib import Path

from click.testing import CliRunner

from codd.cli import main
from codd.repl.continuation import join_continuation


class TestJoinContinuation:
    """Unit tests for join_continuation helper."""

    def test_no_continuation(self) -> None:
        assert list(join_continuation(["a", "b", "c"])) == ["a", "b", "c"]

    def test_single_continuation(self) -> None:
        assert list(join_continuation(["a \\", "b"])) == ["a b"]

    def test_multiple_continuations(self) -> None:
        lines = ["a \\", "b \\", "c"]
        assert list(join_continuation(lines)) == ["a b c"]

    def test_trailing_whitespace_after_backslash(self) -> None:
        assert list(join_continuation(["a \\  ", "b"])) == ["a b"]

    def test_mixed_continued_and_plain(self) -> None:
        lines = ["x = 1", "a \\", "b", "y = 2"]
        assert list(join_continuation(lines)) == ["x = 1", "a b", "y = 2"]

    def test_empty_input(self) -> None:
        assert list(join_continuation([])) == []

    def test_unterminated_continuation(self) -> None:
        """Trailing backslash on last line yields accumulated buffer."""
        assert list(join_continuation(["a \\"])) == ["a "]

    def test_backslash_mid_line_not_continuation(self) -> None:
        r"""A backslash not at end of line is not a continuation."""
        assert list(join_continuation(["\\load foo"])) == ["\\load foo"]

    def test_blank_continuation_line(self) -> None:
        """A line that is just backslash joins with empty content."""
        assert list(join_continuation(["\\", "b"])) == ["b"]

    def test_dash_comment_line_skipped(self) -> None:
        """Standalone -- comment lines are dropped."""
        assert list(join_continuation(["-- comment", "a", "b"])) == ["a", "b"]

    def test_dash_comment_inside_continuation_skipped(self) -> None:
        """A -- comment line inside a continuation block is skipped."""
        lines = ["a \\", "-- comment", "b"]
        assert list(join_continuation(lines)) == ["a b"]

    def test_indented_dash_comment_inside_continuation_skipped(self) -> None:
        """An indented -- comment line inside a continuation block is skipped."""
        lines = ["a \\", "    -- comment", "b"]
        assert list(join_continuation(lines)) == ["a b"]


class TestScriptContinuation:
    """Integration tests for continuation in -f script mode."""

    def test_script_continuation(self, tmp_path: Path) -> None:
        """Lines ending with backslash are joined in scripts."""
        script = tmp_path / "query.codd"
        script.write_text("E \\\n  ? role = \"engineer\" \\\n  # name\n")

        runner = CliRunner()
        result = runner.invoke(main, ["--sample", "-f", str(script)])

        assert result.exit_code == 0, result.output
        assert "Alice" in result.output

    def test_script_continuation_with_assignment(self, tmp_path: Path) -> None:
        """Continued assignment followed by a query."""
        script = tmp_path / "query.codd"
        script.write_text(
            "eng := E \\\n  ? role = \"engineer\"\neng # name\n"
        )

        runner = CliRunner()
        result = runner.invoke(main, ["--sample", "-f", str(script)])

        assert result.exit_code == 0
        assert "Alice" in result.output
