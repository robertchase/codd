"""Type coercion for schema enforcement.

Converts values to declared types when applying a schema to a relation.
"""

from __future__ import annotations

import datetime
from decimal import Decimal, InvalidOperation

from codd.model.relation import Relation
from codd.model.types import Tuple_, Value, str_to_date


# Canonical built-in type names.
BUILTIN_TYPES = frozenset({"str", "int", "float", "decimal", "date", "bool"})


class CoercionError(Exception):
    """Raised when a value cannot be coerced to the target type."""


def coerce_value(value: Value, target_type: str) -> Value:
    """Coerce a single value to the target type.

    Raises CoercionError if conversion fails.
    """
    if target_type not in BUILTIN_TYPES:
        raise CoercionError(f"Unknown type: {target_type!r}")

    if target_type == "str":
        return _to_str(value)
    if target_type == "int":
        return _to_int(value)
    if target_type == "float":
        return _to_float(value)
    if target_type == "decimal":
        return _to_decimal(value)
    if target_type == "date":
        return _to_date(value)
    if target_type == "bool":
        return _to_bool(value)
    raise CoercionError(f"Unknown type: {target_type!r}")


def apply_schema(rel: Relation, schema: dict[str, str]) -> Relation:
    """Apply a schema to a relation, coercing column values.

    Columns in the schema are coerced.  Columns not in the schema
    are left unchanged.  Schema columns missing from the relation
    raise CoercionError.
    """
    unknown = frozenset(schema.keys()) - rel.attributes
    if unknown:
        raise CoercionError(
            f"Schema references unknown attributes: {sorted(unknown)}"
        )

    # Merge: explicit schema overrides, existing schema fills gaps.
    merged_schema = dict(rel.schema)
    merged_schema.update(schema)

    result: set[Tuple_] = set()
    for t in rel:
        data = t.data
        for attr, type_name in schema.items():
            try:
                data[attr] = coerce_value(data[attr], type_name)
            except (CoercionError, ValueError, TypeError) as e:
                raise CoercionError(
                    f"Cannot coerce {attr}={data[attr]!r} to {type_name}: {e}"
                ) from e
        result.add(Tuple_(data))

    return Relation(frozenset(result), attributes=rel.attributes,
                    schema=merged_schema)


def extract_schema(rel: Relation) -> Relation:
    """Extract the schema of a relation as a two-column relation {attr, type}."""
    schema = rel.schema
    tuples = frozenset(
        Tuple_({"attr": attr, "type": type_name})
        for attr, type_name in schema.items()
    )
    return Relation(tuples, attributes=frozenset({"attr", "type"}))


def infer_type(value: Value) -> str:
    """Infer the type name for a single value."""
    if isinstance(value, bool):
        return "bool"
    if isinstance(value, int):
        return "int"
    if isinstance(value, float):
        return "float"
    if isinstance(value, Decimal):
        return "decimal"
    if isinstance(value, datetime.date):
        return "date"
    return "str"


def schema_from_relation(rel: Relation) -> dict[str, str]:
    """Build a schema-relation (attr→type) from a relation's {attr, type} tuples."""
    if not ({"attr", "type"} <= rel.attributes):
        raise CoercionError(
            "Schema relation must have 'attr' and 'type' attributes, "
            f"got: {sorted(rel.attributes)}"
        )
    schema: dict[str, str] = {}
    for t in rel:
        attr = str(t["attr"])
        type_name = str(t["type"])
        if type_name not in BUILTIN_TYPES:
            raise CoercionError(f"Unknown type {type_name!r} for attribute {attr!r}")
        schema[attr] = type_name
    return schema


# --- Type conversion helpers ---


def _to_str(value: Value) -> str:
    """Convert any value to string."""
    if isinstance(value, datetime.date):
        return value.isoformat()
    return str(value)


def _to_int(value: Value) -> int:
    """Convert to int."""
    if isinstance(value, bool):
        raise CoercionError(f"Cannot coerce bool to int: {value!r}")
    if isinstance(value, int):
        return value
    if isinstance(value, (float, Decimal)):
        if value != int(value):
            raise CoercionError(f"Cannot coerce {value!r} to int (not whole)")
        return int(value)
    if isinstance(value, str):
        try:
            return int(value)
        except ValueError:
            pass
        # Try float-string like "3.0"
        try:
            f = float(value)
            if f == int(f):
                return int(f)
        except ValueError:
            pass
        raise CoercionError(f"Cannot coerce {value!r} to int")
    raise CoercionError(f"Cannot coerce {type(value).__name__} to int")


def _to_float(value: Value) -> float:
    """Convert to float."""
    if isinstance(value, bool):
        raise CoercionError(f"Cannot coerce bool to float: {value!r}")
    if isinstance(value, float):
        return value
    if isinstance(value, (int, Decimal)):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value)
        except ValueError:
            raise CoercionError(f"Cannot coerce {value!r} to float")
    raise CoercionError(f"Cannot coerce {type(value).__name__} to float")


def _to_decimal(value: Value) -> Decimal:
    """Convert to Decimal."""
    if isinstance(value, bool):
        raise CoercionError(f"Cannot coerce bool to decimal: {value!r}")
    if isinstance(value, Decimal):
        return value
    if isinstance(value, int):
        return Decimal(value)
    if isinstance(value, float):
        return Decimal(str(value))
    if isinstance(value, str):
        try:
            return Decimal(value)
        except InvalidOperation:
            raise CoercionError(f"Cannot coerce {value!r} to decimal")
    raise CoercionError(f"Cannot coerce {type(value).__name__} to decimal")


def _to_date(value: Value) -> datetime.date:
    """Convert to date."""
    if isinstance(value, datetime.date):
        return value
    if isinstance(value, str):
        try:
            return str_to_date(value)
        except ValueError:
            raise CoercionError(f"Cannot coerce {value!r} to date")
    raise CoercionError(f"Cannot coerce {type(value).__name__} to date")


def _to_bool(value: Value) -> bool:
    """Convert to bool."""
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        low = value.lower()
        if low == "true":
            return True
        if low == "false":
            return False
        raise CoercionError(f"Cannot coerce {value!r} to bool")
    raise CoercionError(f"Cannot coerce {type(value).__name__} to bool")
