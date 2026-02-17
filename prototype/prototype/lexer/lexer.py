"""Lexer for the relational algebra.

Hand-written with two-character lookahead for digraph operators.
"""

from __future__ import annotations

from prototype.lexer.tokens import Token, TokenType


class LexError(Exception):
    """Raised on invalid input."""

    def __init__(self, message: str, line: int, col: int) -> None:
        super().__init__(f"Lex error at {line}:{col}: {message}")
        self.line = line
        self.col = col


class Lexer:
    """Tokenizes relational algebra source text."""

    def __init__(self, source: str) -> None:
        self._source = source
        self._pos = 0
        self._line = 1
        self._col = 1

    def tokenize(self) -> list[Token]:
        """Tokenize the entire source, returning a list of tokens ending with EOF."""
        tokens: list[Token] = []
        while True:
            tok = self._next_token()
            tokens.append(tok)
            if tok.type == TokenType.EOF:
                break
        return tokens

    def _peek(self, offset: int = 0) -> str:
        """Peek at a character ahead without consuming it."""
        pos = self._pos + offset
        if pos >= len(self._source):
            return ""
        return self._source[pos]

    def _advance(self) -> str:
        """Consume and return the current character."""
        ch = self._source[self._pos]
        self._pos += 1
        if ch == "\n":
            self._line += 1
            self._col = 1
        else:
            self._col += 1
        return ch

    def _skip_whitespace(self) -> None:
        """Skip whitespace and comments."""
        while self._pos < len(self._source):
            ch = self._peek()
            if ch in " \t\r\n":
                self._advance()
            elif ch == "-" and self._peek(1) == "-":
                # Line comment
                while self._pos < len(self._source) and self._peek() != "\n":
                    self._advance()
            else:
                break

    def _make_token(self, ttype: TokenType, value: str, line: int, col: int) -> Token:
        """Create a token with position info."""
        return Token(type=ttype, value=value, line=line, col=col)

    def _next_token(self) -> Token:
        """Produce the next token."""
        self._skip_whitespace()

        if self._pos >= len(self._source):
            return self._make_token(TokenType.EOF, "", self._line, self._col)

        line = self._line
        col = self._col
        ch = self._peek()
        ch2 = self._peek(1)

        # --- Digraph detection (two-char lookahead) ---

        # ?! and ?=
        if ch == "?" and ch2 == "!":
            self._advance()
            self._advance()
            return self._make_token(TokenType.QUESTION_BANG, "?!", line, col)
        if ch == "?" and ch2 == "=":
            self._advance()
            self._advance()
            return self._make_token(TokenType.QUESTION_EQ, "?=", line, col)

        # *:
        if ch == "*" and ch2 == ":":
            self._advance()
            self._advance()
            return self._make_token(TokenType.STAR_COLON, "*:", line, col)

        # /. /: (check before single /)
        if ch == "/" and ch2 == ".":
            self._advance()
            self._advance()
            return self._make_token(TokenType.SLASH_DOT, "/.", line, col)
        if ch == "/" and ch2 == ":":
            self._advance()
            self._advance()
            return self._make_token(TokenType.SLASH_COLON, "/:", line, col)

        # +: +.
        if ch == "+" and ch2 == ":":
            self._advance()
            self._advance()
            return self._make_token(TokenType.PLUS_COLON, "+:", line, col)
        if ch == "+" and ch2 == ".":
            self._advance()
            self._advance()
            return self._make_token(TokenType.PLUS_DOT, "+.", line, col)

        # #.
        if ch == "#" and ch2 == ".":
            self._advance()
            self._advance()
            return self._make_token(TokenType.HASH_DOT, "#.", line, col)

        # >. >= >
        if ch == ">" and ch2 == ".":
            self._advance()
            self._advance()
            return self._make_token(TokenType.GT_DOT, ">.", line, col)
        if ch == ">" and ch2 == "=":
            self._advance()
            self._advance()
            return self._make_token(TokenType.GT_EQ, ">=", line, col)

        # <: <. <= <
        if ch == "<" and ch2 == ":":
            self._advance()
            self._advance()
            return self._make_token(TokenType.LT_COLON, "<:", line, col)
        if ch == "<" and ch2 == ".":
            self._advance()
            self._advance()
            return self._make_token(TokenType.LT_DOT, "<.", line, col)
        if ch == "<" and ch2 == "=":
            self._advance()
            self._advance()
            return self._make_token(TokenType.LT_EQ, "<=", line, col)

        # %.
        if ch == "%" and ch2 == ".":
            self._advance()
            self._advance()
            return self._make_token(TokenType.PERCENT_DOT, "%.", line, col)

        # := (colon + eq)
        if ch == ":" and ch2 == "=":
            self._advance()
            self._advance()
            return self._make_token(TokenType.COLON_EQ, ":=", line, col)
        # ::
        if ch == ":" and ch2 == ":":
            self._advance()
            self._advance()
            return self._make_token(TokenType.COLON_COLON, "::", line, col)

        # |=
        if ch == "|" and ch2 == "=":
            self._advance()
            self._advance()
            return self._make_token(TokenType.PIPE_EQ, "|=", line, col)

        # -=
        if ch == "-" and ch2 == "=":
            self._advance()
            self._advance()
            return self._make_token(TokenType.MINUS_EQ, "-=", line, col)

        # != !~
        if ch == "!" and ch2 == "=":
            self._advance()
            self._advance()
            return self._make_token(TokenType.BANG_EQ, "!=", line, col)
        if ch == "!" and ch2 == "~":
            self._advance()
            self._advance()
            return self._make_token(TokenType.BANG_TILDE, "!~", line, col)

        # --- Single-char operators ---

        single_map: dict[str, TokenType] = {
            "?": TokenType.QUESTION,
            "#": TokenType.HASH,
            "*": TokenType.STAR,
            "@": TokenType.AT,
            "+": TokenType.PLUS,
            "-": TokenType.MINUS,
            "|": TokenType.PIPE,
            "&": TokenType.AMPERSAND,
            "/": TokenType.SLASH,
            "$": TokenType.DOLLAR,
            "^": TokenType.CARET,
            ">": TokenType.GT,
            "<": TokenType.LT,
            "=": TokenType.EQ,
            "~": TokenType.TILDE,
            "(": TokenType.LPAREN,
            ")": TokenType.RPAREN,
            "[": TokenType.LBRACKET,
            "]": TokenType.RBRACKET,
            "{": TokenType.LBRACE,
            "}": TokenType.RBRACE,
            ":": TokenType.COLON,
            ".": TokenType.DOT,
            ",": TokenType.COMMA,
        }

        if ch in single_map:
            self._advance()
            return self._make_token(single_map[ch], ch, line, col)

        # --- String literals ---

        if ch == '"':
            return self._read_string(line, col)

        # --- Number literals ---

        if ch.isdigit():
            return self._read_number(line, col)

        # --- Identifiers and keywords ---

        if ch.isalpha() or ch == "_":
            return self._read_ident(line, col)

        raise LexError(f"Unexpected character: {ch!r}", line, col)

    def _read_string(self, line: int, col: int) -> Token:
        """Read a double-quoted string literal."""
        self._advance()  # consume opening "
        chars: list[str] = []
        while self._pos < len(self._source):
            ch = self._peek()
            if ch == '"':
                self._advance()  # consume closing "
                return self._make_token(TokenType.STRING, "".join(chars), line, col)
            if ch == "\\":
                self._advance()
                esc = self._advance()
                escape_map = {"n": "\n", "t": "\t", "\\": "\\", '"': '"'}
                chars.append(escape_map.get(esc, esc))
            else:
                chars.append(self._advance())
        raise LexError("Unterminated string literal", line, col)

    def _read_number(self, line: int, col: int) -> Token:
        """Read an integer or float literal."""
        start = self._pos
        while self._pos < len(self._source) and self._peek().isdigit():
            self._advance()
        if self._pos < len(self._source) and self._peek() == ".":
            # Check that the next char after . is a digit (not an operator like #.)
            if self._pos + 1 < len(self._source) and self._source[self._pos + 1].isdigit():
                self._advance()  # consume .
                while self._pos < len(self._source) and self._peek().isdigit():
                    self._advance()
                value = self._source[start : self._pos]
                return self._make_token(TokenType.FLOAT, value, line, col)
        value = self._source[start : self._pos]
        return self._make_token(TokenType.INTEGER, value, line, col)

    def _read_ident(self, line: int, col: int) -> Token:
        """Read an identifier or boolean keyword."""
        start = self._pos
        while self._pos < len(self._source) and (
            self._peek().isalnum() or self._peek() == "_"
        ):
            self._advance()
        value = self._source[start : self._pos]
        if value in ("true", "false"):
            return self._make_token(TokenType.BOOLEAN, value, line, col)
        return self._make_token(TokenType.IDENT, value, line, col)
