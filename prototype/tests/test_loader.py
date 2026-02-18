"""Tests for CSV loading and type inference."""

import io
from decimal import Decimal

import pytest

from prototype.data.loader import LoadError, coerce_row, infer_types, load_csv
from prototype.model.relation import Relation


class TestInferTypes:
    """Test type inference from string values."""

    def test_all_ints(self) -> None:
        rows = [{"age": "30", "id": "1"}, {"age": "25", "id": "2"}]
        types = infer_types(rows)
        assert types == {"age": int, "id": int}

    def test_all_decimals(self) -> None:
        rows = [{"score": "3.5"}, {"score": "4.2"}]
        types = infer_types(rows)
        assert types == {"score": Decimal}

    def test_mixed_int_decimal(self) -> None:
        """If some values are int and some are decimal, the column is Decimal."""
        rows = [{"val": "1"}, {"val": "2.5"}]
        types = infer_types(rows)
        assert types == {"val": Decimal}

    def test_all_bool(self) -> None:
        rows = [{"active": "true"}, {"active": "false"}, {"active": "True"}]
        types = infer_types(rows)
        assert types == {"active": bool}

    def test_all_strings(self) -> None:
        rows = [{"name": "Alice"}, {"name": "Bob"}]
        types = infer_types(rows)
        assert types == {"name": str}

    def test_mixed_types_fallback_to_str(self) -> None:
        """If a column has ints and strings, it's str."""
        rows = [{"val": "42"}, {"val": "hello"}]
        types = infer_types(rows)
        assert types == {"val": str}

    def test_empty_values_ignored(self) -> None:
        """Empty strings are ignored during inference."""
        rows = [{"age": "30"}, {"age": ""}, {"age": "25"}]
        types = infer_types(rows)
        assert types == {"age": int}

    def test_all_empty_is_str(self) -> None:
        """A column with only empty values defaults to str."""
        rows = [{"x": ""}, {"x": ""}]
        types = infer_types(rows)
        assert types == {"x": str}

    def test_negative_ints(self) -> None:
        rows = [{"val": "-1"}, {"val": "5"}]
        types = infer_types(rows)
        assert types == {"val": int}

    def test_negative_decimals(self) -> None:
        rows = [{"val": "-1.5"}, {"val": "2.0"}]
        types = infer_types(rows)
        assert types == {"val": Decimal}

    def test_empty_rows(self) -> None:
        types = infer_types([])
        assert types == {}


class TestCoerceRow:
    """Test row coercion."""

    def test_int_coercion(self) -> None:
        result = coerce_row({"age": "30"}, {"age": int})
        assert result == {"age": 30}
        assert isinstance(result["age"], int)

    def test_decimal_coercion(self) -> None:
        result = coerce_row({"score": "3.5"}, {"score": Decimal})
        assert result == {"score": Decimal("3.5")}
        assert isinstance(result["score"], Decimal)

    def test_bool_coercion(self) -> None:
        result = coerce_row({"active": "true"}, {"active": bool})
        assert result == {"active": True}
        assert isinstance(result["active"], bool)

    def test_bool_false(self) -> None:
        result = coerce_row({"active": "false"}, {"active": bool})
        assert result == {"active": False}

    def test_str_passthrough(self) -> None:
        result = coerce_row({"name": "Alice"}, {"name": str})
        assert result == {"name": "Alice"}

    def test_empty_string_preserved(self) -> None:
        """Empty strings stay as empty strings regardless of target type."""
        result = coerce_row({"age": ""}, {"age": int})
        assert result == {"age": ""}


