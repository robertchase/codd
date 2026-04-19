"""Tests for the parser."""

from codd.lexer.lexer import Lexer
from codd.parser.parser import Parser, ParseError
from codd.parser import ast_nodes as ast
import pytest


def parse(source: str) -> ast.RelExpr:
    """Helper: lex + parse a source string."""
    tokens = Lexer(source).tokenize()
    return Parser(tokens).parse()


class TestAtom:
    """Test parsing atomic expressions."""

    def test_relation_name(self) -> None:
        """Bare identifier parses as a RelName."""
        result = parse("E")
        assert isinstance(result, ast.RelName)
        assert result.name == "E"

    def test_parenthesized(self) -> None:
        """Parenthesized expression unwraps to inner node."""
        result = parse("(E)")
        assert isinstance(result, ast.RelName)
        assert result.name == "E"


class TestProject:
    """Test project parsing."""

    def test_single_attr(self) -> None:
        """Project on a single attribute."""
        result = parse("E # name")
        assert isinstance(result, ast.Project)
        assert result.attrs == ("name",)

    def test_multiple_attrs(self) -> None:
        """Project on multiple bracketed attributes."""
        result = parse("E # [name salary]")
        assert isinstance(result, ast.Project)
        assert result.attrs == ("name", "salary")


class TestRemove:
    """Test remove (#!) parsing."""

    def test_single_attr(self) -> None:
        """Remove a single attribute."""
        result = parse("E #! salary")
        assert isinstance(result, ast.Remove)
        assert result.attrs == ("salary",)
        assert isinstance(result.source, ast.RelName)

    def test_multiple_attrs(self) -> None:
        """Remove multiple bracketed attributes."""
        result = parse("E #! [emp_id dept_id]")
        assert isinstance(result, ast.Remove)
        assert result.attrs == ("emp_id", "dept_id")


class TestFilter:
    """Test filter parsing."""

    def test_simple_gt(self) -> None:
        """Greater-than filter with an integer literal."""
        result = parse("E ? salary > 50000")
        assert isinstance(result, ast.Filter)
        assert isinstance(result.condition, ast.Comparison)
        assert result.condition.op == ">"
        assert isinstance(result.condition.right, ast.IntLiteral)
        assert result.condition.right.value == 50000

    def test_eq_string(self) -> None:
        """Equality filter with a string literal."""
        result = parse('E ? name = "Alice"')
        assert isinstance(result, ast.Filter)
        assert result.condition.op == "="
        assert isinstance(result.condition.right, ast.StringLiteral)
        assert result.condition.right.value == "Alice"

    def test_negated_filter(self) -> None:
        """Negated filter operator produces NegatedFilter node."""
        result = parse('E ?! role = "engineer"')
        assert isinstance(result, ast.NegatedFilter)
        assert result.condition.op == "="

    def test_or_condition(self) -> None:
        """OR boolean combination in a filter condition."""
        result = parse("E ? (dept_id = 20 | salary > 80000)")
        assert isinstance(result, ast.Filter)
        assert isinstance(result.condition, ast.BoolCombination)
        assert result.condition.op == "|"

    def test_and_condition(self) -> None:
        """AND boolean combination in a filter condition."""
        result = parse("E ? (salary > 50000 & dept_id = 10)")
        assert isinstance(result, ast.Filter)
        assert isinstance(result.condition, ast.BoolCombination)
        assert result.condition.op == "&"

    def test_negative_int_literal(self) -> None:
        """Negative integer literal in a comparison."""
        result = parse("E ? salary > -1")
        assert isinstance(result, ast.Filter)
        assert isinstance(result.condition.right, ast.IntLiteral)
        assert result.condition.right.value == -1

    def test_negative_float_literal(self) -> None:
        """Negative float literal in a comparison."""
        result = parse("E ? salary > -1.5")
        assert isinstance(result, ast.Filter)
        assert isinstance(result.condition.right, ast.FloatLiteral)
        assert result.condition.right.value == -1.5

    def test_set_membership(self) -> None:
        """Set literal on the right side of a comparison."""
        result = parse("E ? dept_id = {10, 20, 30}")
        assert isinstance(result, ast.Filter)
        assert isinstance(result.condition.right, ast.SetLiteral)
        assert len(result.condition.right.elements) == 3


class TestChaining:
    """Test chaining of operations."""

    def test_filter_project(self) -> None:
        """Filter followed by project chains correctly."""
        result = parse("E ? salary > 50000 # [name salary]")
        assert isinstance(result, ast.Project)
        assert isinstance(result.source, ast.Filter)

    def test_double_filter(self) -> None:
        """Two consecutive filters chain left-to-right."""
        result = parse("E ? dept_id = 10 ? salary > 70000")
        assert isinstance(result, ast.Filter)
        assert isinstance(result.source, ast.Filter)
        assert isinstance(result.source.source, ast.RelName)

    def test_join_filter_project(self) -> None:
        """Join then filter then project chains correctly."""
        result = parse('E *. D ? dept_name = "Engineering" # [name salary]')
        assert isinstance(result, ast.Project)
        assert isinstance(result.source, ast.Filter)
        assert isinstance(result.source.source, ast.NaturalJoin)


