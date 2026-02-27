# Scoping, Multi-Statement Execution, and User-Defined Operators

## Motivation

This expression fails:

```
E@[dept_id > d salary>s] /d x:+.s/(E/.+.s)
```

The subquery `(E/.+.s)` references the original `E`, which has `salary` not `s`. The rename only affects the outer chain. This is correct scoping, but there's no way to name the intermediate result and reference it in the subquery — Codd only supports single-statement execution today.

The fix works but is awkward — you must remember the original column name:

```
E@[dept_id > d salary>s] /d x:+.s/(E/.+.salary)
```

What we'd like to write:

```
S .= E@[dept_id > d salary>s]
S /d x:+.s/(S/.+.s)
```

This requires multi-statement execution and a scoping model.

## Scoping Model

Two binding forms:

- `:=` — **global scope**. Always assigns to the global environment. Persists across REPL lines, visible after file execution.
- `.=` — **local scope**. Assigns to the current local scope if one exists. If no local scope exists, falls through to global scope.

### Where scopes exist

| Context | Local scope? | `.=` behavior |
|---------|-------------|---------------|
| REPL line | No | Same as `:=` |
| `eval` | No | Same as `:=` |
| File (`run`) | Yes — the file body | Binding vanishes after file completes |
| Function body | Yes — the function body | Binding is local to the call |

### Rules

- Global bindings are visible everywhere.
- Local bindings shadow global ones within their scope.
- `:=` inside a local scope still writes to global (it "escapes" the scope).
- Nested scopes (future, via functions) see enclosing scopes — standard lexical scoping.

### File execution example

```
-- analysis.codd
S .= E@[dept_id > d salary>s]       -- local to file
Total .= S /. +.s                    -- local to file
Result := S /d x:+.s/(Total)        -- persists globally
```

After `run analysis.codd`: `Result` is in the environment; `S` and `Total` are gone.

## Multi-Statement Execution

### Statement separation

- **Newlines** separate statements.
- **Semicolons** are optional, for one-liners: `S .= E@[salary>s]; S /d +.s`
- Blank lines and comment-only lines are skipped.

### Result display

Open question: should the last expression in a file be automatically printed? In the REPL, every expression result is printed. For files, options:

1. Last expression printed (notebook/script feel)
2. Nothing printed unless assigned (pure pipeline feel)
3. All non-assignment expression results printed (REPL-like)

### Comments

Not yet in the language. Likely `--` line comments, but this is a separate design decision.

## File Execution

New CLI command:

```
uv run -m prototype.cli run script.codd [FILES...]
```

Loads CSVs/workspaces (like `eval`), then executes the `.codd` file as a sequence of statements in a local scope.

## User-Defined Operators

### Goal

A user-defined function should create a new operator that — like the built-in postfix ops — takes a relation and parameter(s) and emits a relation. It should feel like a natural extension of the chain syntax.

### Definition

A function is a value. Definition uses `func.` (a system-level operator, using the `.` suffix reserved for built-ins) followed by parameters and a `{}` delimited body:

```
pct_of_total := func. col {
  Total .= R /. +.col
  R /d x: +.col / (Total)
}
```

- **`func.`** introduces the function literal.
- **Parameters** follow `func.` with bracket elision: single param bare, multiple in `[]`, none omitted.
- **`{}`** delimits the body. Statements separated by newlines or `;`.
- **Last expression** is the return value — no explicit return keyword.
- **`R`** is the implicit input relation, automatically bound and local to the call. Not declared in the parameter list. Inside the body, `R` always refers to the relation the function was called on.

```
pct_of_total := func. col { ... }           -- one param
multi_param := func. [col1 col2] { ... }    -- multiple params
count_all := func. { R /. #. }              -- no params, one-liner
```

Since a function is a value assigned with `:=` or `.=`, scoping comes for free:

```
-- stats.codd (a library file)
helper .= func. col { R /. +.col }          -- local to file
pct_of_total := func. col {                  -- persists globally
  R /d x: +.col / (helper: col)
}
```

### Invocation

