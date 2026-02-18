"""Workspace persistence: save and load .codd workspace files."""

from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path
from typing import Any

from prototype.executor.environment import Environment
from prototype.model.relation import Relation
from prototype.model.types import Tuple_, Value

# Workspace file format version.
WORKSPACE_VERSION = 1

# Type tag strings used in the serialized format.
_TYPE_STR = "str"
_TYPE_INT = "int"
_TYPE_BOOL = "bool"
_TYPE_DECIMAL = "Decimal"
_TYPE_RELATION = "Relation"


def save_workspace(env: Environment, path: Path) -> None:
    """Serialize all relations in the environment to a .codd JSON file."""
    relations: dict[str, Any] = {}
    for name in env.names():
        rel = env.lookup(name)
        relations[name] = _serialize_relation(rel)

    doc = {"version": WORKSPACE_VERSION, "relations": relations}
    path.write_text(json.dumps(doc, indent=2) + "\n")


def load_workspace(path: Path) -> dict[str, Relation]:
    """Deserialize a .codd workspace file into a dict of named Relations."""
    doc = json.loads(path.read_text())
    _validate_workspace(doc, path)

    result: dict[str, Relation] = {}
    for name, rel_data in doc["relations"].items():
        result[name] = _deserialize_relation(rel_data)
    return result


def is_workspace_file(path: Path) -> bool:
    """Sniff whether a file is a .codd workspace (JSON with version+relations keys)."""
    try:
        doc = json.loads(path.read_text())
        return (
            isinstance(doc, dict)
            and "version" in doc
            and "relations" in doc
        )
    except (json.JSONDecodeError, UnicodeDecodeError):
        return False


def _validate_workspace(doc: Any, path: Path) -> None:
    """Validate workspace document structure."""
    if not isinstance(doc, dict):
        raise ValueError(f"Invalid workspace file: {path}")
    if doc.get("version") != WORKSPACE_VERSION:
        raise ValueError(
            f"Unsupported workspace version {doc.get('version')} in {path}"
        )
    if "relations" not in doc or not isinstance(doc["relations"], dict):
        raise ValueError(f"Invalid workspace file (missing relations): {path}")


def _serialize_relation(rel: Relation) -> dict[str, Any]:
    """Serialize a Relation to a JSON-compatible dict."""
    attr_types = _infer_attr_types(rel)
    tuples = [_serialize_tuple(t, attr_types) for t in rel]
    return {"attributes": attr_types, "tuples": tuples}


def _infer_attr_types(rel: Relation) -> dict[str, str]:
    """Infer the type tag for each attribute by inspecting tuple values."""
    attr_types: dict[str, str] = {}
    for attr in sorted(rel.attributes):
        attr_types[attr] = _TYPE_STR  # default
        for t in rel:
            val = t[attr]
            attr_types[attr] = _value_type_tag(val)
            break  # one sample is enough; types are uniform within a relation
    return attr_types


def _value_type_tag(value: Value) -> str:
    """Return the type tag string for a value."""
    if isinstance(value, bool):
        return _TYPE_BOOL
    if isinstance(value, int):
        return _TYPE_INT
    if isinstance(value, Decimal):
        return _TYPE_DECIMAL
    if isinstance(value, Relation):
        return _TYPE_RELATION
    return _TYPE_STR


def _serialize_tuple(tup: Tuple_, attr_types: dict[str, str]) -> dict[str, Any]:
    """Serialize a single tuple to a JSON-compatible dict."""
    result: dict[str, Any] = {}
    for attr, type_tag in attr_types.items():
        val = tup[attr]
        if type_tag == _TYPE_DECIMAL:
            result[attr] = str(val)
        elif type_tag == _TYPE_RELATION:
            assert isinstance(val, Relation)
            result[attr] = _serialize_relation(val)
        else:
            result[attr] = val
    return result


def _deserialize_relation(data: dict[str, Any]) -> Relation:
    """Deserialize a relation dict back into a Relation."""
    attr_types: dict[str, str] = data["attributes"]
    raw_tuples: list[dict[str, Any]] = data["tuples"]
    attributes = frozenset(attr_types.keys())

    tuples: set[Tuple_] = set()
    for raw in raw_tuples:
        tuples.add(_deserialize_tuple(raw, attr_types))

    return Relation(frozenset(tuples), attributes=attributes)


def _deserialize_tuple(
    raw: dict[str, Any], attr_types: dict[str, str]
) -> Tuple_:
    """Deserialize a single tuple dict back into a Tuple_."""
    data: dict[str, Value] = {}
    for attr, type_tag in attr_types.items():
        val = raw[attr]
        data[attr] = _deserialize_value(val, type_tag)
    return Tuple_(data)


def _deserialize_value(val: Any, type_tag: str) -> Value:
    """Deserialize a single value given its type tag."""
    if type_tag == _TYPE_INT:
        return int(val)
    if type_tag == _TYPE_DECIMAL:
        return Decimal(val)
    if type_tag == _TYPE_BOOL:
        return bool(val)
    if type_tag == _TYPE_RELATION:
        return _deserialize_relation(val)
    return str(val)