class TestJoin:
    """Test join parsing."""

    def test_natural_join(self) -> None:
        """Natural join between two relations."""
        result = parse("E *. D")
        assert isinstance(result, ast.NaturalJoin)
        assert isinstance(result.right, ast.RelName)
        assert result.right.name == "D"

    def test_nest_join(self) -> None:
        """Nest join with target nest name."""
        result = parse("E *: Phone -> phones")
        assert isinstance(result, ast.NestJoin)
        assert isinstance(result.right, ast.RelName)
        assert result.nest_name == "phones"

    def test_left_join_no_defaults(self) -> None:
        """Left join with no defaults bracket."""
        result = parse("E *< D")
        assert isinstance(result, ast.LeftJoin)
        assert isinstance(result.right, ast.RelName)
        assert result.right.name == "D"
        assert result.defaults == ()

    def test_left_join_with_defaults(self) -> None:
        """Left join with a defaults bracket."""
        result = parse("E *< D [total: 0]")
        assert isinstance(result, ast.LeftJoin)
        assert len(result.defaults) == 1
        assert result.defaults[0].name == "total"
        assert isinstance(result.defaults[0].expr, ast.IntLiteral)
        assert result.defaults[0].expr.value == 0

    def test_left_join_chains(self) -> None:
        """Left join result can be projected."""
        result = parse("E *< D # name")
        assert isinstance(result, ast.Project)
        assert isinstance(result.source, ast.LeftJoin)


class TestUnnest:
    """Test unnest parsing."""

    def test_simple_unnest(self) -> None:
        """Unnest extracts the nested attribute name."""
        result = parse("E <: phones")
        assert isinstance(result, ast.Unnest)
        assert isinstance(result.source, ast.RelName)
        assert result.nest_attr == "phones"

    def test_unnest_after_nest_join(self) -> None:
        """Unnest chains after a nest join."""
        result = parse("E *: Phone -> phones <: phones")
        assert isinstance(result, ast.Unnest)
        assert result.nest_attr == "phones"
        assert isinstance(result.source, ast.NestJoin)


class TestExtend:
    """Test extend parsing."""

    def test_single(self) -> None:
        """Single computed column with arithmetic expression."""
        result = parse("E +: bonus: salary * 0.1")
        assert isinstance(result, ast.Extend)
        assert len(result.computations) == 1
        comp = result.computations[0]
        assert comp.name == "bonus"
        assert isinstance(comp.expr, ast.BinOp)
        assert comp.expr.op == "*"

    def test_multiple(self) -> None:
        """Multiple bracketed computed columns."""
        result = parse("E +: [bonus: salary * 0.1  tax: salary * 0.3]")
        assert isinstance(result, ast.Extend)
        assert len(result.computations) == 2
        assert result.computations[0].name == "bonus"
        assert result.computations[1].name == "tax"


class TestModify:
    """Test modify parsing."""

    def test_single(self) -> None:
        """Single modify expression."""
        result = parse("E =: salary: salary * 1.1")
        assert isinstance(result, ast.Modify)
        assert len(result.computations) == 1
        comp = result.computations[0]
        assert comp.name == "salary"
        assert isinstance(comp.expr, ast.BinOp)
        assert comp.expr.op == "*"

    def test_multiple(self) -> None:
        """Multiple bracketed modify expressions."""
        result = parse('E =: [salary: salary * 1.1  role: "senior"]')
        assert isinstance(result, ast.Modify)
        assert len(result.computations) == 2
        assert result.computations[0].name == "salary"
        assert result.computations[1].name == "role"


class TestLeftToRightArithmetic:
    """Test left-to-right arithmetic evaluation (no precedence)."""

    def test_chained_multiply_divide(self) -> None:
        """a / b * 2 parses as (a / b) * 2 (left-to-right)."""
        result = parse("R +: x: a / b * 2")
        assert isinstance(result, ast.Extend)
        expr = result.computations[0].expr
        assert isinstance(expr, ast.BinOp)
        assert expr.op == "*"
        assert isinstance(expr.left, ast.BinOp)
        assert expr.left.op == "/"
        assert isinstance(expr.right, ast.IntLiteral)
        assert expr.right.value == 2

    def test_add_then_multiply(self) -> None:
        """a + b * 2 parses as (a + b) * 2 (left-to-right, no precedence)."""
        result = parse("R +: x: a + b * 2")
        assert isinstance(result, ast.Extend)
        expr = result.computations[0].expr
        assert isinstance(expr, ast.BinOp)
        assert expr.op == "*"
        assert isinstance(expr.left, ast.BinOp)
        assert expr.left.op == "+"
        assert isinstance(expr.right, ast.IntLiteral)
        assert expr.right.value == 2

    def test_chained_additive(self) -> None:
        """a + b - c parses as (a + b) - c."""
        result = parse("R +: x: a + b - c")
        assert isinstance(result, ast.Extend)
        expr = result.computations[0].expr
        assert isinstance(expr, ast.BinOp)
        assert expr.op == "-"
        assert isinstance(expr.left, ast.BinOp)
        assert expr.left.op == "+"

    def test_parens_override(self) -> None:
        """a + (b * 2) groups multiplication first via parentheses."""
        result = parse("R +: x: a + (b * 2)")
        assert isinstance(result, ast.Extend)
        expr = result.computations[0].expr
        assert isinstance(expr, ast.BinOp)
        assert expr.op == "+"
        assert isinstance(expr.left, ast.AttrRef)
        assert isinstance(expr.right, ast.BinOp)
        assert expr.right.op == "*"

    def test_tilde_left_to_right(self) -> None:
        """a ~ 2 + b parses as (a ~ 2) + b (tilde has no special precedence)."""
        result = parse("R +: x: a ~ 2 + b")
        assert isinstance(result, ast.Extend)
        expr = result.computations[0].expr
        assert isinstance(expr, ast.BinOp)
        assert expr.op == "+"
        assert isinstance(expr.left, ast.Round)
        assert expr.left.places == 2
        assert isinstance(expr.right, ast.AttrRef)

    def test_integer_divide(self) -> None:
        """a // b parses as BinOp with op '//'."""
        result = parse("R +: x: a // b")
        assert isinstance(result, ast.Extend)
        expr = result.computations[0].expr
        assert isinstance(expr, ast.BinOp)
        assert expr.op == "//"

    def test_remainder(self) -> None:
        """a % b parses as BinOp with op '%'."""
        result = parse("R +: x: a % b")
        assert isinstance(result, ast.Extend)
        expr = result.computations[0].expr
        assert isinstance(expr, ast.BinOp)
        assert expr.op == "%"


