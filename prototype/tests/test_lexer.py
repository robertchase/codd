"""Tests for the lexer."""

import pytest

from prototype.lexer.lexer import Lexer, LexError
from prototype.lexer.tokens import TokenType


def types(source: str) -> list[TokenType]:
    """Helper: return token types (excluding EOF)."""
    tokens = Lexer(source).tokenize()
    return [t.type for t in tokens if t.type != TokenType.EOF]


def values(source: str) -> list[str]:
    """Helper: return token values (excluding EOF)."""
    tokens = Lexer(source).tokenize()
    return [t.value for t in tokens if t.type != TokenType.EOF]


class TestSingleCharOperators:
    """Test single-character operator tokens."""

    def test_all_singles(self) -> None:
        src = "? # * @ + - | & / $ ^ > < = ~ ( ) [ ] { } : ."
        result = types(src)
        expected = [
            TokenType.QUESTION, TokenType.HASH, TokenType.STAR, TokenType.AT,
            TokenType.PLUS, TokenType.MINUS, TokenType.PIPE, TokenType.AMPERSAND,
            TokenType.SLASH, TokenType.DOLLAR, TokenType.CARET, TokenType.GT,
            TokenType.LT, TokenType.EQ, TokenType.TILDE, TokenType.LPAREN,
            TokenType.RPAREN, TokenType.LBRACKET, TokenType.RBRACKET,
            TokenType.LBRACE, TokenType.RBRACE, TokenType.COLON, TokenType.DOT,
        ]
        assert result == expected


class TestDigraphOperators:
    """Test two-character operator tokens."""

    def test_question_bang(self) -> None:
        assert types("?!") == [TokenType.QUESTION_BANG]

    def test_star_colon(self) -> None:
        assert types("*:") == [TokenType.STAR_COLON]

    def test_slash_dot(self) -> None:
        assert types("/.") == [TokenType.SLASH_DOT]

    def test_slash_colon(self) -> None:
        assert types("/:") == [TokenType.SLASH_COLON]

    def test_plus_colon(self) -> None:
        assert types("+:") == [TokenType.PLUS_COLON]

    def test_hash_dot(self) -> None:
        assert types("#.") == [TokenType.HASH_DOT]

    def test_plus_dot(self) -> None:
        assert types("+.") == [TokenType.PLUS_DOT]

    def test_gt_dot(self) -> None:
        assert types(">.") == [TokenType.GT_DOT]

    def test_lt_dot(self) -> None:
        assert types("<.") == [TokenType.LT_DOT]

    def test_percent_dot(self) -> None:
        assert types("%.") == [TokenType.PERCENT_DOT]

    def test_colon_eq(self) -> None:
        assert types(":=") == [TokenType.COLON_EQ]

    def test_pipe_eq(self) -> None:
        assert types("|=") == [TokenType.PIPE_EQ]

    def test_minus_eq(self) -> None:
        assert types("-=") == [TokenType.MINUS_EQ]

    def test_question_eq(self) -> None:
        assert types("?=") == [TokenType.QUESTION_EQ]

    def test_bang_eq(self) -> None:
        assert types("!=") == [TokenType.BANG_EQ]

    def test_gt_eq(self) -> None:
        assert types(">=") == [TokenType.GT_EQ]

    def test_lt_eq(self) -> None:
        assert types("<=") == [TokenType.LT_EQ]

    def test_bang_tilde(self) -> None:
        assert types("!~") == [TokenType.BANG_TILDE]

    def test_colon_colon(self) -> None:
        assert types("::") == [TokenType.COLON_COLON]


class TestLiterals:
    """Test literal tokens."""

    def test_integer(self) -> None:
        toks = Lexer("42").tokenize()
        assert toks[0].type == TokenType.INTEGER
        assert toks[0].value == "42"

    def test_float(self) -> None:
        toks = Lexer("3.14").tokenize()
        assert toks[0].type == TokenType.FLOAT
        assert toks[0].value == "3.14"

    def test_string(self) -> None:
        toks = Lexer('"hello world"').tokenize()
        assert toks[0].type == TokenType.STRING
        assert toks[0].value == "hello world"

    def test_string_escape(self) -> None:
        toks = Lexer(r'"say \"hi\""').tokenize()
        assert toks[0].value == 'say "hi"'

    def test_boolean_true(self) -> None:
        toks = Lexer("true").tokenize()
        assert toks[0].type == TokenType.BOOLEAN
        assert toks[0].value == "true"

    def test_boolean_false(self) -> None:
        toks = Lexer("false").tokenize()
        assert toks[0].type == TokenType.BOOLEAN
        assert toks[0].value == "false"


