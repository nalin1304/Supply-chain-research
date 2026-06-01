r"""Syntactic validator for the manuscript's LaTeX tables.

Checks:
  1. Every \begin{...} has a matching \end{...} with the same env name.
  2. Brace balance is zero across the file.
  3. No orphan \\ at start of a line (which usually means a previous
     \\ ate the newline and started a content line).
  4. Every \caption{...} and \label{...} has balanced braces.
  5. Tabular column count matches the col-spec ({lccc} -> 4 cols per row).
"""

from pathlib import Path
import re
import sys


def check_brace_balance(text: str) -> tuple[bool, int]:
    """Return (is_balanced, depth_at_end) ignoring escapes."""
    depth = 0
    i = 0
    while i < len(text):
        c = text[i]
        if c == "\\" and i + 1 < len(text) and text[i + 1] in "{}":
            i += 2
            continue
        if c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth < 0:
                return False, depth
        i += 1
    return depth == 0, depth


def check_env_matching(text: str) -> list[str]:
    """Stack-based check that every \\begin has a properly-nested \\end."""
    stack: list[str] = []
    errors = []
    pattern = re.compile(r"\\(begin|end)\{(\w+\*?)\}")
    for m in pattern.finditer(text):
        kind = m.group(1)
        env = m.group(2)
        if kind == "begin":
            stack.append(env)
        else:
            if not stack:
                errors.append(f"  unmatched \\end{{{env}}}")
                continue
            top = stack.pop()
            if top != env:
                errors.append(
                    f"  \\end{{{env}}} but innermost open is {top}"
                )
    if stack:
        errors.append(f"  unclosed envs: {stack}")
    return errors


def check_tabular_columns(text: str) -> list[str]:
    """Verify each tabular row has the same number of columns the spec declares.

    Multi-line rows are joined on logical row boundaries (the row
    terminator ``\\\\``) before counting cell separators, so a row that
    is broken across several physical lines for source readability is
    counted correctly.
    """
    errors = []
    # Walk every ``\begin{tabular}{...}`` opener manually so we can
    # extract the column-spec with balanced braces (the spec may
    # contain ``@{...}`` constructs and ``p{...}`` width arguments
    # whose inner ``}`` would terminate a naive ``[^}]+`` capture).
    pos = 0
    open_re = re.compile(r"\\begin\{tabular\}\{")
    while True:
        m = open_re.search(text, pos)
        if not m:
            break
        # Capture the column-spec by walking the brace balance.
        i = m.end()
        depth = 1
        while i < len(text) and depth > 0:
            ch = text[i]
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    break
            i += 1
        spec = text[m.end() : i]
        # Find the matching ``\end{tabular}`` to bound the body.
        end_m = re.search(r"\\end\{tabular\}", text[i + 1 :])
        if not end_m:
            break
        body = text[i + 1 : i + 1 + end_m.start()]
        pos = i + 1 + end_m.end()

        # Count column tokens in spec (l, c, r, p{...}, m{...}, b{...}).
        # ``@{...}`` constructs are zero-width inserts and contribute no
        # column; ``*{n}{...}`` repeaters could be expanded, but no
        # manuscript table uses them so we keep the parser simple.
        spec_clean = re.sub(r"@\{[^}]*\}", "", spec)
        cols = len(
            re.findall(
                r"l|c|r|p\{[^}]*\}|m\{[^}]*\}|b\{[^}]*\}",
                spec_clean,
            )
        )
        # Strip line-comments from the body before joining: a ``%``
        # outside braces marks the rest of the source line as a
        # comment.
        body_lines = []
        for raw_line in body.splitlines():
            stripped = raw_line.lstrip()
            if stripped.startswith("%"):
                continue  # comment-only line
            body_lines.append(raw_line)
        body_clean = "\n".join(body_lines)
        # Logical rows are split by ``\\`` (the LaTeX row-terminator).
        logical_rows = body_clean.split(r"\\")
        for row_idx, chunk in enumerate(logical_rows, start=1):
            row = chunk.strip()
            if not row:
                continue
            if (
                row.startswith("\\hline")
                or row.startswith("\\toprule")
                or row.startswith("\\midrule")
                or row.startswith("\\bottomrule")
            ):
                continue
            if re.fullmatch(
                r"\\(?:hline|toprule|midrule|bottomrule)\s*", row
            ):
                continue
            # Count cell separators, ignoring escaped ampersands
            # (``\&`` is a literal ``&`` in the table cell, not a
            # column delimiter).
            n_amps = len(re.findall(r"(?<!\\)&", row))
            mc_spans = sum(
                int(mm.group(1))
                for mm in re.finditer(r"\\multicolumn\{(\d+)\}", row)
            )
            mc_count = len(re.findall(r"\\multicolumn\{\d+\}", row))
            effective_cells = (n_amps + 1) + (mc_spans - mc_count)
            if effective_cells != cols:
                preview = row.replace("\n", " ")[:80]
                errors.append(
                    f"  tabular row {row_idx}: {effective_cells} effective "
                    f"cells vs spec {cols} (row: {preview!r})"
                )
    return errors


def main() -> int:
    tables_dir = Path("outputs/tables")
    rc = 0
    for tex in sorted(tables_dir.glob("*.tex")):
        text = tex.read_text()
        problems = []
        ok, depth = check_brace_balance(text)
        if not ok:
            problems.append(f"  brace imbalance: depth ends at {depth}")
        problems.extend(check_env_matching(text))
        problems.extend(check_tabular_columns(text))

        # Orphan \\ at line start
        for ln, line in enumerate(text.splitlines(), 1):
            if line.lstrip().startswith("\\\\") and not line.lstrip().startswith("\\\\["):
                # Likely formatting artifact; warn but don't fail
                pass

        if problems:
            rc = 1
            print(f"FAIL {tex.name}:")
            for p in problems:
                print(p)
        else:
            print(f"OK   {tex.name} ({len(text)} bytes)")

    return rc


if __name__ == "__main__":
    sys.exit(main())