class TestSubstring:
    """Test .s (substring) parsing."""

    def test_two_args(self) -> None:
        """name .s [1 3] parses as Substring(start=1, end=3)."""
        result = parse("R +: sub: name .s [1 3]")
        assert isinstance(result, ast.Extend)
        expr = result.computations[0].expr
        assert isinstance(expr, ast.Substring)
        assert expr.start == 1
        assert expr.end == 3
        assert isinstance(expr.expr, ast.AttrRef)

    def test_single_arg(self) -> None:
        """name .s [3] parses as Substring(start=3, end=None)."""
        result = parse("R +: sub: name .s [3]")
        assert isinstance(result, ast.Extend)
        expr = result.computations[0].expr
        assert isinstance(expr, ast.Substring)
        assert expr.start == 3
        assert expr.end is None

    def test_negative_args(self) -> None:
        """name .s [-4 -2] parses with negative indices."""
        result = parse("R +: sub: name .s [-4 -2]")
        assert isinstance(result, ast.Extend)
        expr = result.computations[0].expr
        assert isinstance(expr, ast.Substring)
        assert expr.start == -4
        assert expr.end == -2

    def test_chains_left_to_right(self) -> None:
        """name .s [1 3] + suffix chains left-to-right."""
        result = parse("R +: x: name .s [1 3] + suffix")
        assert isinstance(result, ast.Extend)
        expr = result.computations[0].expr
        assert isinstance(expr, ast.BinOp)
        assert expr.op == "+"
        assert isinstance(expr.left, ast.Substring)


class TestIota:
    """Test i. (iota) parsing."""

    def test_basic(self) -> None:
        """i. 5 parses as Iota with IntLiteral count."""
        result = parse("i. 5")
        assert isinstance(result, ast.Iota)
        assert isinstance(result.count, ast.IntLiteral)
        assert result.count.value == 5
        assert result.name == "i"

    def test_named(self) -> None:
        """i. month: 12 parses with custom name."""
        result = parse("i. month: 12")
        assert isinstance(result, ast.Iota)
        assert isinstance(result.count, ast.IntLiteral)
        assert result.count.value == 12
        assert result.name == "month"

    def test_chain(self) -> None:
        """i. 10 can be followed by postfix operators."""
        result = parse("i. 10 =: i: i + 9")
        assert isinstance(result, ast.Modify)
        assert isinstance(result.source, ast.Iota)
        assert isinstance(result.source.count, ast.IntLiteral)
        assert result.source.count.value == 10

    def test_named_chain(self) -> None:
        """i. day: 365 +: ... chains correctly."""
        result = parse("i. day: 365 +: x: day * 2")
        assert isinstance(result, ast.Extend)
        assert isinstance(result.source, ast.Iota)
        assert result.source.name == "day"
        assert isinstance(result.source.count, ast.IntLiteral)
        assert result.source.count.value == 365

    def test_in_subquery(self) -> None:
        """i. works inside parenthesized subqueries."""
        result = parse("E *. (i. 5 @ i emp_id)")
        assert isinstance(result, ast.NaturalJoin)
        assert isinstance(result.right, ast.Rename)

    def test_subquery_count(self) -> None:
        """i. week: (R /. >. week) parses as Iota with SubqueryExpr count."""
        result = parse("i. week: (R /. >. week)")
        assert isinstance(result, ast.Iota)
        assert result.name == "week"
        assert isinstance(result.count, ast.SubqueryExpr)

    def test_zero_count_error(self) -> None:
        """i. 0 is a runtime error (detected at execution time)."""
        from codd.executor.executor import ExecutionError
        from codd.executor.environment import Environment
        from codd.executor.executor import Executor
        from codd.lexer.lexer import Lexer
        from codd.parser.parser import Parser
        tokens = Lexer("i. 0").tokenize()
        tree = Parser(tokens).parse()
        with pytest.raises(ExecutionError, match="positive integer"):
            Executor(Environment()).execute(tree)


class TestIotaZero:
    """Test I. (zero-based iota) parsing."""

    def test_basic(self) -> None:
        """I. 5 parses as Iota with zero_based=True."""
        result = parse("I. 5")
        assert isinstance(result, ast.Iota)
        assert result.zero_based is True
        assert isinstance(result.count, ast.IntLiteral)
        assert result.count.value == 5
        assert result.name == "i"

    def test_named(self) -> None:
        """I. idx: 10 parses with custom name and zero_based=True."""
        result = parse("I. idx: 10")
        assert isinstance(result, ast.Iota)
        assert result.zero_based is True
        assert result.name == "idx"

    def test_one_based_not_zero(self) -> None:
        """i. 5 has zero_based=False."""
        result = parse("i. 5")
        assert isinstance(result, ast.Iota)
        assert result.zero_based is False


