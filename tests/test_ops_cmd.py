"""Tests for --ops output."""

from __future__ import annotations

from click.testing import CliRunner

from codd.cli import main


class TestOpsCmd:
    """Test the --ops flag output."""

    def test_exit_code(self) -> None:
        """Command exits successfully."""
        runner = CliRunner()
        result = runner.invoke(main, ["--ops"])
        assert result.exit_code == 0

    def test_contains_filter(self) -> None:
        """Output includes the filter primitive."""
        runner = CliRunner()
        result = runner.invoke(main, ["--ops"])
        assert "?" in result.output
        assert "Filter" in result.output

    def test_contains_count_aggregate(self) -> None:
        """Output includes the count aggregate."""
        runner = CliRunner()
        result = runner.invoke(main, ["--ops"])
        assert "#." in result.output
        assert "Count" in result.output

    def test_contains_precision(self) -> None:
        """Output includes the precision primitive."""
        runner = CliRunner()
        result = runner.invoke(main, ["--ops"])
        assert "~" in result.output
        assert "Precision" in result.output

    def test_section_headers(self) -> None:
        """Output includes all section headers."""
        runner = CliRunner()
        result = runner.invoke(main, ["--ops"])
        for header in ("Relational", "Aggregates", "Expressions", "Other"):
            assert header in result.output
