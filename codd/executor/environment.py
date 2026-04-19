"""Environment: stores named relation variables (relvars)."""

from __future__ import annotations

from codd.model.relation import Relation


class Environment:
    """A mutable mapping of relation names to Relation values."""

    def __init__(self) -> None:
        self._bindings: dict[str, Relation] = {}
        # User-defined type aliases: name -> target type string (e.g. "decimal(2)").
        # Separate namespace from relations.
        self._types: dict[str, str] = {}

    def bind(self, name: str, relation: Relation) -> None:
        """Bind a name to a relation."""
        self._bindings[name] = relation

    def lookup(self, name: str) -> Relation:
        """Look up a relation by name."""
        if name not in self._bindings:
            raise KeyError(f"Unknown relation: {name!r}")
        return self._bindings[name]

    def names(self) -> list[str]:
        """Return all bound relation names, sorted."""
        return sorted(self._bindings.keys())

    def unbind(self, name: str) -> None:
        """Remove a relation binding by name.

        Raises KeyError if the name is not bound.
        """
        if name not in self._bindings:
            raise KeyError(f"Unknown relation: {name!r}")
        del self._bindings[name]

    def all_bindings(self) -> dict[str, Relation]:
        """Return a copy of all bindings."""
        return dict(self._bindings)

    def __contains__(self, name: str) -> bool:
        return name in self._bindings

    # --- Type namespace ---

    def bind_type(self, name: str, target_type: str) -> None:
        """Bind a user-defined type alias."""
        self._types[name] = target_type

    def lookup_type(self, name: str) -> str:
        """Look up a user-defined type alias.  Raises KeyError if not defined."""
        if name not in self._types:
            raise KeyError(f"Unknown type: {name!r}")
        return self._types[name]

    def type_names(self) -> list[str]:
        """Return all bound type names, sorted."""
        return sorted(self._types.keys())

    def has_type(self, name: str) -> bool:
        """Check if a type alias is defined."""
        return name in self._types