class TestTypeCast:
    """Test .as (type cast) parsing."""

    def test_basic(self) -> None:
        """amount .as int parses as TypeCast."""
        result = parse("E +: n: amount .as int")
        assert isinstance(result, ast.Extend)
        comp = result.computations[0]
        assert isinstance(comp.expr, ast.TypeCast)
        assert comp.expr.target_type == "int"
        assert isinstance(comp.expr.expr, ast.AttrRef)

    def test_chained_with_arithmetic(self) -> None:
        """salary + 1 .as int parses as TypeCast(BinOp, 'int')."""
        result = parse("E +: n: salary + 1 .as int")
        comp = result.computations[0]
        assert isinstance(comp.expr, ast.TypeCast)
        assert isinstance(comp.expr.expr, ast.BinOp)

    def test_in_filter_lhs(self) -> None:
        """amount .as int works on the LHS of a comparison."""
        result = parse('E ? amount .as int > 100')
        assert isinstance(result, ast.Filter)
        assert isinstance(result.condition.left, ast.TypeCast)
        assert result.condition.left.target_type == "int"


class TestRotate:
    """Test r. (rotate) parsing."""

    def test_basic(self) -> None:
        """E r. parses as Rotate."""
        result = parse("E r.")
        assert isinstance(result, ast.Rotate)
        assert isinstance(result.source, ast.RelName)

    def test_after_filter(self) -> None:
        """E ? salary > 50000 r. chains correctly."""
        result = parse("E ? salary > 50000 r.")
        assert isinstance(result, ast.Rotate)
        assert isinstance(result.source, ast.Filter)


class TestRelationLiteral:
    """Test {} (relation literal) parsing."""

    def test_basic(self) -> None:
        """Parses a simple two-column relation."""
        result = parse('{name age; "Alice" 30; "Bob" 25}')
        assert isinstance(result, ast.RelationLiteral)
        assert result.attributes == ("name", "age")
        assert len(result.rows) == 2
        assert ("Alice", 30) in result.rows
        assert ("Bob", 25) in result.rows

    def test_single_column(self) -> None:
        """Single-column relation."""
        result = parse("{x; 1; 2; 3}")
        assert isinstance(result, ast.RelationLiteral)
        assert result.attributes == ("x",)
        assert result.rows == ((1,), (2,), (3,))

    def test_chain(self) -> None:
        """Relation literal feeds into postfix chain."""
        result = parse('{x; 1; 2; 3} ? x > 1')
        assert isinstance(result, ast.Filter)
        assert isinstance(result.source, ast.RelationLiteral)

    def test_negative_values(self) -> None:
        """Negative numbers in rows."""
        result = parse("{x; -1; -2}")
        assert isinstance(result, ast.RelationLiteral)
        assert result.rows == ((-1,), (-2,))

    def test_mixed_types(self) -> None:
        """String, int, float, bool in one row."""
        result = parse('{s n f b; "hi" 1 2.5 true}')
        assert isinstance(result, ast.RelationLiteral)
        assert result.rows == (("hi", 1, 2.5, True),)

    def test_wrong_column_count_error(self) -> None:
        """Row with wrong number of values is an error."""
        with pytest.raises(ParseError, match="values but header has"):
            parse("{a b; 1}")

    def test_trailing_semicolon(self) -> None:
        """Trailing semicolon is allowed."""
        result = parse("{x; 1; 2;}")
        assert isinstance(result, ast.RelationLiteral)
        assert result.rows == ((1,), (2,))

    def test_empty_header_error(self) -> None:
        """Empty braces with no header is an error."""
        with pytest.raises(ParseError, match="attribute names"):
            parse("{; 1}")


class TestDateOp:
    """Test .d (date) parsing."""

    def test_promotion(self) -> None:
        """.d with no RHS parses as DateOp(fmt=None)."""
        result = parse("R +: d: col .d")
        assert isinstance(result, ast.Extend)
        expr = result.computations[0].expr
        assert isinstance(expr, ast.DateOp)
        assert expr.fmt is None
        assert isinstance(expr.expr, ast.AttrRef)

    def test_extraction(self) -> None:
        """.d "year" parses as DateOp(fmt='year')."""
        result = parse('R +: y: col .d "year"')
        assert isinstance(result, ast.Extend)
        expr = result.computations[0].expr
        assert isinstance(expr, ast.DateOp)
        assert expr.fmt == "year"

    def test_format_pattern(self) -> None:
        """.d "{dd}/{mm}/{yyyy}" parses with format string."""
        result = parse('R +: f: col .d "{dd}/{mm}/{yyyy}"')
        assert isinstance(result, ast.Extend)
        expr = result.computations[0].expr
        assert isinstance(expr, ast.DateOp)
        assert expr.fmt == "{dd}/{mm}/{yyyy}"

    def test_chains_with_arithmetic(self) -> None:
        """.d promotes, then + adds days."""
        result = parse("R +: d: col .d + 1")
        assert isinstance(result, ast.Extend)
        expr = result.computations[0].expr
        assert isinstance(expr, ast.BinOp)
        assert expr.op == "+"
        assert isinstance(expr.left, ast.DateOp)
        assert expr.left.fmt is None

    def test_extraction_in_chain(self) -> None:
        """.d "month" returns int, usable in arithmetic."""
        result = parse('R +: x: col .d "month" + 1')
        assert isinstance(result, ast.Extend)
        expr = result.computations[0].expr
        assert isinstance(expr, ast.BinOp)
        assert isinstance(expr.left, ast.DateOp)
        assert expr.left.fmt == "month"


