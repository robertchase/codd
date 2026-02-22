"""Tests for the parser."""

from prototype.lexer.lexer import Lexer
from prototype.parser.parser import Parser, ParseError
from prototype.parser import ast_nodes as ast
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
        result = parse('E * D ? dept_name = "Engineering" # [name salary]')
        assert isinstance(result, ast.Project)
        assert isinstance(result.source, ast.Filter)
        assert isinstance(result.source.source, ast.NaturalJoin)


class TestJoin:
    """Test join parsing."""

    def test_natural_join(self) -> None:
        """Natural join between two relations."""
        result = parse("E * D")
        assert isinstance(result, ast.NaturalJoin)
        assert isinstance(result.right, ast.RelName)
        assert result.right.name == "D"

    def test_nest_join(self) -> None:
        """Nest join with target nest name."""
        result = parse("E *: Phone > phones")
        assert isinstance(result, ast.NestJoin)
        assert isinstance(result.right, ast.RelName)
        assert result.nest_name == "phones"


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
        result = parse("E *: Phone > phones <: phones")
        assert isinstance(result, ast.Unnest)
        assert result.nest_attr == "phones"
        assert isinstance(result.source, ast.NestJoin)


class TestExtend:
    """Test extend parsing."""

    def test_single(self) -> None:
        """Single computed column with arithmetic expression."""
        result = parse("E + bonus: salary * 0.1")
        assert isinstance(result, ast.Extend)
        assert len(result.computations) == 1
        comp = result.computations[0]
        assert comp.name == "bonus"
        assert isinstance(comp.expr, ast.BinOp)
        assert comp.expr.op == "*"

    def test_multiple(self) -> None:
        """Multiple bracketed computed columns."""
        result = parse("E + [bonus: salary * 0.1  tax: salary * 0.3]")
        assert isinstance(result, ast.Extend)
        assert len(result.computations) == 2
        assert result.computations[0].name == "bonus"
        assert result.computations[1].name == "tax"


class TestArithmeticPrecedence:
    """Test arithmetic chaining and operator precedence in extend."""

    def test_chained_multiply_divide(self) -> None:
        """a / b * 2 parses as (a / b) * 2 (left-to-right)."""
        result = parse("R + x: a / b * 2")
        assert isinstance(result, ast.Extend)
        expr = result.computations[0].expr
        assert isinstance(expr, ast.BinOp)
        assert expr.op == "*"
        assert isinstance(expr.left, ast.BinOp)
        assert expr.left.op == "/"
        assert isinstance(expr.right, ast.IntLiteral)
        assert expr.right.value == 2

    def test_multiply_before_add(self) -> None:
        """a + b * 2 parses as a + (b * 2) (precedence)."""
        result = parse("R + x: a + b * 2")
        assert isinstance(result, ast.Extend)
        expr = result.computations[0].expr
        assert isinstance(expr, ast.BinOp)
        assert expr.op == "+"
        assert isinstance(expr.left, ast.AttrRef)
        assert isinstance(expr.right, ast.BinOp)
        assert expr.right.op == "*"

    def test_chained_additive(self) -> None:
        """a + b - c parses as (a + b) - c."""
        result = parse("R + x: a + b - c")
        assert isinstance(result, ast.Extend)
        expr = result.computations[0].expr
        assert isinstance(expr, ast.BinOp)
        assert expr.op == "-"
        assert isinstance(expr.left, ast.BinOp)
        assert expr.left.op == "+"

    def test_parens_override_precedence(self) -> None:
        """(a + b) * 2 groups addition first via parentheses."""
        result = parse("R + x: (a + b) * 2")
        assert isinstance(result, ast.Extend)
        expr = result.computations[0].expr
        assert isinstance(expr, ast.BinOp)
        assert expr.op == "*"
        assert isinstance(expr.left, ast.BinOp)
        assert expr.left.op == "+"


class TestRename:
    """Test rename parsing."""

    def test_single(self) -> None:
        """Single attribute rename mapping."""
        result = parse("E @ pay > salary")
        assert isinstance(result, ast.Rename)
        assert result.mappings == (("pay", "salary"),)

    def test_multiple(self) -> None:
        """Multiple bracketed rename mappings."""
        result = parse("E @ [pay > salary  dept > department]")
        assert isinstance(result, ast.Rename)
        assert len(result.mappings) == 2


class TestSetOps:
    """Test set operation parsing."""

    def test_union(self) -> None:
        """Union of two relations."""
        result = parse("E | (D)")
        assert isinstance(result, ast.Union)

    def test_difference(self) -> None:
        """Set difference of two projected relations."""
        result = parse("E # emp_id - (Phone # emp_id)")
        assert isinstance(result, ast.Difference)
        assert isinstance(result.source, ast.Project)

    def test_intersect(self) -> None:
        """Set intersection of two projected relations."""
        result = parse("(E # emp_id) & (Phone # emp_id)")
        assert isinstance(result, ast.Intersect)


