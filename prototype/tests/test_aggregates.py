"""Tests for aggregate functions."""

import pytest

from prototype.executor.aggregates import (
    agg_count,
    agg_max,
    agg_mean,
    agg_min,
    agg_sum,
)
from prototype.model.relation import Relation
from prototype.model.types import Tuple_


def _sample() -> Relation:
    return Relation(
        frozenset(
            {
                Tuple_(name="Alice", salary=80000),
                Tuple_(name="Bob", salary=60000),
                Tuple_(name="Carol", salary=55000),
            }
        )
    )


class TestAggCount:
    """Tests for #. (count)."""

    def test_count(self) -> None:
        """#. on 3-tuple relation returns 3."""
        assert agg_count(_sample()) == 3

    def test_empty(self) -> None:
        """#. on empty relation returns 0."""
        empty = Relation(frozenset(), attributes=frozenset({"name"}))
        assert agg_count(empty) == 0


class TestAggSum:
    """Tests for +. (sum)."""

    def test_sum(self) -> None:
        """+. salary -> 195000."""
        assert agg_sum(_sample(), "salary") == 195000

    def test_requires_attr(self) -> None:
        """+. without attr raises ValueError."""
        with pytest.raises(ValueError):
            agg_sum(_sample())


class TestAggMax:
    """Tests for >. (max)."""

    def test_max(self) -> None:
        """>. salary -> 80000."""
        assert agg_max(_sample(), "salary") == 80000

    def test_max_string(self) -> None:
        """>. name -> "Carol" (lexicographic max)."""
        assert agg_max(_sample(), "name") == "Carol"


class TestAggMin:
    """Tests for <. (min)."""

    def test_min(self) -> None:
        """<. salary -> 55000."""
        assert agg_min(_sample(), "salary") == 55000


class TestAggMean:
    """Tests for %. (mean)."""

    def test_mean_returns_float(self) -> None:
        """%. salary -> 65000.0 (always returns float)."""
        assert agg_mean(_sample(), "salary") == 65000.0
        assert isinstance(agg_mean(_sample(), "salary"), float)

    def test_mean_fractional(self) -> None:
        """%. v -> 21.0 (63/3)."""
        r = Relation(
            frozenset(
                {
                    Tuple_(v=10),
                    Tuple_(v=20),
                    Tuple_(v=33),
                }
            )
        )
        assert agg_mean(r, "v") == 21.0
        assert isinstance(agg_mean(r, "v"), float)