class TestFormatStr:
    """Test .f (format string) parsing."""

    def test_basic(self) -> None:
        """String .f parses as FormatStr."""
        result = parse('R +: lbl: "{name} - {dept_id}" .f')
        assert isinstance(result, ast.Extend)
        expr = result.computations[0].expr
        assert isinstance(expr, ast.FormatStr)
        assert isinstance(expr.expr, ast.StringLiteral)
        assert expr.expr.value == "{name} - {dept_id}"

    def test_chains(self) -> None:
        """.f can chain with other operators (result is a string)."""
        result = parse('R +: x: "{name}" .f .s [1 3]')
        assert isinstance(result, ast.Extend)
        expr = result.computations[0].expr
        assert isinstance(expr, ast.Substring)
        assert isinstance(expr.expr, ast.FormatStr)


class TestRename:
    """Test rename parsing."""

    def test_single(self) -> None:
        """Single attribute rename mapping."""
        result = parse("E @ pay salary")
        assert isinstance(result, ast.Rename)
        assert result.mappings == (("pay", "salary"),)

    def test_multiple(self) -> None:
        """Multiple bracketed rename mappings."""
        result = parse("E @ [pay salary  dept department]")
        assert isinstance(result, ast.Rename)
        assert len(result.mappings) == 2


class TestSetOps:
    """Test set operation parsing."""

    def test_union(self) -> None:
        """Union of two relations."""
        result = parse("E |. (D)")
        assert isinstance(result, ast.Union)

    def test_difference(self) -> None:
        """Set difference of two projected relations."""
        result = parse("E # emp_id -. (Phone # emp_id)")
        assert isinstance(result, ast.Difference)
        assert isinstance(result.source, ast.Project)

    def test_intersect(self) -> None:
        """Set intersection of two projected relations."""
        result = parse("(E # emp_id) &. (Phone # emp_id)")
        assert isinstance(result, ast.Intersect)