User-defined operators are invoked with `name:` at chain level, with bracket elision for arguments:

```
E@[dept_id > d salary>s] pct_of_total: s
E some_op: [col1 col2]
E count_all:
```

The `:` suffix distinguishes user-defined ops from system ops (which use `.` suffix like `#.`, `+.`). The `:` is also used for named expressions inside extend/summarize (`total: +.salary`), but the contexts are visually and syntactically distinct — the parser knows whether it's at chain level or inside a bracket group.

### Scoping

Function bodies follow the same scoping rules as everywhere else:

- `.=` writes to the function's local scope — bindings vanish after the call.
- `:=` escapes to global scope — useful for factory patterns where a function creates globally-visible bindings (e.g., a file that defines a library of functions).
- `R` is implicitly local. It shadows any global `R` for the duration of the call.

### Closures

The syntax is compatible with lexical closures (inner functions capturing bindings from enclosing scopes), but closures are **not in scope for the initial implementation**. The design does not preclude adding them later.

### Recursion and higher-order functions

Not needed now. The syntax does not preclude them.

## Grammar Changes (preliminary)

### New tokens

- `.=` — local assignment operator
- `func.` — function definition keyword
- `{` / `}` — function body delimiters
- Newline — becomes significant (statement separator) instead of whitespace
- `;` — optional statement separator
- `--` — line comment (tentative)

### New AST nodes

- `LocalAssignment(name, expr)` — `.=` binding
- `Program(statements: list[Statement])` — sequence of statements
- `FuncDef(params: list[str], body: Program)` — function literal
- `FuncCall(name: str, args: list[...], source: RelExpr)` — user-op invocation in postfix chain

### Parser changes

- `parse()` returns `Program` instead of single statement
- Newline/semicolon handling as statement boundary
- `.=` as alternative to `:=`
- `func.` after `:=` / `.=` triggers function definition parsing
- `IDENT COLON` at chain level triggers function call parsing (with bracket elision for args)

## Impact on REPL and eval

### REPL

No local scope — `.=` and `:=` are equivalent. Multi-statement per line supported via `;`:

```
codd> S .= E@[salary>s]; S /d +.s
```

The REPL already processes one input at a time; the only change is allowing `;` within a single input to chain statements.

### eval

Same as REPL — no local scope, `;` for multi-statement one-liners.

## Implementation Sketch

### Lexer

- Add `DOT_EQ` token for `.=`
- Add `FUNC_DOT` token for `func.`
- Add `LBRACE` / `RBRACE` tokens for `{` / `}`
- Add `SEMICOLON` token
- Add `NEWLINE` token (emitted instead of skipping `\n`)
- Add `COMMENT` handling (skip `--` to end of line)

### Parser

- New top-level `_parse_program()` that loops parsing statements until EOF
- Statement = assignment (`:=`), local assignment (`.=`), or expression
- Semicolons and newlines consumed as separators between statements
- When RHS of assignment is `func.`, parse function definition: optional params (bracket elision), then `{` body `}`
- In `_parse_postfix_chain`, when next tokens are `IDENT COLON`, parse as function call: consume name and `:`, then args (bracket elision)

### AST

- `LocalAssignment` node (parallel to `Assignment`)
- `Program` node (list of statements)
- `FuncDef` node (params + body as `Program`)
- `FuncCall` node (name + args + source relation)

### Environment

- Add scope support: stack of `dict[str, Relation]` frames
- `push_scope()` / `pop_scope()` for file and function execution
- `.=` writes to top frame; `:=` writes to bottom (global) frame
- `lookup()` walks the stack top-down
- Functions stored in the environment alongside relations

### Executor

- `execute()` handles `Program` by evaluating statements in sequence
- `LocalAssignment` binds in local scope
- File execution wraps in `push_scope()` / `pop_scope()`
- `FuncDef` evaluation stores the function value in the environment
- `FuncCall` evaluation: push scope, bind `R` to source relation, bind params to args, execute body, pop scope, return last result

### CLI

- New `run` subcommand: loads files, reads `.codd` script, executes as `Program`
