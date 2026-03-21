"""Tests for the type coercion module."""

import datetime
from decimal import Decimal

import pytest

from codd.model.coerce import (
    CoercionError,
    apply_schema,
    coerce_value,
    extract_schema,
    infer_type,
    parse_type_string,
    schema_from_relation,
    validate_schema,
)
from codd.model.relation import Relation
from codd.model.types import Tuple_


class TestCoerceValue:
    """Test individual value coercion."""

    def test_str_to_int(self) -> None:
        """String '42' coerces to int 42."""
        assert coerce_value("42", "int") == 42

    def test_str_to_int_float_string(self) -> None:
        """String '3.0' coerces to int 3."""
        assert coerce_value("3.0", "int") == 3

    def test_str_to_int_fails(self) -> None:
        """Non-numeric string raises CoercionError."""
        with pytest.raises(CoercionError):
            coerce_value("hello", "int")

    def test_str_to_float(self) -> None:
        """String '2.5' coerces to float 2.5."""
        assert coerce_value("2.5", "float") == 2.5

    def test_str_to_decimal(self) -> None:
        """String '1.23' coerces to Decimal('1.23')."""
        assert coerce_value("1.23", "decimal") == Decimal("1.23")

    def test_str_to_date(self) -> None:
        """String '2026-01-15' coerces to date."""
        assert coerce_value("2026-01-15", "date") == datetime.date(2026, 1, 15)

    def test_str_to_bool_true(self) -> None:
        """String 'true' coerces to True."""
        assert coerce_value("true", "bool") is True

    def test_str_to_bool_false(self) -> None:
        """String 'false' coerces to False."""
        assert coerce_value("false", "bool") is False

    def test_str_to_bool_fails(self) -> None:
        """Arbitrary string raises CoercionError for bool."""
        with pytest.raises(CoercionError):
            coerce_value("maybe", "bool")

    def test_int_to_float(self) -> None:
        """Int widens to float."""
        assert coerce_value(5, "float") == 5.0

    def test_int_to_decimal(self) -> None:
        """Int widens to Decimal."""
        assert coerce_value(5, "decimal") == Decimal(5)

    def test_float_to_decimal(self) -> None:
        """Float converts to Decimal via string."""
        assert coerce_value(1.5, "decimal") == Decimal("1.5")

    def test_date_to_str(self) -> None:
        """Date converts to ISO string."""
        assert coerce_value(datetime.date(2026, 3, 20), "str") == "2026-03-20"

    def test_any_to_str(self) -> None:
        """Int converts to string."""
        assert coerce_value(42, "str") == "42"

    def test_bool_to_int_fails(self) -> None:
        """Bool cannot coerce to int."""
        with pytest.raises(CoercionError):
            coerce_value(True, "int")

    def test_unknown_type(self) -> None:
        """Unknown type name raises CoercionError."""
        with pytest.raises(CoercionError):
            coerce_value("x", "unknown")

    def test_float_to_int_whole(self) -> None:
        """Float 3.0 coerces to int 3."""
        assert coerce_value(3.0, "int") == 3

    def test_float_to_int_not_whole(self) -> None:
        """Float 3.5 cannot coerce to int."""
        with pytest.raises(CoercionError):
            coerce_value(3.5, "int")


class TestApplySchema:
    """Test applying a schema to a relation."""

    def test_basic(self) -> None:
        """Apply schema coerces specified columns."""
        rel = Relation(
            frozenset({
                Tuple_(name="Alice", age="30"),
                Tuple_(name="Bob", age="25"),
            })
        )
        result = apply_schema(rel, {"age": "int"})
        for t in result:
            assert isinstance(t["age"], int)

    def test_preserves_unmentioned_columns(self) -> None:
        """Columns not in schema are left unchanged."""
        rel = Relation(frozenset({Tuple_(name="Alice", age="30")}))
        result = apply_schema(rel, {"age": "int"})
        for t in result:
            assert isinstance(t["name"], str)

    def test_unknown_attr_error(self) -> None:
        """Schema referencing unknown attribute raises CoercionError."""
        rel = Relation(frozenset({Tuple_(a="1")}))
        with pytest.raises(CoercionError):
            apply_schema(rel, {"nonexistent": "int"})

    def test_merged_schema(self) -> None:
        """Applied schema merges with existing defaults."""
        rel = Relation(frozenset({Tuple_(a="1", b="hello")}))
        result = apply_schema(rel, {"a": "int"})
        schema = result.schema
        assert schema["a"] == "int"
        assert schema["b"] == "str"