class TestSummarize:
    """Test summarize parsing."""

    def test_single_key(self) -> None:
        """Summarize with one group key and two aggregates."""
        result = parse("E /. dept_id [n: #.  avg: %. salary]")
        assert isinstance(result, ast.Summarize)
        assert result.group_attrs == ("dept_id",)
        assert len(result.computations) == 2
        assert result.computations[0].name == "n"
        assert isinstance(result.computations[0].expr, ast.AggregateCall)
        assert result.computations[0].expr.func == "#."
        assert result.computations[1].name == "avg"
        assert isinstance(result.computations[1].expr, ast.AggregateCall)
        assert result.computations[1].expr.func == "%."
        assert result.computations[1].expr.arg == ast.AttrRef(parts=("salary",))

    def test_single_aggregate_no_brackets(self) -> None:
        """Summarize with one aggregate without brackets."""
        result = parse("E /. dept_id total: +. salary")
        assert isinstance(result, ast.Summarize)
        assert result.group_attrs == ("dept_id",)
        assert len(result.computations) == 1
        assert result.computations[0].name == "total"
        assert isinstance(result.computations[0].expr, ast.AggregateCall)
        assert result.computations[0].expr.func == "+."
        assert result.computations[0].expr.arg == ast.AttrRef(parts=("salary",))

    def test_summarize_all_no_brackets(self) -> None:
        """Summarize-all with a single aggregate, no brackets."""
        result = parse("E /. n: #.")
        assert isinstance(result, ast.SummarizeAll)
        assert len(result.computations) == 1
        assert result.computations[0].name == "n"
        assert isinstance(result.computations[0].expr, ast.AggregateCall)
        assert result.computations[0].expr.func == "#."

    def test_summarize_all(self) -> None:
        """Summarize-all with multiple bracketed aggregates."""
        result = parse("E /. [n: #.  total: +. salary]")
        assert isinstance(result, ast.SummarizeAll)
        assert len(result.computations) == 2

    # --- Auto-naming ---

    def test_auto_name_count(self) -> None:
        """Bare #. gets auto-named 'count'."""
        result = parse("E /. dept_id #.")
        assert isinstance(result, ast.Summarize)
        assert result.computations[0].name == "count"
        assert result.computations[0].expr.func == "#."

    def test_auto_name_sum(self) -> None:
        """Bare +. salary gets auto-named 'sum_salary'."""
        result = parse("E /. dept_id +. salary")
        assert isinstance(result, ast.Summarize)
        assert result.computations[0].name == "sum_salary"

    def test_auto_name_max(self) -> None:
        """Bare >. salary gets auto-named 'max_salary'."""
        result = parse("E /. dept_id >. salary")
        assert isinstance(result, ast.Summarize)
        assert result.computations[0].name == "max_salary"

    def test_auto_name_min(self) -> None:
        """Bare <. salary gets auto-named 'min_salary'."""
        result = parse("E /. dept_id <. salary")
        assert isinstance(result, ast.Summarize)
        assert result.computations[0].name == "min_salary"

    def test_auto_name_mean(self) -> None:
        """Bare %. salary gets auto-named 'mean_salary'."""
        result = parse("E /. dept_id %. salary")
        assert isinstance(result, ast.Summarize)
        assert result.computations[0].name == "mean_salary"

    def test_auto_name_collect(self) -> None:
        """Bare n. gets auto-named 'collect'."""
        result = parse("E /. dept_id n.")
        assert isinstance(result, ast.Summarize)
        assert result.computations[0].name == "collect"

    def test_auto_name_collect_attr(self) -> None:
        """Bare n. name gets auto-named 'collect_name'."""
        result = parse("E /. dept_id n. name")
        assert isinstance(result, ast.Summarize)
        assert result.computations[0].name == "collect_name"

    def test_auto_name_count_rva(self) -> None:
        """#. with RVA source gets auto-named 'count_phones'."""
        result = parse("E /. dept_id #. phones")
        assert isinstance(result, ast.Summarize)
        assert result.computations[0].name == "count_phones"

    def test_auto_name_bracketed_multiple(self) -> None:
        """Multiple auto-named aggregates in brackets."""
        result = parse("E /. dept_id [#.  +. salary  %. salary]")
        assert isinstance(result, ast.Summarize)
        assert len(result.computations) == 3
        assert result.computations[0].name == "count"
        assert result.computations[1].name == "sum_salary"
        assert result.computations[2].name == "mean_salary"

    def test_auto_name_mixed_with_explicit(self) -> None:
        """Mix of auto-named and explicitly named aggregates."""
        result = parse("E /. dept_id [#.  avg: %. salary  +. bonus]")
        assert isinstance(result, ast.Summarize)
        assert len(result.computations) == 3
        assert result.computations[0].name == "count"
        assert result.computations[1].name == "avg"
        assert result.computations[2].name == "sum_bonus"

    def test_auto_name_summarize_all(self) -> None:
        """Auto-naming works with summarize-all (/.)."""
        result = parse("E /. [#.  +. salary]")
        assert isinstance(result, ast.SummarizeAll)
        assert result.computations[0].name == "count"
        assert result.computations[1].name == "sum_salary"

    def test_auto_name_summarize_all_single(self) -> None:
        """Auto-naming works with summarize-all, single aggregate, no brackets."""
        result = parse("E /. #.")
        assert isinstance(result, ast.SummarizeAll)
        assert result.computations[0].name == "count"

    def test_auto_name_duplicate_error(self) -> None:
        """Duplicate auto-generated names are a parse error."""
        with pytest.raises(ParseError, match="Duplicate column name"):
            parse("E /. dept_id [+. salary  +. salary]")

    def test_auto_name_complex_expr_requires_name(self) -> None:
        """Complex expression starting with aggregate requires explicit name."""
        with pytest.raises(ParseError, match="Complex expression requires an explicit name"):
            parse("E /. dept_id +. salary * 2")

    def test_multi_key(self) -> None:
        """Summarize with multiple grouping keys."""
        result = parse("E /. [dept_id region] +. salary")
        assert isinstance(result, ast.Summarize)
        assert result.group_attrs == ("dept_id", "region")
        assert len(result.computations) == 1
        assert result.computations[0].name == "sum_salary"

    def test_multi_key_multi_agg(self) -> None:
        """Summarize with multiple keys and multiple aggregates."""
        result = parse("E /. [dept_id region] [n: #.  total: +. salary]")
        assert isinstance(result, ast.Summarize)
        assert result.group_attrs == ("dept_id", "region")
        assert len(result.computations) == 2
        assert result.computations[0].name == "n"
        assert result.computations[1].name == "total"

    def test_nest_by(self) -> None:
        """Nest-by groups and assigns a nest name."""
        result = parse("E /: dept_id -> team")
        assert isinstance(result, ast.NestBy)
        assert result.group_attrs == ("dept_id",)
        assert result.nest_name == "team"

    def test_nest_by_multi_key(self) -> None:
        """Nest-by with multiple grouping keys."""
        result = parse("E /: [dept_id region] -> team")
        assert isinstance(result, ast.NestBy)
        assert result.group_attrs == ("dept_id", "region")
        assert result.nest_name == "team"


class TestSort:
    """Test sort parsing."""

    def test_ascending(self) -> None:
        """Ascending sort on a single key."""
        result = parse("E $ salary")
        assert isinstance(result, ast.Sort)
        assert result.keys == (ast.SortKey(attr="salary", descending=False),)

    def test_descending(self) -> None:
        """Descending sort using trailing minus."""
        result = parse("E $ salary-")
        assert isinstance(result, ast.Sort)
        assert result.keys == (ast.SortKey(attr="salary", descending=True),)

    def test_multi_key(self) -> None:
        """Multi-key sort with mixed directions."""
        result = parse("E $ [dept_id salary-]")
        assert isinstance(result, ast.Sort)
        assert len(result.keys) == 2
        assert result.keys[0].descending is False
        assert result.keys[1].descending is True

    def test_take(self) -> None:
        """Take limits results after a sort."""
        result = parse("E $ salary- ^ 3")
        assert isinstance(result, ast.Take)
        assert result.count == 3
        assert isinstance(result.source, ast.Sort)


