"""Tests for the ops CLI subcommand."""

from __future__ import annotations

from click.testing import CliRunner

from codd.cli.ops_cmd import ops_cmd


class TestOpsCmd:
    """Test the ops command output."""

    def test_exit_code(self) -> None:
        """Command exits successfully."""
        runner = CliRunner()
        result = runner.invoke(ops_cmd)
        assert result.exit_code == 0

    def test_contains_filter(self) -> None:
        """Output includes the filter primitive."""
        runner = CliRunner()
        result = runner.invoke(ops_cmd)
        assert "?" in result.output
        assert "Filter" in result.output

    def test_contains_count_aggregate(self) -> None:
        """Output includes the count aggregate."""
        runner = CliRunner()
        result = runner.invoke(ops_cmd)
        assert "#." in result.output
        assert "Count" in result.output

    def test_contains_precision(self) -> None:
        """Output includes the precision primitive."""
        runner = CliRunner()
        result = runner.invoke(ops_cmd)
        assert "~" in result.output
        assert "Precision" in result.output

    def test_section_headers(self) -> None:
        """Output includes all section headers."""
        runner = CliRunner()
        result = runner.invoke(ops_cmd)
        for header in ("Relational", "Aggregates", "Expressions", "Other"):
            assert header in result.output
