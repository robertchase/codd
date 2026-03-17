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
    STAR = auto()           # *   multiply
    AT = auto()             # @   rename
    PLUS = auto()           # +   add
    MINUS = auto()          # -   subtract / descending sort / negation
    PIPE = auto()           # |   OR in filter
    AMPERSAND = auto()      # &   AND in filter
    SLASH = auto()          # /   divide
    DOLLAR = auto()         # $   sort
    DOLLAR_DOT = auto()     # $.  order columns
    CARET = auto()          # ^   take
    GT = auto()             # >   greater than
    LT = auto()             # <   less than
    EQ = auto()             # =   equality

    # Digraph operators
    QUESTION_BANG = auto()  # ?!  negated filter
    QUESTION_COLON = auto() # ?:  ternary
    STAR_DOT = auto()       # *.  natural join
    STAR_COLON = auto()     # *:  nest join
    LT_COLON = auto()       # <:  unnest
    SLASH_DOT = auto()      # /.  summarize
    SLASH_COLON = auto()    # /:  nest by
    PLUS_COLON = auto()     # +:  extend
    EQUALS_COLON = auto()   # =:  modify
    HASH_BANG = auto()      # #!  remove (inverse project)
    HASH_DOT = auto()       # #.  count aggregate
    PLUS_DOT = auto()       # +.  sum aggregate
    GT_DOT = auto()         # >.  max aggregate
    LT_DOT = auto()         # <.  min aggregate
    PERCENT_DOT = auto()    # %.  mean aggregate
    N_DOT = auto()          # n.  collect aggregate
    P_DOT = auto()          # p.  percent aggregate
    COLON_EQ = auto()       # :=  assign
    PIPE_DOT = auto()       # |.  union
    PIPE_EQ = auto()        # |=  insert
    MINUS_DOT = auto()      # -.  difference
    MINUS_EQ = auto()       # -=  delete
    AMPERSAND_DOT = auto()  # &.  intersect
    ARROW = auto()          # ->  rename/alias arrow
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