class TestComplexExpressions:
    """Test complex chained expressions from the design doc."""

    def test_union_with_rename(self) -> None:
        """Union where the left side has a rename."""
        result = parse("ContractorPay @ [pay salary] |. (E # [name salary])")
        assert isinstance(result, ast.Union)
        assert isinstance(result.source, ast.Rename)

    def test_sort_take(self) -> None:
        """Project then sort then take chain."""
        result = parse("E # [name salary] $ salary- ^ 3")
        assert isinstance(result, ast.Take)
        assert isinstance(result.source, ast.Sort)
        assert isinstance(result.source.source, ast.Project)

    def test_nest_by_extend(self) -> None:
        """Extend with aggregate call after nest-by."""
        result = parse("E /: dept_id -> team +: [top: >. team.salary]")
        assert isinstance(result, ast.Extend)
        assert isinstance(result.source, ast.NestBy)
        comp = result.computations[0]
        assert comp.name == "top"
        assert isinstance(comp.expr, ast.AggregateCall)
        assert comp.expr.func == ">."


class TestAssignment:
    """Test := assignment parsing."""

    def test_simple_assignment(self) -> None:
        """Assignment with a filter expression."""
        result = parse("high := E ? salary > 70000")
        assert isinstance(result, ast.Assignment)
        assert result.name == "high"
        assert isinstance(result.expr, ast.Filter)

    def test_assignment_with_chain(self) -> None:
        """Assignment with a project expression."""
        result = parse("names := E # name")
        assert isinstance(result, ast.Assignment)
        assert result.name == "names"
        assert isinstance(result.expr, ast.Project)

    def test_assignment_bare_relation(self) -> None:
        """Assignment of a bare relation name."""
        result = parse("copy := E")
        assert isinstance(result, ast.Assignment)
        assert result.name == "copy"
        assert isinstance(result.expr, ast.RelName)
        assert result.expr.name == "E"

    def test_assignment_complex_chain(self) -> None:
        """Assignment of a multi-step chained expression."""
        result = parse("top3 := E # [name salary] $ salary- ^ 3")
        assert isinstance(result, ast.Assignment)
        assert result.name == "top3"
        assert isinstance(result.expr, ast.Take)


class TestTypeAliasParsing:
    """Test type-alias parsing (name := type <target>)."""

    def test_simple_alias(self) -> None:
        """Alias to a built-in type."""
        result = parse("Age := type int")
        assert isinstance(result, ast.TypeAlias)
        assert result.name == "Age"
        assert result.target_type == "int"

    def test_parameterised_alias(self) -> None:
        """Alias to decimal(N)."""
        result = parse("Money := type decimal(2)")
        assert isinstance(result, ast.TypeAlias)
        assert result.name == "Money"
        assert result.target_type == "decimal(2)"

    def test_in_constraint_alias(self) -> None:
        """Alias to an in() constraint."""
        result = parse("Status := type in(Statuses, name)")
        assert isinstance(result, ast.TypeAlias)
        assert result.target_type == "in(Statuses, name)"

    def test_alias_to_another_udt(self) -> None:
        """Alias to another UDT is a bare IDENT target."""
        result = parse("Price := type Money")
        assert isinstance(result, ast.TypeAlias)
        assert result.target_type == "Money"

    def test_type_not_a_keyword(self) -> None:
        """`type` followed by a non-IDENT is still a regular assignment.

        Assigning `X := type` (relation named `type`) is currently a parse
        error downstream, but `X := type # col` must NOT be mistaken for
        a type alias.
        """
        # Parses as project on the relation named `type`.
        result = parse("X := type # col")
        assert isinstance(result, ast.Assignment)
        assert isinstance(result.expr, ast.Project)


class TestTernaryParsing:
    """Test ternary expression parsing."""

    def test_basic_ternary(self) -> None:
        """Basic ternary with comparison, true, and false branches."""
        result = parse('E +: [grp: ?: dept_id = 10 "eng" "other"]')
        assert isinstance(result, ast.Extend)
        comp = result.computations[0]
        assert comp.name == "grp"
        assert isinstance(comp.expr, ast.TernaryExpr)
        assert isinstance(comp.expr.condition, ast.Comparison)
        assert comp.expr.condition.op == "="
        assert isinstance(comp.expr.true_expr, ast.StringLiteral)
        assert comp.expr.true_expr.value == "eng"
        assert isinstance(comp.expr.false_expr, ast.StringLiteral)
        assert comp.expr.false_expr.value == "other"

    def test_nested_ternary_parenthesized(self) -> None:
        """Nested ternary in parenthesized false branch."""
        result = parse(
            'E +: [tier: ?: salary >= 80000 "high" (?: salary >= 60000 "mid" "low")]'
        )
        assert isinstance(result, ast.Extend)
        comp = result.computations[0]
        assert isinstance(comp.expr, ast.TernaryExpr)
        assert isinstance(comp.expr.true_expr, ast.StringLiteral)
        assert comp.expr.true_expr.value == "high"
        # false branch is a nested ternary
        assert isinstance(comp.expr.false_expr, ast.TernaryExpr)
        inner = comp.expr.false_expr
        assert isinstance(inner.true_expr, ast.StringLiteral)
        assert inner.true_expr.value == "mid"
        assert isinstance(inner.false_expr, ast.StringLiteral)
        assert inner.false_expr.value == "low"

    def test_nested_ternary_bare(self) -> None:
        """Nested ternary without parentheses."""
        result = parse(
            'E +: [tier: ?: salary >= 80000 "high" ?: salary >= 60000 "mid" "low"]'
        )
        assert isinstance(result, ast.Extend)
        comp = result.computations[0]
        assert isinstance(comp.expr, ast.TernaryExpr)
        assert comp.expr.true_expr.value == "high"
        assert isinstance(comp.expr.false_expr, ast.TernaryExpr)
        inner = comp.expr.false_expr
        assert inner.true_expr.value == "mid"
        assert inner.false_expr.value == "low"