class TestSummarize:
    """Test summarize parsing."""

    def test_single_key(self) -> None:
        """Summarize with one group key and two aggregates."""
        result = parse("E / dept_id [n: #.  avg: %. salary]")
        assert isinstance(result, ast.Summarize)
        assert result.group_attrs == ("dept_id",)
        assert len(result.aggregates) == 2
        assert result.aggregates[0].name == "n"
        assert result.aggregates[0].func == "#."
        assert result.aggregates[1].name == "avg"
        assert result.aggregates[1].func == "%."
        assert result.aggregates[1].attr == "salary"

    def test_single_aggregate_no_brackets(self) -> None:
        """Summarize with one aggregate without brackets."""
        result = parse("E / dept_id total: +. salary")
        assert isinstance(result, ast.Summarize)
        assert result.group_attrs == ("dept_id",)
        assert len(result.aggregates) == 1
        assert result.aggregates[0].name == "total"
        assert result.aggregates[0].func == "+."
        assert result.aggregates[0].attr == "salary"

    def test_summarize_all_no_brackets(self) -> None:
        """Summarize-all with a single aggregate, no brackets."""
        result = parse("E /. n: #.")
        assert isinstance(result, ast.SummarizeAll)
        assert len(result.aggregates) == 1
        assert result.aggregates[0].name == "n"
        assert result.aggregates[0].func == "#."

    def test_summarize_all(self) -> None:
        """Summarize-all with multiple bracketed aggregates."""
        result = parse("E /. [n: #.  total: +. salary]")
        assert isinstance(result, ast.SummarizeAll)
        assert len(result.aggregates) == 2

    def test_nest_by(self) -> None:
        """Nest-by groups and assigns a nest name."""
        result = parse("E /: dept_id > team")
        assert isinstance(result, ast.NestBy)
        assert result.group_attrs == ("dept_id",)
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
        result = parse("ContractorPay @ [pay > salary] | (E # [name salary])")
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
        result = parse("E /: dept_id > team + [top: >. team.salary]")
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


class TestTernaryParsing:
    """Test ternary expression parsing."""

    def test_basic_ternary(self) -> None:
        """Basic ternary with comparison, true, and false branches."""
        result = parse('E + [grp: ? dept_id = 10 "eng" "other"]')
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
            'E + [tier: ? salary >= 80000 "high" (? salary >= 60000 "mid" "low")]'
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
            'E + [tier: ? salary >= 80000 "high" ? salary >= 60000 "mid" "low"]'
        )
        assert isinstance(result, ast.Extend)
        comp = result.computations[0]
        assert isinstance(comp.expr, ast.TernaryExpr)
        assert comp.expr.true_expr.value == "high"
        assert isinstance(comp.expr.false_expr, ast.TernaryExpr)
        inner = comp.expr.false_expr
        assert inner.true_expr.value == "mid"
        assert inner.false_expr.value == "low"


class TestFunctionCall:
    """Test function call parsing."""

    def test_function_call_in_extend(self) -> None:
        """Function call wrapping a binary expression parses correctly."""
        result = parse("R + pct: round(value / total, 2)")
        assert isinstance(result, ast.Extend)
        comp = result.computations[0]
        assert comp.name == "pct"
        assert isinstance(comp.expr, ast.FunctionCall)
        assert comp.expr.name == "round"
        assert len(comp.expr.args) == 2
        assert isinstance(comp.expr.args[0], ast.BinOp)
        assert comp.expr.args[0].op == "/"
        assert isinstance(comp.expr.args[1], ast.IntLiteral)
        assert comp.expr.args[1].value == 2

    def test_function_call_no_args(self) -> None:
        """Function call with no arguments parses correctly."""
        result = parse("R + x: foo()")
        assert isinstance(result, ast.Extend)
        comp = result.computations[0]
        assert isinstance(comp.expr, ast.FunctionCall)
        assert comp.expr.name == "foo"
        assert comp.expr.args == ()

    def test_function_call_single_arg(self) -> None:
        """Function call with a single argument parses correctly."""
        result = parse("R + x: abs(salary)")
        assert isinstance(result, ast.Extend)
        comp = result.computations[0]
        assert isinstance(comp.expr, ast.FunctionCall)
        assert comp.expr.name == "abs"
        assert len(comp.expr.args) == 1
        assert isinstance(comp.expr.args[0], ast.AttrRef)


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