class TestLoadCsv:
    """Test full CSV loading pipeline."""

    def test_basic(self) -> None:
        csv_data = "name,age\nAlice,30\nBob,25\n"
        result = load_csv(io.StringIO(csv_data), "people")
        assert isinstance(result, Relation)
        assert len(result) == 2
        assert result.attributes == frozenset({"name", "age"})
        ages = {t["age"] for t in result}
        assert ages == {30, 25}

    def test_type_inference(self) -> None:
        csv_data = "name,salary,active\nAlice,80000,true\nBob,60000,false\n"
        result = load_csv(io.StringIO(csv_data), "emp")
        for t in result:
            assert isinstance(t["salary"], int)
            assert isinstance(t["active"], bool)
            assert isinstance(t["name"], str)

    def test_decimal_column(self) -> None:
        csv_data = "item,price\nApple,1.50\nBanana,0.75\n"
        result = load_csv(io.StringIO(csv_data), "prices")
        assert len(result) == 2
        for t in result:
            assert isinstance(t["price"], Decimal)

    def test_empty_file(self) -> None:
        result = load_csv(io.StringIO(""), "empty")
        assert isinstance(result, Relation)
        assert len(result) == 0
        assert result.attributes == frozenset()

    def test_headers_only(self) -> None:
        result = load_csv(io.StringIO("name,age\n"), "empty")
        assert isinstance(result, Relation)
        assert len(result) == 0
        assert result.attributes == frozenset({"name", "age"})

    def test_deduplication(self) -> None:
        """Duplicate rows are deduplicated (relational set semantics)."""
        csv_data = "name,age\nAlice,30\nAlice,30\n"
        result = load_csv(io.StringIO(csv_data), "people")
        assert len(result) == 1

    def test_malformed_rows_skipped(self) -> None:
        """Rows with wrong number of columns are skipped."""
        csv_data = "name,age\nAlice,30\nBob\nCarol,25\n"
        result = load_csv(io.StringIO(csv_data), "people")
        assert len(result) == 2
        names = {t["name"] for t in result}
        assert names == {"Alice", "Carol"}

    def test_whitespace_in_headers(self) -> None:
        """Leading/trailing whitespace in headers is stripped."""
        csv_data = " name , age \nAlice,30\n"
        result = load_csv(io.StringIO(csv_data), "people")
        assert result.attributes == frozenset({"name", "age"})

    def test_mixed_int_decimal_column(self) -> None:
        """Column with mix of int and decimal strings becomes Decimal."""
        csv_data = "val\n1\n2.5\n3\n"
        result = load_csv(io.StringIO(csv_data), "data")
        vals = {t["val"] for t in result}
        assert all(isinstance(v, Decimal) for v in vals)


class TestGenkey:
    """Test --genkey: synthetic key column generation."""

    def test_genkey_adds_id_column(self) -> None:
        csv_data = "name,age\nAlice,30\nBob,25\n"
        result = load_csv(io.StringIO(csv_data), "people", genkey="people")
        assert "people_id" in result.attributes
        assert len(result) == 2
        ids = {t["people_id"] for t in result}
        assert ids == {1, 2}

    def test_genkey_custom_name(self) -> None:
        csv_data = "name\nAlice\nBob\n"
        result = load_csv(io.StringIO(csv_data), "data", genkey="item")
        assert "item_id" in result.attributes
        ids = {t["item_id"] for t in result}
        assert ids == {1, 2}

    def test_genkey_preserves_original_data(self) -> None:
        csv_data = "name,age\nAlice,30\nBob,25\n"
        result = load_csv(io.StringIO(csv_data), "people", genkey="people")
        names = {t["name"] for t in result}
        assert names == {"Alice", "Bob"}

    def test_genkey_sequential_integers(self) -> None:
        """Keys are sequential starting at 1, one per CSV row."""
        csv_data = "x\na\nb\nc\nd\n"
        result = load_csv(io.StringIO(csv_data), "data", genkey="data")
        ids = sorted(t["data_id"] for t in result)
        assert ids == [1, 2, 3, 4]

    def test_genkey_prevents_deduplication(self) -> None:
        """Duplicate rows get distinct keys, preventing deduplication."""
        csv_data = "name\nAlice\nAlice\n"
        result = load_csv(io.StringIO(csv_data), "data", genkey="data")
        assert len(result) == 2
        ids = {t["data_id"] for t in result}
        assert ids == {1, 2}

    def test_genkey_column_conflict_raises(self) -> None:
        """Error if generated key column name already exists."""
        csv_data = "data_id,name\n1,Alice\n"
        with pytest.raises(LoadError, match="column already exists"):
            load_csv(io.StringIO(csv_data), "data", genkey="data")

    def test_genkey_empty_data(self) -> None:
        """Genkey with headers-only produces empty relation with key attr."""
        csv_data = "name\n"
        result = load_csv(io.StringIO(csv_data), "data", genkey="data")
        assert len(result) == 0
        assert "data_id" in result.attributes
