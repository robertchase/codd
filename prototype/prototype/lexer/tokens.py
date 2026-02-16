"""Token types and Token dataclass for the relational algebra lexer."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum, auto


class TokenType(Enum):
    """All token types in the relational algebra."""

    # Literals
    INTEGER = auto()
    FLOAT = auto()
    STRING = auto()
    BOOLEAN = auto()

    # Identifiers
    IDENT = auto()

    # Single-char operators
    QUESTION = auto()       # ?   filter
    HASH = auto()           # #   project
    STAR = auto()           # *   natural join
    AT = auto()             # @   rename
    PLUS = auto()           # +   extend
    MINUS = auto()          # -   difference / descending sort / negation
    PIPE = auto()           # |   union / OR in filter
    AMPERSAND = auto()      # &   intersect / AND in filter
    SLASH = auto()          # /   summarize
    DOLLAR = auto()         # $   sort
    CARET = auto()          # ^   take
    GT = auto()             # >   greater than / rename arrow / nest name
    LT = auto()             # <   less than
    EQ = auto()             # =   equality

    # Digraph operators
    QUESTION_BANG = auto()  # ?!  negated filter
    STAR_COLON = auto()     # *:  nest join
    SLASH_DOT = auto()      # /.  summarize all
    SLASH_COLON = auto()    # /:  nest by
    PLUS_COLON = auto()     # +:  modify
    HASH_DOT = auto()       # #.  count aggregate
    PLUS_DOT = auto()       # +.  sum aggregate
    GT_DOT = auto()         # >.  max aggregate
    LT_DOT = auto()         # <.  min aggregate
    PERCENT_DOT = auto()    # %.  mean aggregate
    COLON_EQ = auto()       # :=  assign
    PIPE_EQ = auto()        # |=  insert
    MINUS_EQ = auto()       # -=  delete
    QUESTION_EQ = auto()    # ?=  update
    BANG_EQ = auto()        # !=  not equal
    GT_EQ = auto()          # >=  greater or equal
    LT_EQ = auto()          # <=  less or equal
    BANG_TILDE = auto()     # !~  regex non-match
    COLON_COLON = auto()    # ::  type check
    TILDE = auto()          # ~   regex match

    # Delimiters
    LPAREN = auto()         # (
    RPAREN = auto()         # )
    LBRACKET = auto()       # [
    RBRACKET = auto()       # ]
    LBRACE = auto()         # {
    RBRACE = auto()         # }
    COLON = auto()          # :
    DOT = auto()            # .
    COMMA = auto()          # ,

    # Special
    EOF = auto()


@dataclass(frozen=True)
class Token:
    """A lexer token with type, value, and position."""

    type: TokenType
    value: str
    line: int
    col: int

    def __repr__(self) -> str:
        return f"Token({self.type.name}, {self.value!r}, {self.line}:{self.col})"
