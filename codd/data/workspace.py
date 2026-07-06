"""Workspace persistence: save and load .codd workspace files."""

from __future__ import annotations

import datetime
import json
from decimal import Decimal
from pathlib import Path
from typing import Any

from codd.executor.environment import Environment
from codd.model.relation import Relation
from codd.model.types import Tuple_, Value

# Workspace file format version.
# v1: relations only.  v2: adds "types" (UDT aliases) and "functions".
WORKSPACE_VERSION = 2

# Type tag strings used in the serialized format.
_TYPE_STR = "str"
_TYPE_INT = "int"
_TYPE_FLOAT = "float"
_TYPE_BOOL = "bool"
_TYPE_DECIMAL = "Decimal"
_TYPE_RELATION = "Relation"
_TYPE_DATE = "date"


def save_workspace(env: Environment, path: Path) -> None:
    """Serialize the environment (relations, types, functions) to a .codd file.

    Written atomically: to a temp file in the same directory, then renamed.
    """
    relations: dict[str, Any] = {}
    for name in env.names():
        rel = env.lookup(name)
        relations[name] = _serialize_relation(rel)

    types = {name: env.lookup_type(name) for name in env.type_names()}

    functions: dict[str, Any] = {}
    for name in env.function_names():
        fn = env.lookup_function(name)
        functions[name] = {
            "params": list(getattr(fn, "params", ())),
            "body": getattr(fn, "body_source", ""),
        }

    doc = {
        "version": WORKSPACE_VERSION,
        "relations": relations,
        "types": types,
        "functions": functions,
    }
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(doc, indent=2) + "\n")
    tmp.replace(path)


def load_workspace(path: Path) -> "Workspace":
    """Deserialize a .codd workspace file.

    Accepts v1 (relations only) and v2 (relations + types + functions).
    Function bodies are re-parsed from their stored source; a body that
    no longer parses raises ValueError naming the function.
    """
    doc = json.loads(path.read_text())
    _validate_workspace(doc, path)

    relations: dict[str, Relation] = {}
    for name, rel_data in doc["relations"].items():
        relations[name] = _deserialize_relation(rel_data)

    types: dict[str, str] = dict(doc.get("types", {}))

    functions: dict[str, Any] = {}
    for name, spec in doc.get("functions", {}).items():
        functions[name] = _parse_function(
            name, spec.get("params", []), spec.get("body", ""), path
        )

    return Workspace(relations=relations, types=types, functions=functions)


class Workspace:
    """A deserialized workspace: relations, type aliases, functions."""

    def __init__(
        self,
        relations: dict[str, Relation],
        types: dict[str, str],
        functions: dict[str, Any],
    ) -> None:
        self.relations = relations
        self.types = types
        self.functions = functions

    def bind_into(self, env: Environment) -> None:
        """Bind everything in this workspace into *env*."""
        for name, rel in self.relations.items():
            env.bind(name, rel)
        for name, target in self.types.items():
            env.bind_type(name, target)
        for name, fn in self.functions.items():
            env.bind_function(name, fn)


def _parse_function(
    name: str, params: list[str], body: str, path: Path
) -> Any:
    """Re-parse a stored function definition into a FunctionDef node."""
    # Local imports avoid a hard parser dependency at module import time.
    from codd.lexer.lexer import Lexer
    from codd.parser.parser import Parser
    from codd.parser import ast_nodes as ast

    sig = f"{name}({' '.join(params)})" if params else name
    source = f"{sig} := fn {body}"
    try:
        node = Parser(Lexer(source).tokenize()).parse()
    except Exception as e:
        raise ValueError(
            f"Workspace {path}: function {name!r} failed to re-parse: {e}"
        ) from e
    if not isinstance(node, ast.FunctionDef):
        raise ValueError(
            f"Workspace {path}: function {name!r} did not parse to a "
            "function definition"
        )
    return node


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
    if doc.get("version") not in (1, 2):
        raise ValueError(
            f"Unsupported workspace version {doc.get('version')} in {path}"
        )
    if "relations" not in doc or not isinstance(doc["relations"], dict):
        raise ValueError(f"Invalid workspace file (missing relations): {path}")


def _serialize_relation(rel: Relation) -> dict[str, Any]:
    """Serialize a Relation to a JSON-compatible dict."""
    attr_types = _infer_attr_types(rel)
    result: dict[str, Any] = {"attributes": attr_types, "tuples": [_serialize_tuple(t, attr_types) for t in rel]}
    # Persist explicit schema if present.
    if rel._schema is not None:
        result["schema"] = dict(rel._schema)
    return result


def _infer_attr_types(rel: Relation) -> dict[str, str]:
    """Infer the type tag for each attribute by inspecting tuple values.

    Skips empty strings (CSV missing-value sentinels) when sampling,
    since they don't represent the column's real type.
    """
    attr_types: dict[str, str] = {}
    for attr in sorted(rel.attributes):
        attr_types[attr] = _TYPE_STR  # default
        for t in rel:
            val = t[attr]
            if val == "":
                continue  # skip missing values
            attr_types[attr] = _value_type_tag(val)
            break
    return attr_types


def _value_type_tag(value: Value) -> str:
    """Return the type tag string for a value."""
    if isinstance(value, bool):
        return _TYPE_BOOL
    if isinstance(value, int):
        return _TYPE_INT
    if isinstance(value, float):
        return _TYPE_FLOAT
    if isinstance(value, Decimal):
        return _TYPE_DECIMAL
    if isinstance(value, datetime.date):
        return _TYPE_DATE
    if isinstance(value, Relation):
        return _TYPE_RELATION
    return _TYPE_STR


def _serialize_tuple(tup: Tuple_, attr_types: dict[str, str]) -> dict[str, Any]:
    """Serialize a single tuple to a JSON-compatible dict."""
    result: dict[str, Any] = {}
    for attr, type_tag in attr_types.items():
        val = tup[attr]
        if type_tag in (_TYPE_DECIMAL, _TYPE_FLOAT):
            result[attr] = str(val)
        elif type_tag == _TYPE_DATE:
            result[attr] = val.isoformat() if isinstance(val, datetime.date) else str(val)
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

    # Restore explicit schema if saved.
    schema = data.get("schema")
    return Relation(frozenset(tuples), attributes=attributes, schema=schema)


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
    if type_tag == _TYPE_FLOAT:
        return float(val)
    if type_tag == _TYPE_DECIMAL:
        # Empty strings come from CSV columns with missing values.
        if val == "":
            return val
        return Decimal(val)
    if type_tag == _TYPE_BOOL:
        return bool(val)
    if type_tag == _TYPE_DATE:
        return datetime.date.fromisoformat(val)
    if type_tag == _TYPE_RELATION:
        return _deserialize_relation(val)
    return str(val)
