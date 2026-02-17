"""Tests for the data model: Tuple_ and Relation."""

from prototype.model.types import Tuple_
from prototype.model.relation import Relation


# --- Tuple_ tests ---


class TestTuple:
    """Tests for Tuple_ immutability, equality, hashing, and operations."""

    def test_create_from_dict(self) -> None:
        t = Tuple_({"name": "Alice", "age": 30})
        assert t["name"] == "Alice"
        assert t["age"] == 30

    def test_create_from_kwargs(self) -> None:
        t = Tuple_(name="Bob", salary=60000)
        assert t["name"] == "Bob"
        assert t["salary"] == 60000

    def test_attributes(self) -> None:
        t = Tuple_(name="Alice", salary=80000)
        assert t.attributes() == frozenset({"name", "salary"})

    def test_equality(self) -> None:
        t1 = Tuple_(name="Alice", salary=80000)
        t2 = Tuple_(name="Alice", salary=80000)
        assert t1 == t2

    def test_inequality(self) -> None:
        t1 = Tuple_(name="Alice", salary=80000)
        t2 = Tuple_(name="Bob", salary=60000)
        assert t1 != t2

    def test_hashable(self) -> None:
        t1 = Tuple_(name="Alice", salary=80000)
        t2 = Tuple_(name="Alice", salary=80000)
        assert hash(t1) == hash(t2)
        assert len({t1, t2}) == 1

    def test_immutable(self) -> None:
        t = Tuple_(name="Alice")
        try:
            t.x = 1  # type: ignore[attr-defined]
            assert False, "Should have raised"
        except AttributeError:
            pass

    def test_project(self) -> None:
        t = Tuple_(name="Alice", salary=80000, dept_id=10)
        p = t.project(frozenset({"name", "salary"}))
        assert p == Tuple_(name="Alice", salary=80000)

    def test_extend(self) -> None:
        t = Tuple_(name="Alice", salary=80000)
        e = t.extend({"bonus": 8000})
        assert e["bonus"] == 8000
        assert e["name"] == "Alice"

    def test_rename(self) -> None:
        t = Tuple_(pay=70000, name="Frank")
        r = t.rename({"pay": "salary"})
        assert r["salary"] == 70000
        assert "pay" not in r

    def test_matches_shared_attrs(self) -> None:
        t1 = Tuple_(emp_id=1, name="Alice", dept_id=10)
        t2 = Tuple_(dept_id=10, dept_name="Engineering")
        assert t1.matches(t2)

    def test_matches_no_shared_attrs(self) -> None:
        t1 = Tuple_(name="Alice")
        t2 = Tuple_(dept_name="Engineering")
        assert t1.matches(t2)

    def test_not_matches(self) -> None:
        t1 = Tuple_(dept_id=10)
        t2 = Tuple_(dept_id=20)
        assert not t1.matches(t2)

    def test_merge(self) -> None:
        t1 = Tuple_(emp_id=1, dept_id=10)
        t2 = Tuple_(dept_id=10, dept_name="Engineering")
        m = t1.merge(t2)
        assert m["emp_id"] == 1
        assert m["dept_name"] == "Engineering"
        assert m["dept_id"] == 10

    def test_get(self) -> None:
        t = Tuple_(name="Alice")
        assert t.get("name") == "Alice"

    def test_contains(self) -> None:
        t = Tuple_(name="Alice", salary=80000)
        assert "name" in t
        assert "dept_id" not in t

    def test_repr(self) -> None:
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
        r = Relation(frozenset(), attributes=frozenset({"a", "b"}))
        assert len(r) == 0
        assert r.attributes == frozenset({"a", "b"})

    def test_deduplication(self) -> None:
        t = Tuple_(name="Alice")
        r = Relation([t, t, t])
        assert len(r) == 1

    def test_project_single(self) -> None:
        e = self._employees()
        result = e.project(frozenset({"name"}))
        assert len(result) == 5
        assert result.attributes == frozenset({"name"})
        names = {t["name"] for t in result}
        assert names == {"Alice", "Bob", "Carol", "Dave", "Eve"}

    def test_project_multiple(self) -> None:
        e = self._employees()
        result = e.project(frozenset({"name", "salary"}))
        assert result.attributes == frozenset({"name", "salary"})
        assert len(result) == 5

    def test_where(self) -> None:
        e = self._employees()
        result = e.where(lambda t: t["salary"] > 50000)
        assert len(result) == 4
        names = {t["name"] for t in result}
        assert "Eve" not in names

    def test_chained_where(self) -> None:
        e = self._employees()
        result = e.where(lambda t: t["dept_id"] == 10).where(
            lambda t: t["salary"] > 70000
        )
        assert len(result) == 2
        names = {t["name"] for t in result}
        assert names == {"Alice", "Dave"}

    def test_natural_join(self) -> None:
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
        e = self._employees()
        result = e.extend(lambda t: {"bonus": t["salary"] * 0.1})
        assert "bonus" in result.attributes
        for t in result:
            assert t["bonus"] == t["salary"] * 0.1

    def test_rename(self) -> None:
        cp = Relation(frozenset({Tuple_(name="Frank", pay=70000)}))
        result = cp.rename({"pay": "salary"})
        assert "salary" in result.attributes
        assert "pay" not in result.attributes
        for t in result:
            assert t["salary"] == 70000

    def test_union(self) -> None:
        r1 = Relation(frozenset({Tuple_(name="Alice", salary=80000)}))
        r2 = Relation(frozenset({Tuple_(name="Frank", salary=70000)}))
        result = r1.union(r2)
        assert len(result) == 2

    def test_difference(self) -> None:
        e = self._employees()
        p = self._phones()
        e_ids = e.project(frozenset({"emp_id"}))
        p_ids = p.project(frozenset({"emp_id"}))
        result = e_ids.difference(p_ids)
        ids = {t["emp_id"] for t in result}
        assert ids == {2, 4, 5}

    def test_intersect(self) -> None:
        e = self._employees()
        p = self._phones()
        e_ids = e.project(frozenset({"emp_id"}))
        p_ids = p.project(frozenset({"emp_id"}))
        result = e_ids.intersect(p_ids)
        ids = {t["emp_id"] for t in result}
        assert ids == {1, 3}

    def test_summarize(self) -> None:
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

    def test_sort(self) -> None:
        e = self._employees()
        projected = e.project(frozenset({"name", "salary"}))
        result = projected.sort(key_fn=lambda t: -t["salary"])
        assert len(result) == 5
        assert result[0]["name"] == "Dave"
        assert result[-1]["name"] == "Eve"

    def test_sort_take(self) -> None:
        e = self._employees()
        projected = e.project(frozenset({"name", "salary"}))
        result = projected.sort(key_fn=lambda t: -t["salary"])[:3]
        assert len(result) == 3
        names = [t["name"] for t in result]
        assert names == ["Dave", "Alice", "Bob"]

    def test_immutable(self) -> None:
        r = Relation(frozenset())
        try:
            r.x = 1  # type: ignore[attr-defined]
            assert False, "Should have raised"
        except AttributeError:
            pass

    def test_equality(self) -> None:
        r1 = Relation(frozenset({Tuple_(a=1)}))
        r2 = Relation(frozenset({Tuple_(a=1)}))
        assert r1 == r2

    def test_hashable(self) -> None:
        r1 = Relation(frozenset({Tuple_(a=1)}))
        r2 = Relation(frozenset({Tuple_(a=1)}))
        assert hash(r1) == hash(r2)
