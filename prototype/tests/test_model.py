"""Tests for the data model: Tuple_ and Relation."""

import pytest

from prototype.model.types import Tuple_
from prototype.model.relation import Relation


# --- Tuple_ tests ---


class TestTuple:
    """Tests for Tuple_ immutability, equality, hashing, and operations."""

    def test_create_from_dict(self) -> None:
        """Create tuple from a dict of attributes."""
        t = Tuple_({"name": "Alice", "age": 30})
        assert t["name"] == "Alice"
        assert t["age"] == 30

    def test_create_from_kwargs(self) -> None:
        """Create tuple from keyword arguments."""
        t = Tuple_(name="Bob", salary=60000)
        assert t["name"] == "Bob"
        assert t["salary"] == 60000

    def test_attributes(self) -> None:
        """attributes() returns frozenset of attribute names."""
        t = Tuple_(name="Alice", salary=80000)
        assert t.attributes() == frozenset({"name", "salary"})

    def test_equality(self) -> None:
        """Tuples with identical attributes are equal."""
        t1 = Tuple_(name="Alice", salary=80000)
        t2 = Tuple_(name="Alice", salary=80000)
        assert t1 == t2

    def test_inequality(self) -> None:
        """Tuples with different values are not equal."""
        t1 = Tuple_(name="Alice", salary=80000)
        t2 = Tuple_(name="Bob", salary=60000)
        assert t1 != t2

    def test_hashable(self) -> None:
        """Equal tuples produce the same hash and deduplicate in sets."""
        t1 = Tuple_(name="Alice", salary=80000)
        t2 = Tuple_(name="Alice", salary=80000)
        assert hash(t1) == hash(t2)
        assert len({t1, t2}) == 1

    def test_immutable(self) -> None:
        """Tuple rejects attribute assignment."""
        t = Tuple_(name="Alice")
        try:
            t.x = 1  # type: ignore[attr-defined]
            assert False, "Should have raised"
        except AttributeError:
            pass

    def test_project(self) -> None:
        """Project keeps only specified attributes."""
        t = Tuple_(name="Alice", salary=80000, dept_id=10)
        p = t.project(frozenset({"name", "salary"}))
        assert p == Tuple_(name="Alice", salary=80000)

    def test_extend(self) -> None:
        """Extend adds new attributes."""
        t = Tuple_(name="Alice", salary=80000)
        e = t.extend({"bonus": 8000})
        assert e["bonus"] == 8000
        assert e["name"] == "Alice"

    def test_rename(self) -> None:
        """Rename maps old attribute names to new ones."""
        t = Tuple_(pay=70000, name="Frank")
        r = t.rename({"pay": "salary"})
        assert r["salary"] == 70000
        assert "pay" not in r

    def test_matches_shared_attrs(self) -> None:
        """Tuples match when shared attributes have equal values."""
        t1 = Tuple_(emp_id=1, name="Alice", dept_id=10)
        t2 = Tuple_(dept_id=10, dept_name="Engineering")
        assert t1.matches(t2)

    def test_matches_no_shared_attrs(self) -> None:
        """Tuples with no shared attributes always match."""
        t1 = Tuple_(name="Alice")
        t2 = Tuple_(dept_name="Engineering")
        assert t1.matches(t2)

    def test_not_matches(self) -> None:
        """Tuples with differing shared attribute values do not match."""
        t1 = Tuple_(dept_id=10)
        t2 = Tuple_(dept_id=20)
        assert not t1.matches(t2)

    def test_merge(self) -> None:
        """Merge combines attributes from both tuples."""
        t1 = Tuple_(emp_id=1, dept_id=10)
        t2 = Tuple_(dept_id=10, dept_name="Engineering")
        m = t1.merge(t2)
        assert m["emp_id"] == 1
        assert m["dept_name"] == "Engineering"
        assert m["dept_id"] == 10

    def test_get(self) -> None:
        """get() retrieves attribute value by name."""
        t = Tuple_(name="Alice")
        assert t.get("name") == "Alice"

    def test_contains(self) -> None:
        """'in' operator checks attribute existence."""
        t = Tuple_(name="Alice", salary=80000)
        assert "name" in t
        assert "dept_id" not in t

    def test_repr(self) -> None:
        """repr includes attribute values."""
        t = Tuple_(name="Alice", salary=80000)
        r = repr(t)
        assert "Alice" in r
        assert "80000" in r