class TestIdentifiers:
    """Test identifier tokens."""

    def test_simple(self) -> None:
        toks = Lexer("Employee").tokenize()
        assert toks[0].type == TokenType.IDENT
        assert toks[0].value == "Employee"

    def test_underscore(self) -> None:
        toks = Lexer("dept_id").tokenize()
        assert toks[0].type == TokenType.IDENT
        assert toks[0].value == "dept_id"

    def test_alphanumeric(self) -> None:
        toks = Lexer("table2").tokenize()
        assert toks[0].type == TokenType.IDENT
        assert toks[0].value == "table2"


class TestComplexExpressions:
    """Test tokenizing full expressions."""

    def test_filter_project(self) -> None:
        src = 'E ? salary > 50000 # [name salary]'
        result = types(src)
        expected = [
            TokenType.IDENT, TokenType.QUESTION, TokenType.IDENT,
            TokenType.GT, TokenType.INTEGER, TokenType.HASH,
            TokenType.LBRACKET, TokenType.IDENT, TokenType.IDENT,
            TokenType.RBRACKET,
        ]
        assert result == expected

    def test_summarize(self) -> None:
        src = "E / dept_id [n: #.  avg: %. salary]"
        result = types(src)
        expected = [
            TokenType.IDENT, TokenType.SLASH, TokenType.IDENT,
            TokenType.LBRACKET, TokenType.IDENT, TokenType.COLON,
            TokenType.HASH_DOT, TokenType.IDENT, TokenType.COLON,
            TokenType.PERCENT_DOT, TokenType.IDENT, TokenType.RBRACKET,
        ]
        assert result == expected

    def test_nest_join(self) -> None:
        src = "E *: Phone > phones"
        result = types(src)
        expected = [
            TokenType.IDENT, TokenType.STAR_COLON, TokenType.IDENT,
            TokenType.GT, TokenType.IDENT,
        ]
        assert result == expected

    def test_sort_take(self) -> None:
        src = "E # [name salary] $ salary- ^ 3"
        # Note: salary- is IDENT(salary) MINUS
        result = types(src)
        assert TokenType.DOLLAR in result
        assert TokenType.CARET in result

    def test_extend_computation(self) -> None:
        src = "E + bonus: salary * 0.1"
        result = types(src)
        expected = [
            TokenType.IDENT, TokenType.PLUS, TokenType.IDENT,
            TokenType.COLON, TokenType.IDENT, TokenType.STAR,
            TokenType.FLOAT,
        ]
        assert result == expected

    def test_set_literal(self) -> None:
        src = "E ? dept_id = {10, 20, 30}"
        result = types(src)
        assert TokenType.LBRACE in result
        assert TokenType.RBRACE in result
        assert TokenType.COMMA in result

    def test_or_filter(self) -> None:
        src = "E ? (dept_id = 20 | salary > 80000)"
        result = types(src)
        assert TokenType.LPAREN in result
        assert TokenType.PIPE in result
        assert TokenType.RPAREN in result

    def test_number_before_dot_operator(self) -> None:
        """Ensure 0.1 is parsed as float, but 50000 before #. is integer."""
        src = "50000 #."
        result = types(src)
        assert result == [TokenType.INTEGER, TokenType.HASH_DOT]


class TestComments:
    """Test comment handling."""

    def test_line_comment(self) -> None:
        src = "E -- this is a comment\n? salary > 50000"
        result = types(src)
        assert result[0] == TokenType.IDENT
        assert result[1] == TokenType.QUESTION


class TestErrors:
    """Test error handling."""

    def test_unterminated_string(self) -> None:
        with pytest.raises(LexError):
            Lexer('"unterminated').tokenize()

    def test_unexpected_char(self) -> None:
        with pytest.raises(LexError):
            Lexer("E ? salary ` 50000").tokenize()


class TestPositionTracking:
    """Test that tokens have correct line/col info."""

    def test_first_token(self) -> None:
        toks = Lexer("E").tokenize()
        assert toks[0].line == 1
        assert toks[0].col == 1

    def test_multiline(self) -> None:
        toks = Lexer("E\n? salary").tokenize()
        assert toks[0].line == 1  # E
        assert toks[1].line == 2  # ?
        assert toks[2].line == 2  # salary
