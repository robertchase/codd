"""Recursive descent parser for the relational algebra.

Grammar overview (informal):

  expr       := atom postfix*
  atom       := IDENT | '(' expr ')'
  postfix    := filter | project | join | nest_join | extend | rename
              | union | difference | intersect | summarize
              | nest_by | sort | take

The core loop is _parse_postfix_chain: parse an atom, then keep consuming
postfix operators left-to-right until none match.
"""

from __future__ import annotations

from codd.lexer.tokens import Token, TokenType
from codd.parser import ast_nodes as ast


class ParseError(Exception):
    """Raised on parse errors."""

    def __init__(self, message: str, token: Token) -> None:
        super().__init__(f"Parse error at {token.line}:{token.col}: {message}")
        self.token = token


class Parser:
    """Recursive descent parser for the relational algebra."""

    def __init__(self, tokens: list[Token]) -> None:
        self._tokens = tokens
        self._pos = 0

    def parse(self) -> ast.RelExpr | ast.Assignment:
        """Parse the token stream into an AST.

        Checks for assignment (IDENT := expr) before parsing as expression.
        """
        if (
            self._peek().type == TokenType.IDENT
            and self._peek(1).type == TokenType.COLON_EQ
        ):
            return self._parse_assignment()

        result = self._parse_expr()
        if self._peek().type != TokenType.EOF:
            raise ParseError(
                f"Unexpected token {self._peek().value!r}", self._peek()
            )
        return result

    def _parse_assignment(self) -> ast.Assignment:
        """Parse: name := expr."""
        name_tok = self._advance()  # consume IDENT
        self._advance()  # consume :=
        expr = self._parse_expr()
        if self._peek().type != TokenType.EOF:
            raise ParseError(
                f"Unexpected token {self._peek().value!r}", self._peek()
            )
        return ast.Assignment(name=name_tok.value, expr=expr)

    # --- Token navigation ---

    def _peek(self, offset: int = 0) -> Token:
        """Look at a token without consuming it."""
        pos = self._pos + offset
        if pos >= len(self._tokens):
            return self._tokens[-1]  # EOF
        return self._tokens[pos]

    def _advance(self) -> Token:
        """Consume and return the current token."""
        tok = self._tokens[self._pos]
        self._pos += 1
        return tok

    def _expect(self, ttype: TokenType) -> Token:
        """Consume a token of the expected type, or raise."""
        tok = self._peek()
        if tok.type != ttype:
            raise ParseError(
                f"Expected {ttype.name}, got {tok.type.name} ({tok.value!r})", tok
            )
        return self._advance()

    def _match(self, *types: TokenType) -> Token | None:
        """Consume if the current token matches any of the given types."""
        if self._peek().type in types:
            return self._advance()
        return None

    # --- Expression parsing ---

    def _parse_expr(self) -> ast.RelExpr:
        """Parse a full expression (atom + postfix chain)."""
        left = self._parse_atom()
        return self._parse_postfix_chain(left)

    def _parse_atom(self) -> ast.RelExpr:
        """Parse an atomic expression: IDENT, '(' expr ')', or i. source."""
        tok = self._peek()
        if tok.type == TokenType.IDENT:
            self._advance()
            return ast.RelName(name=tok.value)
        if tok.type == TokenType.LPAREN:
            self._advance()
            expr = self._parse_expr()
            self._expect(TokenType.RPAREN)
            return expr
        if tok.type == TokenType.I_DOT:
            return self._parse_iota()
        raise ParseError(f"Expected relation name or '(', got {tok.value!r}", tok)

    def _parse_iota(self) -> ast.Iota:
        """Parse: i. [name:] COUNT.

        COUNT must be a literal positive integer.
        Optional name: prefix sets the attribute name (default 'i').
        """
        self._advance()  # consume i.
        name = "i"
        # Check for optional name: prefix (IDENT followed by COLON)
        if (
            self._peek().type == TokenType.IDENT
            and self._peek(1).type == TokenType.COLON
        ):
            name = self._advance().value  # consume IDENT
            self._advance()  # consume :
        tok = self._expect(TokenType.INTEGER)
        count = int(tok.value)
        if count <= 0:
            raise ParseError("i. count must be a positive integer", tok)
        return ast.Iota(count=count, name=name)

    def _parse_postfix_chain(self, left: ast.RelExpr) -> ast.RelExpr:
        """Parse a chain of postfix operators applied to left."""
        while True:
            tok = self._peek()

            if tok.type == TokenType.QUESTION:
                left = self._parse_filter(left)
            elif tok.type == TokenType.QUESTION_BANG:
                left = self._parse_negated_filter(left)
            elif tok.type == TokenType.HASH:
                left = self._parse_project(left)
            elif tok.type == TokenType.HASH_BANG:
                left = self._parse_remove(left)
            elif tok.type == TokenType.STAR_DOT:
                left = self._parse_natural_join(left)
            elif tok.type == TokenType.STAR_COLON:
                left = self._parse_nest_join(left)
            elif tok.type == TokenType.LT_COLON:
                left = self._parse_unnest(left)
            elif tok.type == TokenType.PLUS_COLON:
                left = self._parse_extend(left)
            elif tok.type == TokenType.EQUALS_COLON:
                left = self._parse_modify(left)
            elif tok.type == TokenType.AT:
                left = self._parse_rename(left)
            elif tok.type == TokenType.PIPE_DOT:
                left = self._parse_union(left)
            elif tok.type == TokenType.MINUS_DOT:
                left = self._parse_difference(left)
            elif tok.type == TokenType.AMPERSAND_DOT:
                left = self._parse_intersect(left)
            elif tok.type == TokenType.SLASH_DOT:
                left = self._parse_summarize(left)
            elif tok.type == TokenType.SLASH_COLON:
                left = self._parse_nest_by(left)
            elif tok.type == TokenType.DOLLAR:
                left = self._parse_sort(left)
            elif tok.type == TokenType.DOLLAR_DOT:
                left = self._parse_order_columns(left)
            elif tok.type == TokenType.CARET:
                left = self._parse_take(left)
            else:
                break
        return left

    # --- Postfix operator parsers ---

    def _parse_filter(self, source: ast.RelExpr) -> ast.Filter:
        """Parse: ? condition."""
        self._advance()  # consume ?
        condition = self._parse_condition()
        return ast.Filter(source=source, condition=condition)

    def _parse_negated_filter(self, source: ast.RelExpr) -> ast.NegatedFilter:
        """Parse: ?! condition."""
        self._advance()  # consume ?!
        condition = self._parse_condition()
        return ast.NegatedFilter(source=source, condition=condition)

    def _parse_project(self, source: ast.RelExpr) -> ast.Project:
        """Parse: # attr or # [attr1 attr2]."""
        self._advance()  # consume #
        attrs = self._parse_attr_list()
        return ast.Project(source=source, attrs=attrs)

    def _parse_remove(self, source: ast.RelExpr) -> ast.Remove:
        """Parse: #! attr or #! [attr1 attr2]."""
        self._advance()  # consume #!
        attrs = self._parse_attr_list()
        return ast.Remove(source=source, attrs=attrs)

    def _parse_natural_join(self, source: ast.RelExpr) -> ast.NaturalJoin:
        """Parse: *. RelName."""
        self._advance()  # consume *.
        right = self._parse_atom()
        return ast.NaturalJoin(source=source, right=right)

    def _parse_nest_join(self, source: ast.RelExpr) -> ast.NestJoin:
        """Parse: *: RelName -> nest_name."""
        self._advance()  # consume *:
        right = self._parse_atom()
        self._expect(TokenType.ARROW)
        name_tok = self._expect(TokenType.IDENT)
        return ast.NestJoin(source=source, right=right, nest_name=name_tok.value)

    def _parse_unnest(self, source: ast.RelExpr) -> ast.Unnest:
        """Parse: <: attr_name."""
        self._advance()  # consume <:
        name_tok = self._expect(TokenType.IDENT)
        return ast.Unnest(source=source, nest_attr=name_tok.value)

    def _parse_extend(self, source: ast.RelExpr) -> ast.Extend:
        """Parse: +: name: expr or +: [name1: expr1  name2: expr2]."""
        self._advance()  # consume +:
        computations = self._parse_named_expr_list()
        return ast.Extend(source=source, computations=tuple(computations))

    def _parse_modify(self, source: ast.RelExpr) -> ast.Modify:
        """Parse: =: name: expr or =: [name1: expr1  name2: expr2]."""
        self._advance()  # consume =:
        computations = self._parse_named_expr_list()
        return ast.Modify(source=source, computations=tuple(computations))

    def _parse_rename(self, source: ast.RelExpr) -> ast.Rename:
        """Parse: @ old -> new or @ [old1 -> new1  old2 -> new2]."""
        self._advance()  # consume @
        mappings = self._parse_rename_list()
        return ast.Rename(source=source, mappings=tuple(mappings))

    def _parse_union(self, source: ast.RelExpr) -> ast.Union:
        """Parse: |. (right_expr)."""
        self._advance()  # consume |.
        right = self._parse_binary_right()
        return ast.Union(source=source, right=right)

    def _parse_difference(self, source: ast.RelExpr) -> ast.Difference:
        """Parse: -. (right_expr)."""
        self._advance()  # consume -.
        right = self._parse_binary_right()
        return ast.Difference(source=source, right=right)

    def _parse_intersect(self, source: ast.RelExpr) -> ast.Intersect:
        """Parse: &. (right_expr)."""
        self._advance()  # consume &.
        right = self._parse_binary_right()
        return ast.Intersect(source=source, right=right)

    def _parse_summarize(
        self, source: ast.RelExpr
    ) -> ast.Summarize | ast.SummarizeAll:
        """Parse: /. key [aggs] or /. [aggs] (summarize-all).

        After consuming /., determines if grouping keys are present:
        - Next is aggregate token -> no key (summarize-all)
        - Next is IDENT followed by COLON -> named aggregate, no key
        - Next is LBRACKET with aggregate or IDENT COLON inside -> no key
        - Otherwise -> grouping keys present
        """
        self._advance()  # consume /.
        if self._is_summarize_all():
            computations = self._parse_named_expr_list(allow_auto_name=True)
            return ast.SummarizeAll(
                source=source, computations=tuple(computations)
            )
        group_attrs = self._parse_attr_list()
        computations = self._parse_named_expr_list(allow_auto_name=True)
        return ast.Summarize(
            source=source,
            group_attrs=group_attrs,
            computations=tuple(computations),
        )

    def _is_summarize_all(self) -> bool:
        """Determine whether the current position starts aggregates (no grouping key)."""
        tok = self._peek()
        # Direct aggregate token -> summarize-all
        if tok.type in self._AGG_TOKENS:
            return True
        # IDENT followed by COLON -> named aggregate (summarize-all)
        if tok.type == TokenType.IDENT and self._peek(1).type == TokenType.COLON:
            return True
        # LBRACKET -> peek inside
        if tok.type == TokenType.LBRACKET:
            inner = self._peek(1)
            if inner.type in self._AGG_TOKENS:
                return True
            if (
                inner.type == TokenType.IDENT
                and self._peek(2).type == TokenType.COLON
            ):
                return True
            return False
        return False

    def _parse_nest_by(self, source: ast.RelExpr) -> ast.NestBy:
        """Parse: /: key -> name or /: [key1 key2] -> name."""
        self._advance()  # consume /:
        group_attrs = self._parse_attr_list()
        self._expect(TokenType.ARROW)
        name_tok = self._expect(TokenType.IDENT)
        return ast.NestBy(
            source=source,
            group_attrs=group_attrs,
            nest_name=name_tok.value,
        )

    def _parse_sort(self, source: ast.RelExpr) -> ast.Sort:
        """Parse: $ key or $ key- or $ [key1 key2-]."""
        self._advance()  # consume $
        keys = self._parse_sort_key_list()
        return ast.Sort(source=source, keys=tuple(keys))

    def _parse_order_columns(self, source: ast.RelExpr) -> ast.OrderColumns:
        """Parse: $. col or $. [col1 col2 ...]."""
        self._advance()  # consume $.
        columns = self._parse_attr_list()
        return ast.OrderColumns(source=source, columns=columns)

    def _parse_take(self, source: ast.RelExpr) -> ast.Take:
        """Parse: ^ N."""
        self._advance()  # consume ^
        tok = self._expect(TokenType.INTEGER)
        return ast.Take(source=source, count=int(tok.value))

    # --- Helper parsers ---

    def _parse_binary_right(self) -> ast.RelExpr:
        """Parse the right side of a binary operator.

        Either a bare relation name or a parenthesized expression.
        """
        return self._parse_atom()

    def _parse_attr_list(self) -> tuple[str, ...]:
        """Parse: attr or [attr1 attr2 ...]."""
        if self._peek().type == TokenType.LBRACKET:
            self._advance()
            attrs: list[str] = []
            while self._peek().type != TokenType.RBRACKET:
                tok = self._expect(TokenType.IDENT)
                attrs.append(tok.value)
            self._expect(TokenType.RBRACKET)
            return tuple(attrs)
        else:
            tok = self._expect(TokenType.IDENT)
            return (tok.value,)

    def _parse_rename_list(self) -> list[tuple[str, str]]:
        """Parse: old -> new or [old1 -> new1  old2 -> new2]."""
        if self._peek().type == TokenType.LBRACKET:
            self._advance()
            mappings: list[tuple[str, str]] = []
            while self._peek().type != TokenType.RBRACKET:
                old = self._expect(TokenType.IDENT).value
                self._expect(TokenType.ARROW)
                new = self._expect(TokenType.IDENT).value
                mappings.append((old, new))
            self._expect(TokenType.RBRACKET)
            return mappings
        else:
            old = self._expect(TokenType.IDENT).value
            self._expect(TokenType.ARROW)
            new = self._expect(TokenType.IDENT).value
            return [(old, new)]

    def _parse_sort_key_list(self) -> list[ast.SortKey]:
        """Parse: key or key- or [key1 key2-]."""
        if self._peek().type == TokenType.LBRACKET:
            self._advance()
            keys: list[ast.SortKey] = []
            while self._peek().type != TokenType.RBRACKET:
                key = self._parse_sort_key()
                keys.append(key)
            self._expect(TokenType.RBRACKET)
            return keys
        else:
            return [self._parse_sort_key()]

    def _parse_sort_key(self) -> ast.SortKey:
        """Parse a single sort key: attr or attr-."""
        tok = self._expect(TokenType.IDENT)
        desc = False
        if self._peek().type == TokenType.MINUS:
            self._advance()
            desc = True
        return ast.SortKey(attr=tok.value, descending=desc)

    _AGG_TOKENS = {
        TokenType.HASH_DOT,
        TokenType.PLUS_DOT,
        TokenType.GT_DOT,
        TokenType.LT_DOT,
        TokenType.PERCENT_DOT,
        TokenType.N_DOT,
        TokenType.P_DOT,
    }

    _AGG_NAME_PREFIX: dict[str, str] = {
        "#.": "count",
        "+.": "sum",
        ">.": "max",
        "<.": "min",
        "%.": "mean",
        "n.": "collect",
        "p.": "pct",
    }

    def _parse_named_expr_list(
        self, *, allow_auto_name: bool = False
    ) -> list[ast.NamedExpr]:
        """Parse: name: expr or [name1: expr1  name2: expr2].

        When allow_auto_name is True (summarize context), aggregate
        expressions may omit the name: prefix and get auto-generated names.
        """
        if self._peek().type == TokenType.LBRACKET:
            self._advance()
            exprs: list[ast.NamedExpr] = []
            while self._peek().type != TokenType.RBRACKET:
                named = self._parse_maybe_named_expr(allow_auto_name)
                exprs.append(named)
            self._expect(TokenType.RBRACKET)
        else:
            exprs = [self._parse_maybe_named_expr(allow_auto_name)]
        if allow_auto_name:
            self._check_duplicate_names(exprs)
        return exprs

    def _parse_maybe_named_expr(
        self, allow_auto_name: bool
    ) -> ast.NamedExpr:
        """Parse a named or auto-named computation expression.

        If allow_auto_name is True and the next token is an aggregate,
        parse the expression and derive a column name from it.
        """
        if allow_auto_name and self._peek().type in self._AGG_TOKENS:
            tok = self._peek()
            expr = self._parse_computation_expr()
            if not isinstance(expr, ast.AggregateCall):
                raise ParseError(
                    "Complex expression requires an explicit name (name: expr)",
                    tok,
                )
            return ast.NamedExpr(name=self._auto_name(expr), expr=expr)
        return self._parse_named_expr()

    def _parse_named_expr(self) -> ast.NamedExpr:
        """Parse: name: expr."""
        name_tok = self._expect(TokenType.IDENT)
        self._expect(TokenType.COLON)
        expr = self._parse_computation_expr()
        return ast.NamedExpr(name=name_tok.value, expr=expr)

    def _auto_name(self, expr: ast.AggregateCall) -> str:
        """Derive a column name from a bare aggregate call."""
        prefix = self._AGG_NAME_PREFIX[expr.func]
        if expr.arg:
            return f"{prefix}_{expr.arg.name}"
        if expr.source and isinstance(expr.source, ast.RelName):
            return f"{prefix}_{expr.source.name}"
        return prefix

    def _check_duplicate_names(self, exprs: list[ast.NamedExpr]) -> None:
        """Raise on duplicate column names in a computation list."""
        seen: set[str] = set()
        for ne in exprs:
            if ne.name in seen:
                raise ParseError(
                    f"Duplicate column name {ne.name!r} in summarize",
                    self._peek(),
                )
            seen.add(ne.name)

    def _parse_condition(self) -> ast.Condition:
        """Parse a filter condition.

        Can be a simple comparison, or parenthesized with | and &.
        """
        if self._peek().type == TokenType.LPAREN:
            self._advance()
            cond = self._parse_bool_expr()
            self._expect(TokenType.RPAREN)
            return cond
        return self._parse_comparison()

    def _parse_bool_expr(self) -> ast.Condition:
        """Parse boolean expression inside parentheses: cond (& | |) cond."""
        left = self._parse_comparison()
        while self._peek().type in (TokenType.PIPE, TokenType.AMPERSAND):
            op_tok = self._advance()
            right = self._parse_comparison()
            left = ast.BoolCombination(left=left, op=op_tok.value, right=right)
        return left

    def _parse_comparison(self) -> ast.Comparison:
        """Parse: attr op value, or aggregate op value."""
        if self._peek().type in self._AGG_TOKENS:
            left: ast.AttrRef | ast.AggregateCall = self._parse_aggregate_call()
        else:
            left = self._parse_attr_ref()
        comp_ops = {
            TokenType.EQ: "=",
            TokenType.BANG_EQ: "!=",
            TokenType.GT: ">",
            TokenType.LT: "<",
            TokenType.GT_EQ: ">=",
            TokenType.LT_EQ: "<=",
        }
        tok = self._peek()
        if tok.type not in comp_ops:
            raise ParseError(
                f"Expected comparison operator, got {tok.value!r}", tok
            )
        self._advance()
        op = comp_ops[tok.type]
        right = self._parse_value_expr()
        return ast.Comparison(left=left, op=op, right=right)

    def _parse_attr_ref(self) -> ast.AttrRef:
        """Parse an attribute reference: ident or ident.ident."""
        parts: list[str] = []
        tok = self._expect(TokenType.IDENT)
        parts.append(tok.value)
        while self._peek().type == TokenType.DOT and self._peek(1).type == TokenType.IDENT:
            self._advance()  # consume .
            tok = self._expect(TokenType.IDENT)
            parts.append(tok.value)
        return ast.AttrRef(parts=tuple(parts))

    def _parse_value_expr(self) -> ast.Expr:
        """Parse a value expression on the RHS of a comparison."""
        tok = self._peek()
        if tok.type == TokenType.MINUS:
            # Unary minus for negative numeric literals
            if self._peek(1).type == TokenType.INTEGER:
                self._advance()  # consume -
                num_tok = self._advance()
                return ast.IntLiteral(value=-int(num_tok.value))
            if self._peek(1).type == TokenType.FLOAT:
                self._advance()  # consume -
                num_tok = self._advance()
                return ast.FloatLiteral(value=-float(num_tok.value))
        if tok.type == TokenType.INTEGER:
            self._advance()
            return ast.IntLiteral(value=int(tok.value))
        if tok.type == TokenType.FLOAT:
            self._advance()
            return ast.FloatLiteral(value=float(tok.value))
        if tok.type == TokenType.STRING:
            self._advance()
            return ast.StringLiteral(value=tok.value)
        if tok.type == TokenType.BOOLEAN:
            self._advance()
            return ast.BoolLiteral(value=tok.value == "true")
        if tok.type == TokenType.LBRACE:
            return self._parse_set_literal()
        if tok.type == TokenType.LPAREN:
            # Subquery in filter RHS
            self._advance()
            query = self._parse_expr()
            self._expect(TokenType.RPAREN)
            return ast.SubqueryExpr(query=query)
        if tok.type == TokenType.IDENT:
            return self._parse_attr_ref()
        raise ParseError(f"Expected value, got {tok.value!r}", tok)

    def _parse_set_literal(self) -> ast.SetLiteral:
        """Parse: {value1, value2, ...}."""
        self._expect(TokenType.LBRACE)
        elements: list[ast.Expr] = []
        while self._peek().type != TokenType.RBRACE:
            elements.append(self._parse_value_expr())
            if self._peek().type == TokenType.COMMA:
                self._advance()
        self._expect(TokenType.RBRACE)
        return ast.SetLiteral(elements=tuple(elements))

    def _parse_computation_expr(self) -> ast.Expr:
        """Parse a computation expression.

        All operators evaluate left-to-right with no precedence (like the
        relational chain).  Use parentheses to override:
        ``salary + bonus * 2`` means ``(salary + bonus) * 2``.
        """
        # Check for ternary expression
        if self._peek().type == TokenType.QUESTION_COLON:
            return self._parse_ternary_expr()

        return self._parse_left_to_right_expr()

    _ARITH_OPS: dict[TokenType, str] = {
        TokenType.PLUS: "+",
        TokenType.MINUS: "-",
        TokenType.STAR: "*",
        TokenType.SLASH: "/",
    }

    def _parse_left_to_right_expr(self) -> ast.Expr:
        """Parse arithmetic left-to-right: atom (op atom)* with no precedence.

        Handles +, -, *, / and ~ (precision) all at the same level.
        """
        left = self._parse_computation_atom()
        while True:
            if self._peek().type == TokenType.TILDE:
                self._advance()  # consume ~
                tok = self._expect(TokenType.INTEGER)
                left = ast.Round(expr=left, places=int(tok.value))
            elif self._peek().type == TokenType.S_DOT:
                self._advance()  # consume s.
                left = self._parse_substring(left)
            elif self._peek().type == TokenType.D_DOT:
                self._advance()  # consume .d
                left = self._parse_date_op(left)
            elif self._peek().type in self._ARITH_OPS:
                op_tok = self._advance()
                right = self._parse_computation_atom()
                left = ast.BinOp(
                    left=left, op=self._ARITH_OPS[op_tok.type], right=right
                )
            else:
                break
        return left

    def _parse_substring(self, expr: ast.Expr) -> ast.Substring:
        """Parse: .s [start] or .s [start end].

        Indices are integers, optionally negative (MINUS INTEGER).
        """
        self._expect(TokenType.LBRACKET)
        start = self._parse_signed_int()
        end: int | None = None
        if self._peek().type in (TokenType.INTEGER, TokenType.MINUS):
            end = self._parse_signed_int()
        self._expect(TokenType.RBRACKET)
        return ast.Substring(expr=expr, start=start, end=end)

    def _parse_signed_int(self) -> int:
        """Parse an optionally negative integer: INTEGER or MINUS INTEGER."""
        if self._peek().type == TokenType.MINUS:
            self._advance()  # consume -
            tok = self._expect(TokenType.INTEGER)
            return -int(tok.value)
        tok = self._expect(TokenType.INTEGER)
        return int(tok.value)

    def _parse_date_op(self, expr: ast.Expr) -> ast.DateOp:
        """Parse: .d or .d 'fmt'.

        If a string literal follows, it is the format/extraction specifier.
        Otherwise it is a bare promotion (string → Date).
        """
        fmt: str | None = None
        if self._peek().type == TokenType.STRING:
            fmt = self._advance().value
        return ast.DateOp(expr=expr, fmt=fmt)

    def _parse_ternary_expr(self) -> ast.TernaryExpr:
        """Parse: ?: condition true_expr false_expr."""
        self._advance()  # consume ?:
        condition = self._parse_comparison()
        true_expr = self._parse_ternary_branch()
        false_expr = self._parse_ternary_branch()
        return ast.TernaryExpr(
            condition=condition, true_expr=true_expr, false_expr=false_expr
        )

    def _parse_ternary_branch(self) -> ast.Expr:
        """Parse a single branch of a ternary expression.

        Handles atoms, aggregate calls, and nested ternaries.
        Binary arithmetic in branches requires parentheses.
        """
        if self._peek().type == TokenType.QUESTION_COLON:
            return self._parse_ternary_expr()
        return self._parse_computation_atom()

    def _parse_aggregate_call(self) -> ast.AggregateCall:
        """Parse an aggregate call: #. or +. salary or >. team.salary.

        Aggregates participate in arithmetic as atoms, so this is called from
        _parse_computation_atom.
        """
        func_tok = self._advance()
        func = func_tok.value

        # Check for parenthesized source
        if self._peek().type == TokenType.LPAREN:
            self._advance()
            source = self._parse_expr()
            self._expect(TokenType.RPAREN)
            return ast.AggregateCall(func=func, source=source)

        # Check for IDENT argument
        if self._peek().type == TokenType.IDENT:
            # If the IDENT is followed by COLON, it's the name of the next
            # named expression, not an argument to this aggregate.
            if self._peek(1).type == TokenType.COLON:
                return ast.AggregateCall(func=func)
            if self._peek(1).type == TokenType.DOT and self._peek(2).type == TokenType.IDENT:
                # Dotted: team.salary -> source=team, attr=salary
                source_name = self._advance().value
                self._advance()  # .
                attr_name = self._advance().value
                return ast.AggregateCall(
                    func=func,
                    arg=ast.AttrRef(parts=(attr_name,)),
                    source=ast.RelName(name=source_name),
                )
            # For #. (count), a bare identifier is the source RVA to count
            if func == "#.":
                source_name = self._advance().value
                return ast.AggregateCall(
                    func=func,
                    source=ast.RelName(name=source_name),
                )
            # For other aggregates, bare identifier is the attribute
            attr_tok = self._advance()
            return ast.AggregateCall(
                func=func, arg=ast.AttrRef(parts=(attr_tok.value,))
            )

        # No arg (count)
        return ast.AggregateCall(func=func)

    def _parse_computation_atom(self) -> ast.Expr:
        """Parse an atomic computation value.

        Handles literals, attribute references, function calls, aggregate
        calls, parenthesized expressions, and parenthesized relational
        subqueries (with backtracking).
        """
        tok = self._peek()
        if tok.type == TokenType.MINUS:
            # Unary minus for negative numeric literals
            if self._peek(1).type == TokenType.INTEGER:
                self._advance()  # consume -
                num_tok = self._advance()
                return ast.IntLiteral(value=-int(num_tok.value))
            if self._peek(1).type == TokenType.FLOAT:
                self._advance()  # consume -
                num_tok = self._advance()
                return ast.FloatLiteral(value=-float(num_tok.value))
        if tok.type == TokenType.INTEGER:
            self._advance()
            return ast.IntLiteral(value=int(tok.value))
        if tok.type == TokenType.FLOAT:
            self._advance()
            return ast.FloatLiteral(value=float(tok.value))
        if tok.type == TokenType.STRING:
            self._advance()
            return ast.StringLiteral(value=tok.value)
        if tok.type == TokenType.BOOLEAN:
            self._advance()
            return ast.BoolLiteral(value=tok.value == "true")
        if tok.type in self._AGG_TOKENS:
            return self._parse_aggregate_call()
        if tok.type == TokenType.IDENT:
            return self._parse_attr_ref()
        if tok.type == TokenType.LPAREN:
            self._advance()
            saved_pos = self._pos
            try:
                expr = self._parse_computation_expr()
                self._expect(TokenType.RPAREN)
                return expr
            except ParseError:
                self._pos = saved_pos
                query = self._parse_expr()
                self._expect(TokenType.RPAREN)
                return ast.SubqueryExpr(query=query)
        raise ParseError(f"Expected value in computation, got {tok.value!r}", tok)