# --- Relation tests ---


class TestRelation:
    """Tests for Relation operations."""

    def _employees(self) -> Relation:
        return Relation(
            frozenset(
                {
                    Tuple_(emp_id=1, name="Alice", salary=80000, dept_id=10, role="engineer"),
                    Tuple_(emp_id=2, name="Bob", salary=60000, dept_id=10, role="manager"),
                    Tuple_(emp_id=3, name="Carol", salary=55000, dept_id=20, role="engineer"),
                    Tuple_(emp_id=4, name="Dave", salary=90000, dept_id=10, role="engineer"),
                    Tuple_(emp_id=5, name="Eve", salary=45000, dept_id=20, role="engineer"),
                }
            )
        )

    def _departments(self) -> Relation:
        return Relation(
            frozenset(
                {
                    Tuple_(dept_id=10, dept_name="Engineering"),
                    Tuple_(dept_id=20, dept_name="Sales"),
                }
            )
        )

    def _phones(self) -> Relation:
        return Relation(
            frozenset(
                {
                    Tuple_(emp_id=1, phone="555-1234"),
                    Tuple_(emp_id=3, phone="555-5678"),
                    Tuple_(emp_id=3, phone="555-9999"),
                }
            )
        )

    def test_create_empty(self) -> None:
        """Empty relation preserves declared attributes."""
        r = Relation(frozenset(), attributes=frozenset({"a", "b"}))
        assert len(r) == 0
        assert r.attributes == frozenset({"a", "b"})

    def test_deduplication(self) -> None:
        """Duplicate tuples are collapsed to one."""
        t = Tuple_(name="Alice")
        r = Relation([t, t, t])
        assert len(r) == 1

    def test_project_single(self) -> None:
        """Project to a single attribute."""
        e = self._employees()
        result = e.project(frozenset({"name"}))
        assert len(result) == 5
        assert result.attributes == frozenset({"name"})
        names = {t["name"] for t in result}
        assert names == {"Alice", "Bob", "Carol", "Dave", "Eve"}

    def test_project_multiple(self) -> None:
        """Project to multiple attributes."""
        e = self._employees()
        result = e.project(frozenset({"name", "salary"}))
        assert result.attributes == frozenset({"name", "salary"})
        assert len(result) == 5

    def test_where(self) -> None:
        """Where filters tuples by predicate."""
        e = self._employees()
        result = e.where(lambda t: t["salary"] > 50000)
        assert len(result) == 4
        names = {t["name"] for t in result}
        assert "Eve" not in names

    def test_chained_where(self) -> None:
        """Chained where narrows results incrementally."""
        e = self._employees()
        result = e.where(lambda t: t["dept_id"] == 10).where(
            lambda t: t["salary"] > 70000
        )
        assert len(result) == 2
        names = {t["name"] for t in result}
        assert names == {"Alice", "Dave"}

    def test_natural_join(self) -> None:
        """Natural join matches on shared attribute dept_id."""
        e = self._employees()
        d = self._departments()
        result = e.natural_join(d)
        assert len(result) == 5
        assert "dept_name" in result.attributes
        for t in result:
            if t["dept_id"] == 10:
                assert t["dept_name"] == "Engineering"
            else:
                assert t["dept_name"] == "Sales"

    def test_nest_join(self) -> None:
        """Nest join produces relation-valued attribute."""
        e = self._employees()
        p = self._phones()
        result = e.nest_join(p, "phones")
        assert len(result) == 5
        assert "phones" in result.attributes
        for t in result:
            phones_rel = t["phones"]
            if t["emp_id"] == 1:
                assert len(phones_rel) == 1
            elif t["emp_id"] == 3:
                assert len(phones_rel) == 2
            else:
                assert len(phones_rel) == 0

    def test_extend(self) -> None:
        """Extend adds computed attribute to each tuple."""
        e = self._employees()
        result = e.extend(lambda t: {"bonus": t["salary"] * 0.1})
        assert "bonus" in result.attributes
        for t in result:
            assert t["bonus"] == t["salary"] * 0.1

    def test_rename(self) -> None:
        """Rename maps attribute names."""
        cp = Relation(frozenset({Tuple_(name="Frank", pay=70000)}))
        result = cp.rename({"pay": "salary"})
        assert "salary" in result.attributes
        assert "pay" not in result.attributes
        for t in result:
            assert t["salary"] == 70000

    def test_union(self) -> None:
        """Union merges two compatible relations."""
        r1 = Relation(frozenset({Tuple_(name="Alice", salary=80000)}))
        r2 = Relation(frozenset({Tuple_(name="Frank", salary=70000)}))
        result = r1.union(r2)
        assert len(result) == 2

    def test_difference(self) -> None:
        """Difference removes matching tuples."""
        e = self._employees()
        p = self._phones()
        e_ids = e.project(frozenset({"emp_id"}))
        p_ids = p.project(frozenset({"emp_id"}))
        result = e_ids.difference(p_ids)
        ids = {t["emp_id"] for t in result}
        assert ids == {2, 4, 5}

    def test_intersect(self) -> None:
        """Intersect keeps only shared tuples."""
        e = self._employees()
        p = self._phones()
        e_ids = e.project(frozenset({"emp_id"}))
        p_ids = p.project(frozenset({"emp_id"}))
        result = e_ids.intersect(p_ids)
        ids = {t["emp_id"] for t in result}
        assert ids == {1, 3}

    def test_union_heading_mismatch(self) -> None:
        """Union rejects mismatched attributes."""
        r1 = Relation(frozenset({Tuple_(a=1)}))
        r2 = Relation(frozenset({Tuple_(b=2)}))
        with pytest.raises(ValueError, match="union requires matching attributes"):
            r1.union(r2)

    def test_difference_heading_mismatch(self) -> None:
        """Difference rejects mismatched attributes."""
        e = self._employees()
        joined = e.natural_join(self._phones())
        with pytest.raises(ValueError, match="difference requires matching attributes"):
            e.difference(joined)

    def test_intersect_heading_mismatch(self) -> None:
        """Intersect rejects mismatched attributes."""
        r1 = Relation(frozenset({Tuple_(a=1)}))
        r2 = Relation(frozenset({Tuple_(a=1, b=2)}))
        with pytest.raises(ValueError, match="intersect requires matching attributes"):
            r1.intersect(r2)

    def test_summarize(self) -> None:
        """Summarize groups by dept_id and aggregates."""
        e = self._employees()
        result = e.summarize(
            frozenset({"dept_id"}),
            {
                "n": lambda r: len(r),
                "total": lambda r: sum(t["salary"] for t in r),
            },
        )
        assert len(result) == 2
        for t in result:
            if t["dept_id"] == 10:
                assert t["n"] == 3
                assert t["total"] == 230000
            else:
                assert t["n"] == 2
                assert t["total"] == 100000

    def test_summarize_all(self) -> None:
        """Summarize-all computes aggregates over entire relation."""
        e = self._employees()
        result = e.summarize_all(
            {
                "n": lambda r: len(r),
                "total": lambda r: sum(t["salary"] for t in r),
            }
        )
        assert len(result) == 1
        t = next(iter(result))
        assert t["n"] == 5
        assert t["total"] == 330000

    def test_nest_by(self) -> None:
        """Nest-by groups tuples into nested relations."""
        e = self._employees()
        result = e.nest_by(frozenset({"dept_id"}), "team")
        assert len(result) == 2
        assert result.attributes == frozenset({"dept_id", "team"})
        for t in result:
            team = t["team"]
            if t["dept_id"] == 10:
                assert len(team) == 3
            else:
                assert len(team) == 2
            # Nested tuples should not contain dept_id
            for member in team:
                assert "dept_id" not in member

    def test_unnest(self) -> None:
        """Unnest flattens relation-valued attribute."""
        e = self._employees()
        p = self._phones()
        nested = e.nest_join(p, "phones")
        result = nested.unnest("phones")
        # Only employees with phones survive: emp_id=1 (1 phone), emp_id=3 (2 phones)
        assert len(result) == 3
        assert "phones" not in result.attributes
        assert "phone" in result.attributes
        emp_ids = {t["emp_id"] for t in result}
        assert emp_ids == {1, 3}

    def test_unnest_empty_rvas_dropped(self) -> None:
        """Unnest drops tuples with empty nested relations."""
        # All RVAs empty -> empty result
        r = Relation(
            frozenset(
                {
                    Tuple_(
                        a=1,
                        nested=Relation(
                            frozenset(), attributes=frozenset({"b"})
                        ),
                    ),
                }
            )
        )
        result = r.unnest("nested")
        assert len(result) == 0

    def test_unnest_multi_nested(self) -> None:
        """Unnest expands multiple nested relations."""
        inner1 = Relation(frozenset({Tuple_(x=10), Tuple_(x=20)}))
        inner2 = Relation(frozenset({Tuple_(x=30)}))
        r = Relation(
            frozenset(
                {
                    Tuple_(a=1, nested=inner1),
                    Tuple_(a=2, nested=inner2),
                }
            )
        )
        result = r.unnest("nested")
        assert len(result) == 3
        vals = {(t["a"], t["x"]) for t in result}
        assert vals == {(1, 10), (1, 20), (2, 30)}

    def test_remove(self) -> None:
        """Remove drops specified attributes, keeps the rest."""
        e = self._employees()
        result = e.remove(frozenset({"salary"}))
        assert "salary" not in result.attributes
        assert result.attributes == frozenset({"emp_id", "name", "dept_id", "role"})
        assert len(result) == 5

    def test_remove_unknown_attribute(self) -> None:
        """Remove rejects unknown attribute names."""
        e = self._employees()
        with pytest.raises(ValueError, match="remove references unknown attributes"):
            e.remove(frozenset({"nonexistent"}))

    def test_sort(self) -> None:
        """Sort orders tuples by key function."""
        e = self._employees()
        projected = e.project(frozenset({"name", "salary"}))
        result = projected.sort(key_fn=lambda t: -t["salary"])
        assert len(result) == 5
        assert result[0]["name"] == "Dave"
        assert result[-1]["name"] == "Eve"

    def test_sort_take(self) -> None:
        """Sort then slice takes top N tuples."""
        e = self._employees()
        projected = e.project(frozenset({"name", "salary"}))
        result = projected.sort(key_fn=lambda t: -t["salary"])[:3]
        assert len(result) == 3
        names = [t["name"] for t in result]
        assert names == ["Dave", "Alice", "Bob"]

    def test_immutable(self) -> None:
        """Relation rejects attribute assignment."""
        r = Relation(frozenset())
        try:
            r.x = 1  # type: ignore[attr-defined]
            assert False, "Should have raised"
        except AttributeError:
            pass

    def test_equality(self) -> None:
        """Relations with same tuples are equal."""
        r1 = Relation(frozenset({Tuple_(a=1)}))
        r2 = Relation(frozenset({Tuple_(a=1)}))
        assert r1 == r2

    def test_hashable(self) -> None:
        """Equal relations produce the same hash."""
        r1 = Relation(frozenset({Tuple_(a=1)}))
        r2 = Relation(frozenset({Tuple_(a=1)}))
        assert hash(r1) == hash(r2)

    def test_project_unknown_attribute(self) -> None:
        """Project rejects unknown attribute names."""
        e = self._employees()
        with pytest.raises(ValueError, match="project references unknown attributes"):
            e.project(frozenset({"nonexistent"}))

    def test_extend_rejects_existing_attribute(self) -> None:
        """Extend rejects overwriting existing attributes."""
        e = self._employees()
        with pytest.raises(
            ValueError, match="extend cannot overwrite existing attributes"
        ):
            e.extend(lambda t: {"name": t["name"].upper()})

    def test_modify_rejects_unknown_attribute(self) -> None:
        """Modify rejects unknown attribute names."""
        e = self._employees()
        with pytest.raises(ValueError, match="modify references unknown attributes"):
            e.modify(lambda t: {"nonexistent": 1})

    def test_rename_unknown_attribute(self) -> None:
        """Rename rejects unknown attribute names."""
        e = self._employees()
        with pytest.raises(ValueError, match="rename references unknown attributes"):
            e.rename({"nonexistent": "something"})

    def test_summarize_unknown_group_attr(self) -> None:
        """Summarize rejects unknown group key attributes."""
        e = self._employees()
        with pytest.raises(
            ValueError, match="summarize group key references unknown attributes"
        ):
            e.summarize(frozenset({"nonexistent"}), {"n": lambda r: len(r)})

    def test_nest_by_unknown_group_attr(self) -> None:
        """Nest-by rejects unknown group key attributes."""
        e = self._employees()
        with pytest.raises(
            ValueError, match="nest_by group key references unknown attributes"
        ):
            e.nest_by(frozenset({"nonexistent"}), "group")
