"""Type coercion for schema enforcement.

Converts values to declared types when applying a schema to a relation.
Supports built-in types and referential constraints via ``in(Relation, attr)``.
"""

from __future__ import annotations

import datetime
import re
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

from codd.model.relation import Relation
from codd.model.types import Tuple_, Value, str_to_date


# Canonical built-in type names.
BUILTIN_TYPES = frozenset({"str", "int", "float", "decimal", "date", "bool"})

# Pattern for in(Relation, attr) constraint strings.
_IN_PATTERN = re.compile(r"^in\(\s*(\w+)\s*,\s*(\w+)\s*\)$")

# Pattern for decimal(N) precision strings.
_DECIMAL_PATTERN = re.compile(r"^decimal\(\s*(\d+)\s*\)$")


class CoercionError(Exception):
    """Raised when a value cannot be coerced to the target type."""


def parse_type_string(type_str: str) -> tuple[str, tuple[str, str] | None]:
    """Parse a type string into (base_type, constraint_info).

    Returns:
        (base_type, None) for built-in types like ``"int"``.
        ("in", (relation_name, attr_name)) for ``"in(R, a)"``.
        ("decimal", ("precision", N_str)) for ``"decimal(N)"``.
        The base_type for ``in()`` constraints is resolved later from
        the referenced relation's schema.
    """
    m = _IN_PATTERN.match(type_str)
    if m:
        return ("in", (m.group(1), m.group(2)))
    m = _DECIMAL_PATTERN.match(type_str)
    if m:
        return ("decimal", ("precision", m.group(1)))
    if type_str in BUILTIN_TYPES:
        return (type_str, None)
    raise CoercionError(f"Unknown type: {type_str!r}")


def resolve_type_alias(type_str: str, env: object | None = None) -> str:
    """Walk user-defined type aliases to a canonical type string.

    If *type_str* is already a built-in or a known pattern (decimal(N),
    in(R, a)), returns it unchanged.  If it's a UDT name defined in *env*,
    follows the alias chain (with cycle detection) until reaching a
    non-alias.  If not a known type and not in *env*, returns it unchanged
    so that downstream ``parse_type_string`` raises a clear error.
    """
    if env is None or not hasattr(env, "has_type"):
        return type_str

    seen: set[str] = set()
    current = type_str
    while True:
        # Patterns and built-ins terminate the walk.
        if _IN_PATTERN.match(current) or _DECIMAL_PATTERN.match(current):
            return current
        if current in BUILTIN_TYPES:
            return current
        # Try UDT lookup.
        if not env.has_type(current):
            return current  # unknown; let parse_type_string handle it
        if current in seen:
            raise CoercionError(f"type alias cycle: {current}")
        seen.add(current)
        current = env.lookup_type(current)