class TestExtractSchema:
    """Test extracting schema from a relation."""

    def test_default_schema(self) -> None:
        """Untyped relation has all-str schema."""
        rel = Relation(frozenset({Tuple_(x="1", y="2")}))
        result = extract_schema(rel)
        assert result.attributes == frozenset({"attr", "type"})
        schema = {t["attr"]: t["type"] for t in result}
        assert schema == {"x": "str", "y": "str"}

    def test_typed_schema(self) -> None:
        """Relation with explicit schema extracts correctly."""
        rel = Relation(
            frozenset({Tuple_(a=1, b="hello")}),
            schema={"a": "int", "b": "str"},
        )
        result = extract_schema(rel)
        schema = {t["attr"]: t["type"] for t in result}
        assert schema == {"a": "int", "b": "str"}


class TestSchemaFromRelation:
    """Test building schema dict from a schema relation."""

    def test_basic(self) -> None:
        """Build schema from {attr, type} relation."""
        schema_rel = Relation(
            frozenset({
                Tuple_(attr="name", type="str"),
                Tuple_(attr="age", type="int"),
            })
        )
        result = schema_from_relation(schema_rel)
        assert result == {"name": "str", "age": "int"}

    def test_missing_columns_error(self) -> None:
        """Relation without attr/type columns raises CoercionError."""
        rel = Relation(frozenset({Tuple_(x="1")}))
        with pytest.raises(CoercionError):
            schema_from_relation(rel)

    def test_unknown_type_error(self) -> None:
        """Unknown type in schema relation raises CoercionError."""
        schema_rel = Relation(
            frozenset({Tuple_(attr="x", type="vector")})
        )
        with pytest.raises(CoercionError):
            schema_from_relation(schema_rel)


class TestInferType:
    """Test type inference for values."""

    def test_bool(self) -> None:
        """Bool inferred before int."""
        assert infer_type(True) == "bool"

    def test_int(self) -> None:
        """Integer type inferred."""
        assert infer_type(42) == "int"

    def test_float(self) -> None:
        """Float type inferred."""
        assert infer_type(3.14) == "float"

    def test_decimal(self) -> None:
        """Decimal type inferred."""
        assert infer_type(Decimal("1.5")) == "decimal"

    def test_date(self) -> None:
        """Date type inferred."""
        assert infer_type(datetime.date(2026, 1, 1)) == "date"

    def test_str(self) -> None:
        """String is the fallback type."""
        assert infer_type("hello") == "str"


class TestParseTypeString:
    """Test parsing type strings."""

    def test_builtin(self) -> None:
        """Built-in type returns (type, None)."""
        assert parse_type_string("int") == ("int", None)

    def test_in_constraint(self) -> None:
        """in(R, a) returns ('in', ('R', 'a'))."""
        assert parse_type_string("in(Status, name)") == ("in", ("Status", "name"))

    def test_in_with_spaces(self) -> None:
        """in() with whitespace is accepted."""
        assert parse_type_string("in( Status , name )") == ("in", ("Status", "name"))

    def test_unknown_type(self) -> None:
        """Unknown type raises CoercionError."""
        with pytest.raises(CoercionError):
            parse_type_string("vector")


