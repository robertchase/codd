"""Recursive descent parser for the relational algebra.

Grammar overview (informal):

  expr       := atom postfix*
  atom       := IDENT | '(' expr ')'
  postfix    := filter | project | join | nest_join | extend | rename
              | union | difference | intersect | summarize | summarize_all
              | nest_by | sort | take

The core loop is _parse_postfix_chain: parse an atom, then keep consuming
postfix operators left-to-right until none match.
"""

from __future__ import annotations

from prototype.lexer.tokens import Token, TokenType
from prototype.parser import ast_nodes as ast


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

    def parse(self) -> ast.RelExpr:
        """Parse the token stream into an AST."""
        result = self._parse_expr()
        if self._peek().type != TokenType.EOF:
            raise ParseError(
                f"Unexpected token {self._peek().value!r}", self._peek()
            )
        return result

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
        """Parse an atomic expression: IDENT or '(' expr ')'."""
        tok = self._peek()
        if tok.type == TokenType.IDENT:
            self._advance()
            return ast.RelName(name=tok.value)
        if tok.type == TokenType.LPAREN:
            self._advance()
            expr = self._parse_expr()
            self._expect(TokenType.RPAREN)
            return expr
        raise ParseError(f"Expected relation name or '(', got {tok.value!r}", tok)

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
            elif tok.type == TokenType.STAR:
                left = self._parse_natural_join(left)
            elif tok.type == TokenType.STAR_COLON:
                left = self._parse_nest_join(left)
            elif tok.type == TokenType.LT_COLON:
                left = self._parse_unnest(left)
            elif tok.type == TokenType.PLUS:
                left = self._parse_extend(left)
            elif tok.type == TokenType.AT:
                left = self._parse_rename(left)
            elif tok.type == TokenType.PIPE:
                left = self._parse_union(left)
            elif tok.type == TokenType.MINUS:
                left = self._parse_difference(left)
            elif tok.type == TokenType.AMPERSAND:
                left = self._parse_intersect(left)
            elif tok.type == TokenType.SLASH:
                left = self._parse_summarize(left)
            elif tok.type == TokenType.SLASH_DOT:
                left = self._parse_summarize_all(left)
            elif tok.type == TokenType.SLASH_COLON:
                left = self._parse_nest_by(left)
            elif tok.type == TokenType.DOLLAR:
                left = self._parse_sort(left)
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

    def _parse_natural_join(self, source: ast.RelExpr) -> ast.NaturalJoin:
        """Parse: * RelName."""
        self._advance()  # consume *
        right = self._parse_atom()
        return ast.NaturalJoin(source=source, right=right)

    def _parse_nest_join(self, source: ast.RelExpr) -> ast.NestJoin:
        """Parse: *: RelName > nest_name."""
        self._advance()  # consume *:
        right = self._parse_atom()
        self._expect(TokenType.GT)
        name_tok = self._expect(TokenType.IDENT)
        return ast.NestJoin(source=source, right=right, nest_name=name_tok.value)

    def _parse_unnest(self, source: ast.RelExpr) -> ast.Unnest:
        """Parse: <: attr_name."""
        self._advance()  # consume <:
        name_tok = self._expect(TokenType.IDENT)
        return ast.Unnest(source=source, nest_attr=name_tok.value)

    def _parse_extend(self, source: ast.RelExpr) -> ast.Extend:
        """Parse: + name: expr or + [name1: expr1  name2: expr2]."""
        self._advance()  # consume +
        computations = self._parse_named_expr_list()
        return ast.Extend(source=source, computations=tuple(computations))

    def _parse_rename(self, source: ast.RelExpr) -> ast.Rename:
        """Parse: @ old > new or @ [old1 > new1  old2 > new2]."""
        self._advance()  # consume @
        mappings = self._parse_rename_list()
        return ast.Rename(source=source, mappings=tuple(mappings))

    def _parse_union(self, source: ast.RelExpr) -> ast.Union:
        """Parse: | (right_expr)."""
        self._advance()  # consume |
        right = self._parse_binary_right()
        return ast.Union(source=source, right=right)

    def _parse_difference(self, source: ast.RelExpr) -> ast.Difference:
        """Parse: - (right_expr)."""
        self._advance()  # consume -
        right = self._parse_binary_right()
        return ast.Difference(source=source, right=right)

    def _parse_intersect(self, source: ast.RelExpr) -> ast.Intersect:
        """Parse: & (right_expr)."""
        self._advance()  # consume &
        right = self._parse_binary_right()
        return ast.Intersect(source=source, right=right)

    def _parse_summarize(self, source: ast.RelExpr) -> ast.Summarize:
        """Parse: / key [agg1: #. agg2: +. attr] or / [key1 key2] [aggs]."""
        self._advance()  # consume /
        group_attrs = self._parse_attr_list()
        aggregates = self._parse_aggregate_list()
        return ast.Summarize(
            source=source,
            group_attrs=group_attrs,
            aggregates=tuple(aggregates),
        )

    def _parse_summarize_all(self, source: ast.RelExpr) -> ast.SummarizeAll:
        """Parse: /. [agg1: #. agg2: +. attr]."""
        self._advance()  # consume /.
        aggregates = self._parse_aggregate_list()
        return ast.SummarizeAll(source=source, aggregates=tuple(aggregates))

    def _parse_nest_by(self, source: ast.RelExpr) -> ast.NestBy:
        """Parse: /: key > name or /: [key1 key2] > name."""
        self._advance()  # consume /:
        group_attrs = self._parse_attr_list()
        self._expect(TokenType.GT)
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
        """Parse: old > new or [old1 > new1  old2 > new2]."""
        if self._peek().type == TokenType.LBRACKET:
            self._advance()
            mappings: list[tuple[str, str]] = []
            while self._peek().type != TokenType.RBRACKET:
                old = self._expect(TokenType.IDENT).value
                self._expect(TokenType.GT)
                new = self._expect(TokenType.IDENT).value
                mappings.append((old, new))
            self._expect(TokenType.RBRACKET)
            return mappings
        else:
            old = self._expect(TokenType.IDENT).value
            self._expect(TokenType.GT)
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

    def _parse_named_expr_list(self) -> list[ast.NamedExpr]:
        """Parse: name: expr or [name1: expr1  name2: expr2]."""
        if self._peek().type == TokenType.LBRACKET:
            self._advance()
            exprs: list[ast.NamedExpr] = []
            while self._peek().type != TokenType.RBRACKET:
                named = self._parse_named_expr()
                exprs.append(named)
            self._expect(TokenType.RBRACKET)
            return exprs
        else:
            return [self._parse_named_expr()]

    def _parse_named_expr(self) -> ast.NamedExpr:
        """Parse: name: expr."""
        name_tok = self._expect(TokenType.IDENT)
        self._expect(TokenType.COLON)
        expr = self._parse_computation_expr()
        return ast.NamedExpr(name=name_tok.value, expr=expr)

    def _parse_aggregate_list(self) -> list[ast.NamedAggregate]:
        """Parse: [name1: agg_func  name2: agg_func attr]."""
        self._expect(TokenType.LBRACKET)
        aggregates: list[ast.NamedAggregate] = []
        while self._peek().type != TokenType.RBRACKET:
            agg = self._parse_named_aggregate()
            aggregates.append(agg)
        self._expect(TokenType.RBRACKET)
        return aggregates

    def _parse_named_aggregate(self) -> ast.NamedAggregate:
        """Parse: name: agg_func [attr].

        agg_func is one of: #., +., >., <., %.
        For #. the attr is optional (count tuples).
        For others, attr is required.
        A parenthesized subquery can provide the source relation:
          name: #. (team ? cond)
        Or a dotted reference like:
          name: >. team.salary
        """
        name_tok = self._expect(TokenType.IDENT)
        self._expect(TokenType.COLON)
        func_tok = self._advance()
        func_types = {
            TokenType.HASH_DOT, TokenType.PLUS_DOT,
            TokenType.GT_DOT, TokenType.LT_DOT, TokenType.PERCENT_DOT,
        }
        if func_tok.type not in func_types:
            raise ParseError(
                f"Expected aggregate function, got {func_tok.value!r}", func_tok
            )
        func = func_tok.value

        # Check for optional source/attr
        attr: str | None = None
        source: ast.RelExpr | None = None

        if self._peek().type == TokenType.LPAREN:
            # Conditional aggregate: #. (team ? role = "engineer")
            self._advance()  # (
            source = self._parse_expr()
            self._expect(TokenType.RPAREN)
        elif self._peek().type == TokenType.IDENT:
            # Could be: attr, or dotted: team.salary
            next_tok = self._peek()
            if self._peek(1).type == TokenType.DOT:
                # Dotted: team.salary -> source=team, attr=salary
                source_name = self._advance().value  # team
                self._advance()  # .
                attr_name = self._expect(TokenType.IDENT).value  # salary
                source = ast.RelName(name=source_name)
                attr = attr_name
            elif self._peek(1).type == TokenType.COLON:
                # Next named aggregate starts, so this is just an attr for #.
                # Actually the IDENT before COLON is the name of the next aggregate
                # So this current aggregate has no attr (count).
                pass
            else:
                attr = self._advance().value

        return ast.NamedAggregate(
            name=name_tok.value, func=func, attr=attr, source=source
        )

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
        """Parse: attr op value."""
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
        """Parse a computation expression (for extend).

        This is the context where * means multiply and / means divide.
        Supports: attr, literal, attr op attr, attr op literal.
        Supports aggregate calls: #. or +. salary etc.
        """
        # Check for aggregate calls first
        agg_types = {
            TokenType.HASH_DOT, TokenType.PLUS_DOT,
            TokenType.GT_DOT, TokenType.LT_DOT, TokenType.PERCENT_DOT,
        }
        if self._peek().type in agg_types:
            return self._parse_aggregate_call()

        left = self._parse_computation_atom()

        # Check for binary arithmetic
        arith_ops = {
            TokenType.STAR: "*",
            TokenType.SLASH: "/",
            TokenType.PLUS: "+",
            TokenType.MINUS: "-",
        }
        if self._peek().type in arith_ops:
            op_tok = self._advance()
            right = self._parse_computation_atom()
            return ast.BinOp(left=left, op=arith_ops[op_tok.type], right=right)

        return left

    def _parse_aggregate_call(self) -> ast.AggregateCall:
        """Parse an aggregate call in extend context: #. or +. salary or >. team.salary."""
        func_tok = self._advance()
        func = func_tok.value

        # Check for parenthesized source
        if self._peek().type == TokenType.LPAREN:
            self._advance()
            source = self._parse_expr()
            self._expect(TokenType.RPAREN)
            return ast.AggregateCall(func=func, source=source)

        # Check for dotted attr: team.salary
        if self._peek().type == TokenType.IDENT:
            if self._peek(1).type == TokenType.DOT and self._peek(2).type == TokenType.IDENT:
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
        """Parse an atomic computation value."""
        tok = self._peek()
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
        if tok.type == TokenType.IDENT:
            return self._parse_attr_ref()
        if tok.type == TokenType.LPAREN:
            self._advance()
            expr = self._parse_computation_expr()
            self._expect(TokenType.RPAREN)
            return expr
        raise ParseError(f"Expected value in computation, got {tok.value!r}", tok)