def coerce_value(value: Value, target_type: str, precision: int | None = None) -> Value:
    """Coerce a single value to a built-in target type.

    For ``decimal`` types, *precision* specifies the number of decimal
    places to quantize to (e.g. 2 → ``0.01``).  Uses ROUND_HALF_UP.

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
        return _to_decimal(value, precision=precision)
    if target_type == "date":
        return _to_date(value)
    if target_type == "bool":
        return _to_bool(value)
    raise CoercionError(f"Unknown type: {target_type!r}")


def apply_schema(
    rel: Relation,
    schema: dict[str, str],
    env: object | None = None,
) -> Relation:
    """Apply a schema to a relation, coercing column values.

    Columns in the schema are coerced.  Columns not in the schema
    are left unchanged.  Schema columns missing from the relation
    raise CoercionError.

    For ``in(Relation, attr)`` constraints, *env* must be provided
    (an object with a ``lookup(name)`` method returning a Relation).
    """
    unknown = frozenset(schema.keys()) - rel.attributes
    if unknown:
        raise CoercionError(
            f"Schema references unknown attributes: {sorted(unknown)}"
        )

    # Resolve UDT aliases to canonical type strings.
    schema = {attr: resolve_type_alias(t, env) for attr, t in schema.items()}

    # Resolve types: find base type, precision, and in() constraint values.
    resolved: dict[str, tuple[str, int | None]] = {}  # attr → (base_type, precision)
    in_constraints: dict[str, tuple[str, str, frozenset]] = {}  # attr → (rel, col, values)
    for attr, type_str in schema.items():
        base_type, constraint = parse_type_string(type_str)
        if base_type == "in" and constraint is not None:
            ref_rel_name, ref_attr = constraint
            if env is None:
                raise CoercionError(
                    f"Cannot resolve in({ref_rel_name}, {ref_attr}): "
                    "no environment available"
                )
            try:
                ref_rel = env.lookup(ref_rel_name)
            except KeyError:
                raise CoercionError(
                    f"Unknown relation {ref_rel_name!r} in "
                    f"in({ref_rel_name}, {ref_attr})"
                )
            if ref_attr not in ref_rel.attributes:
                raise CoercionError(
                    f"Attribute {ref_attr!r} not in {ref_rel_name}"
                )
            # Determine base type from referenced relation's schema.
            ref_schema = ref_rel.schema
            ref_type = ref_schema.get(ref_attr, "str")
            # If the referenced column itself is an in() constraint, use its
            # base type for coercion (don't cascade the constraint resolution).
            ref_base, _ = parse_type_string(ref_type)
            if ref_base == "in":
                ref_type = "str"
            resolved[attr] = (ref_type, None)
            valid_values = frozenset(t[ref_attr] for t in ref_rel)
            in_constraints[attr] = (ref_rel_name, ref_attr, valid_values)
        elif base_type == "decimal" and constraint is not None:
            # decimal(N) — constraint holds ("precision", N_str)
            prec = int(constraint[1])
            resolved[attr] = ("decimal", prec)
        else:
            resolved[attr] = (base_type, None)

    # Merge: explicit schema overrides, existing schema fills gaps.
    merged_schema = dict(rel.schema)
    merged_schema.update(schema)  # keep original type strings (e.g. "in(...)")

    result: set[Tuple_] = set()
    for t in rel:
        data = t.data
        for attr, (base_type, precision) in resolved.items():
            try:
                data[attr] = coerce_value(data[attr], base_type, precision=precision)
            except (CoercionError, ValueError, TypeError) as e:
                raise CoercionError(
                    f"Cannot coerce {attr}={data[attr]!r} to {base_type}: {e}"
                ) from e
            # Check in() membership after coercion.
            if attr in in_constraints:
                ref_rel_name, ref_attr, valid = in_constraints[attr]
                if data[attr] not in valid:
                    raise CoercionError(
                        f"value {data[attr]!r} not in "
                        f"{ref_rel_name}.{ref_attr}"
                    )
        result.add(Tuple_(data))

    return Relation(frozenset(result), attributes=rel.attributes,
                    schema=merged_schema)


def validate_schema(
    rel: Relation,
    env: object | None = None,
    attrs: frozenset[str] | None = None,
) -> None:
    """Validate that a relation's values conform to its schema.

    If *attrs* is given, only those attributes are checked (used after
    extend/modify to check only the changed columns).  Otherwise all
    schema-typed columns are checked.

    Raises CoercionError on the first violation.
    """
    schema_dict = rel.schema
    if not rel._schema:
        return  # no explicit schema, nothing to enforce

    check_attrs = attrs if attrs is not None else frozenset(schema_dict.keys())

    for attr in check_attrs:
        type_str = schema_dict.get(attr)
        if type_str is None or type_str == "str":
            continue  # str is the untyped default — no enforcement
        base_type, constraint = parse_type_string(type_str)
        # decimal(N) — base check is just Decimal isinstance.
        if base_type == "decimal" and constraint is not None:
            # Precision was applied at coercion time; just check it's a Decimal.
            for t in rel:
                val = t[attr]
                if not isinstance(val, Decimal):
                    raise CoercionError(f"{attr}={val!r} is not decimal")
            continue
        # Resolve in() constraint values.
        valid_values: frozenset | None = None
        if constraint is not None:
            ref_rel_name, ref_attr = constraint
            if env is None:
                raise CoercionError(
                    f"Cannot resolve in({ref_rel_name}, {ref_attr}): "
                    "no environment available"
                )
            try:
                ref_rel = env.lookup(ref_rel_name)
            except KeyError:
                raise CoercionError(
                    f"Unknown relation {ref_rel_name!r} in "
                    f"in({ref_rel_name}, {ref_attr})"
                )
            valid_values = frozenset(t[ref_attr] for t in ref_rel)
            # Use referenced column's base type.
            ref_type = ref_rel.schema.get(ref_attr, "str")
            ref_base, _ = parse_type_string(ref_type)
            base_type = ref_type if ref_base != "in" else "str"

        for t in rel:
            val = t[attr]
            # Type check.
            if base_type != "in":
                expected_python = _EXPECTED_TYPES.get(base_type)
                if expected_python and not isinstance(val, expected_python):
                    raise CoercionError(
                        f"{attr}={val!r} is not {base_type}"
                    )
            # Membership check.
            if valid_values is not None and val not in valid_values:
                ref_rel_name, ref_attr = constraint  # type: ignore[misc]
                raise CoercionError(
                    f"value {val!r} not in {ref_rel_name}.{ref_attr}"
                )


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


def schema_from_relation(
    rel: Relation, env: object | None = None
) -> dict[str, str]:
    """Build a schema dict (attr→type) from a relation's {attr, type} tuples.

    Accepts built-in type names, ``in(Relation, attr)`` constraints, and
    user-defined type aliases defined in *env*.  UDT names are kept as-is
    here and resolved later (in apply_schema) so the original intent is
    preserved until coercion.
    """
    if not ({"attr", "type"} <= rel.attributes):
        raise CoercionError(
            "Schema relation must have 'attr' and 'type' attributes, "
            f"got: {sorted(rel.attributes)}"
        )
    schema: dict[str, str] = {}
    for t in rel:
        attr = str(t["attr"])
        type_name = str(t["type"])
        # Validate: must be a built-in, known pattern, or defined UDT.
        try:
            parse_type_string(type_name)
        except CoercionError:
            if env is not None and hasattr(env, "has_type") \
                    and env.has_type(type_name):
                pass  # it's a UDT; accept and resolve at apply time
            else:
                raise CoercionError(
                    f"Unknown type {type_name!r} for attribute {attr!r}"
                )
        schema[attr] = type_name
    return schema


# Map from type name to expected Python types (for validate_schema checks).
_EXPECTED_TYPES: dict[str, tuple[type, ...]] = {
    "str": (str,),
    "int": (int,),
    "float": (float,),
    "decimal": (Decimal,),
    "date": (datetime.date,),
    "bool": (bool,),
}


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


def _to_decimal(value: Value, precision: int | None = None) -> Decimal:
    """Convert to Decimal, optionally quantizing to *precision* places.

    Uses ROUND_HALF_UP when precision is specified.
    """
    if isinstance(value, bool):
        raise CoercionError(f"Cannot coerce bool to decimal: {value!r}")
    if isinstance(value, Decimal):
        result = value
    elif isinstance(value, int):
        result = Decimal(value)
    elif isinstance(value, float):
        result = Decimal(str(value))
    elif isinstance(value, str):
        try:
            result = Decimal(value)
        except InvalidOperation:
            raise CoercionError(f"Cannot coerce {value!r} to decimal")
    else:
        raise CoercionError(f"Cannot coerce {type(value).__name__} to decimal")

    if precision is not None:
        quantizer = Decimal(10) ** -precision
        result = result.quantize(quantizer, rounding=ROUND_HALF_UP)
    return result


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
