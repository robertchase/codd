# Line Continuation

## Goal

Allow long expressions to be broken across multiple lines for readability, using a trailing backslash (`\`) as the continuation character.

```
big = Employees \
  ? department = "Engineering" \
  | name, salary \
  >> salary
```

## Current state

The lexer already treats newlines as whitespace — `Lexer("E\n? salary")` tokenizes correctly. The limitation is in the REPL and script-mode runners, which process input one line at a time:

- **REPL**: reads a single line via `input()`, feeds it to the pipeline.
- **Script mode**: splits the file with `splitlines()`, processes each line independently.

Both intercept lines starting with `\` as backslash commands (`\load`, `\ops`, etc.) before the lexer sees them.

## Design

### Syntax

A trailing `\` (optionally followed by whitespace) at the end of a line means "this line continues on the next line." The `\` and the newline are replaced by a single space before the combined text reaches the lexer.

Only trailing `\` triggers continuation. A `\` at the start of a line remains a backslash command. A `\` mid-line (not currently possible) is unaffected.

### Where to implement

Add a **line-joining helper** that sits between raw input and the existing pipeline. Both the REPL and script-mode runners call it.

```python
def join_continuation(lines: Iterable[str]) -> Iterator[str]:
    """Yield logical lines, joining physical lines ending with backslash."""
    buf = ""
    for line in lines:
        stripped = line.rstrip()
        if stripped.endswith("\\"):
            buf += stripped[:-1] + " "
        else:
            buf += line
            yield buf
            buf = ""
    if buf:
        yield buf
```

### REPL changes

When the user enters a line ending with `\`, the REPL prompts for more input (with a `....> ` continuation prompt) instead of executing immediately. Lines accumulate until a line without a trailing `\` completes the expression.

```
codd> big = Employees \
....>   ? department = "Engineering" \
....>   | name, salary \
....>   >> salary
```

### Script-mode changes

In `_run_script`, replace the current `for line in lines` loop with iteration over `join_continuation(lines)`. No other changes needed — backslash-command detection still works because continuation lines are joined before dispatch.

### Comments and blank lines

- A comment (`-- ...`) on a continuation line is fine — the `--` through end-of-line is consumed by the lexer's whitespace skipper after joining.
- A blank continuation line (just `\`) is treated as joining with an empty segment — harmless, produces an extra space.

### Error handling

If a continuation line is the last line of a script (trailing `\` with no following line), `join_continuation` yields whatever was accumulated. The parser will likely produce an error on the incomplete expression, which is the correct behavior.

In the REPL, if the user is in continuation mode and sends EOF (Ctrl-D), the accumulated buffer is discarded — same as abandoning partial input.

## Scope

- `codd/repl/repl.py` — continuation prompt loop
- `codd/cli/__init__.py` — script-mode line joining
- New helper: `codd/repl/continuation.py` (or inline in repl.py)
- Tests for `join_continuation`, REPL continuation, and script-mode continuation