class TestInConstraint:
    """Test in(Relation, attr) constraint in apply_schema."""

    def _make_env(self):
        """Create a mock environment with a Status relation."""
        from codd.executor.environment import Environment

        env = Environment()
        env.bind(
            "Status",
            Relation(
                frozenset({
                    Tuple_(name="open", desc="Open"),
                    Tuple_(name="closed", desc="Closed"),
                    Tuple_(name="pending", desc="Pending"),
                })
            ),
        )
        return env

    def test_valid_values_pass(self) -> None:
        """Values in the referenced relation pass validation."""
        env = self._make_env()
        rel = Relation(
            frozenset({
                Tuple_(id="1", status="open"),
                Tuple_(id="2", status="closed"),
            })
        )
        result = apply_schema(rel, {"status": "in(Status, name)"}, env=env)
        assert len(result) == 2
        assert result.schema["status"] == "in(Status, name)"

    def test_invalid_value_fails(self) -> None:
        """Value not in referenced relation raises CoercionError."""
        env = self._make_env()
        rel = Relation(
            frozenset({Tuple_(id="1", status="invalid")})
        )
        with pytest.raises(CoercionError, match="not in Status.name"):
            apply_schema(rel, {"status": "in(Status, name)"}, env=env)

    def test_coerces_to_ref_type(self) -> None:
        """Values are coerced to the referenced column's type."""
        from codd.executor.environment import Environment

        env = Environment()
        env.bind(
            "Codes",
            Relation(
                frozenset({
                    Tuple_(code=1),
                    Tuple_(code=2),
                }),
                schema={"code": "int"},
            ),
        )
        rel = Relation(frozenset({Tuple_(x="hello", code="1")}))
        result = apply_schema(rel, {"code": "in(Codes, code)"}, env=env)
        for t in result:
            assert isinstance(t["code"], int)
            assert t["code"] == 1

    def test_unknown_relation_error(self) -> None:
        """Reference to nonexistent relation raises CoercionError."""
        from codd.executor.environment import Environment

        env = Environment()
        rel = Relation(frozenset({Tuple_(a="x")}))
        with pytest.raises(CoercionError, match="Unknown relation"):
            apply_schema(rel, {"a": "in(Nope, col)"}, env=env)

    def test_unknown_attr_in_ref_error(self) -> None:
        """Reference to nonexistent attr in relation raises CoercionError."""
        env = self._make_env()
        rel = Relation(frozenset({Tuple_(a="x")}))
        with pytest.raises(CoercionError, match="not in Status"):
            apply_schema(rel, {"a": "in(Status, nope)"}, env=env)

    def test_no_env_error(self) -> None:
        """in() constraint without env raises CoercionError."""
        rel = Relation(frozenset({Tuple_(a="x")}))
        with pytest.raises(CoercionError, match="no environment"):
            apply_schema(rel, {"a": "in(Status, name)"})

    def test_schema_from_relation_accepts_in(self) -> None:
        """schema_from_relation accepts in() type strings."""
        schema_rel = Relation(
            frozenset({Tuple_(attr="status", type="in(Status, name)")})
        )
        result = schema_from_relation(schema_rel)
        assert result == {"status": "in(Status, name)"}


class TestValidateSchema:
    """Test post-operation schema validation."""

    def test_valid_builtin_passes(self) -> None:
        """Relation with correct types passes validation."""
        rel = Relation(
            frozenset({Tuple_(a=1, b="hello")}),
            schema={"a": "int", "b": "str"},
        )
        validate_schema(rel)  # should not raise

    def test_wrong_type_fails(self) -> None:
        """Relation with wrong value type fails validation."""
        rel = Relation(
            frozenset({Tuple_(a="not_int")}),
            schema={"a": "int"},
        )
        with pytest.raises(CoercionError, match="is not int"):
            validate_schema(rel)

    def test_no_schema_skips(self) -> None:
        """Relation without schema skips validation."""
        rel = Relation(frozenset({Tuple_(a="anything")}))
        validate_schema(rel)  # should not raise

    def test_attrs_filter(self) -> None:
        """Only specified attrs are checked."""
        rel = Relation(
            frozenset({Tuple_(a="not_int", b="hello")}),
            schema={"a": "int", "b": "str"},
        )
        # Checking only b should pass
        validate_schema(rel, attrs=frozenset({"b"}))
        # Checking a should fail
        with pytest.raises(CoercionError):
            validate_schema(rel, attrs=frozenset({"a"}))

    def test_in_constraint_validation(self) -> None:
        """in() constraint is validated post-operation."""
        from codd.executor.environment import Environment

        env = Environment()
        env.bind(
            "Status",
            Relation(frozenset({Tuple_(name="open"), Tuple_(name="closed")})),
        )
        rel = Relation(
            frozenset({Tuple_(status="invalid")}),
            schema={"status": "in(Status, name)"},
        )
        with pytest.raises(CoercionError, match="not in Status.name"):
            validate_schema(rel, env=env)
