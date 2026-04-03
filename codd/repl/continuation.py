"""Line continuation: join physical lines ending with backslash."""

from __future__ import annotations

from collections.abc import Iterable, Iterator


def join_continuation(lines: Iterable[str]) -> Iterator[str]:
    """Yield logical lines, joining physical lines that end with ``\\``.

    A trailing backslash (optionally followed by whitespace) signals that
    the next physical line continues the current logical line.  The
    backslash and newline are replaced by a single space.

    >>> list(join_continuation(["a \\\\", "  b"]))
    ['a  b']
    """
    buf = ""
    for line in lines:
        stripped = line.rstrip()
        # Skip full-line -- comments (even inside a continuation block).
        if stripped.lstrip().startswith("--"):
            continue
        if stripped.endswith("\\"):
            buf += stripped[:-1]
        else:
            buf += line
            yield buf
            buf = ""
    # Unterminated continuation — yield whatever accumulated.
    if buf:
        yield buf