class TestRound:
    """Test ~ (precision) parsing."""

    def test_round_in_extend(self) -> None:
        """Precision primitive on a binary expression parses correctly."""
        result = parse("R +: pct: value / total ~ 2")
        assert isinstance(result, ast.Extend)
        comp = result.computations[0]
        assert comp.name == "pct"
        assert isinstance(comp.expr, ast.Round)
        assert comp.expr.places == 2
        assert isinstance(comp.expr.expr, ast.BinOp)
        assert comp.expr.expr.op == "/"

    def test_round_simple_attr(self) -> None:
        """Precision primitive on a single attribute reference."""
        result = parse("R +: x: salary ~ 0")
        assert isinstance(result, ast.Extend)
        comp = result.computations[0]
        assert isinstance(comp.expr, ast.Round)
        assert comp.expr.places == 0
        assert isinstance(comp.expr.expr, ast.AttrRef)

    def test_round_with_aggregate(self) -> None:
        """Precision primitive wrapping an aggregate expression."""
        result = parse("R /. avg: %. salary ~ 2")
        assert isinstance(result, ast.SummarizeAll)
        comp = result.computations[0]
        assert isinstance(comp.expr, ast.Round)
        assert comp.expr.places == 2
        assert isinstance(comp.expr.expr, ast.AggregateCall)
        assert comp.expr.expr.func == "%."


class TestErrors:
    """Test parse error handling."""

    def test_unexpected_token(self) -> None:
        """ParseError on input starting with an operator."""
        with pytest.raises(ParseError):
            parse("? salary > 50000")

    def test_missing_closing_bracket(self) -> None:
        """ParseError on unclosed bracket in projection."""
        with pytest.raises(ParseError):
            parse("E # [name salary")


class TestSchemaOp:
    """Test :: (schema) operator parsing."""

    def test_apply_schema(self) -> None:
        """R :: S parses as ApplySchema."""
        result = parse("R :: S")
        assert isinstance(result, ast.ApplySchema)
        assert isinstance(result.source, ast.RelName)
        assert result.source.name == "R"
        assert isinstance(result.schema_rel, ast.RelName)
        assert result.schema_rel.name == "S"

    def test_extract_schema(self) -> None:
        """R :: (no RHS) parses as ExtractSchema."""
        result = parse("R ::")
        assert isinstance(result, ast.ExtractSchema)
        assert isinstance(result.source, ast.RelName)
        assert result.source.name == "R"

    def test_apply_schema_with_literal(self) -> None:
        """R :: {attr type; ...} parses as ApplySchema with literal RHS."""
        result = parse('R :: {attr type; "salary" "int"}')
        assert isinstance(result, ast.ApplySchema)
        assert isinstance(result.schema_rel, ast.RelationLiteral)

    def test_schema_chains_after_filter(self) -> None:
        """Schema op chains after other operators."""
        result = parse('R ? salary > 50000 :: S')
        assert isinstance(result, ast.ApplySchema)
        assert isinstance(result.source, ast.Filter)

    def test_extract_schema_chains(self) -> None:
        """Extract schema chains after project."""
        result = parse("R # [name salary] ::")
        assert isinstance(result, ast.ExtractSchema)
        assert isinstance(result.source, ast.Project)


class TestMembershipOp:
    """Test in. (membership) operator parsing."""

    def test_attr_in_relation(self) -> None:
        """attr in. (R # col) parses as Filter with MembershipTest."""
        result = parse("R ? status in. (S # name)")
        assert isinstance(result, ast.Filter)
        cond = result.condition
        assert isinstance(cond, ast.MembershipTest)
        assert isinstance(cond.left, ast.AttrRef)
        assert cond.left.name == "status"
        assert isinstance(cond.rel_expr, ast.Project)

    def test_attr_in_bare_relation(self) -> None:
        """attr in. R (no postfix) parses — RHS is a bare relation name."""
        result = parse("R ? status in. S")
        assert isinstance(result, ast.Filter)
        cond = result.condition
        assert isinstance(cond, ast.MembershipTest)
        assert isinstance(cond.rel_expr, ast.RelName)

    def test_literal_in_relation(self) -> None:
        """Literal in. (R # col) parses as MembershipTest with literal LHS."""
        result = parse('R ? "abc" in. (S # foo)')
        assert isinstance(result, ast.Filter)
        cond = result.condition
        assert isinstance(cond, ast.MembershipTest)
        assert isinstance(cond.left, ast.StringLiteral)
        assert cond.left.value == "abc"

    def test_int_literal_in_relation(self) -> None:
        """Integer literal in. (R # col) parses correctly."""
        result = parse("R ? 42 in. (S # id)")
        assert isinstance(result, ast.Filter)
        cond = result.condition
        assert isinstance(cond, ast.MembershipTest)
        assert isinstance(cond.left, ast.IntLiteral)
        assert cond.left.value == 42

    def test_in_with_bool_combination(self) -> None:
        """in. works inside boolean combinations."""
        result = parse("R ? (status in. (S # name) & active = true)")
        assert isinstance(result, ast.Filter)
        cond = result.condition
        assert isinstance(cond, ast.BoolCombination)
        assert isinstance(cond.left, ast.MembershipTest)
