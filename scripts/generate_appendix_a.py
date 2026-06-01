"""Generate the Appendix A parameter table for the manuscript.

This script walks the :class:`supply_chain_research.config.MasterConfig`
pydantic model tree and emits a 4-column markdown table — *parameter*,
*value*, *units*, *source* — into ``docs/appendix_a_parameters.md``.

The output is fully deterministic: given the same ``config.py`` the
table is byte-identical on every run. There is no RNG path, no time
stamp, and no environment-dependent state. The traversal order
follows :pyattr:`pydantic.BaseModel.model_fields`, which preserves
the declaration order in the source file (Python ≥3.7 dict
ordering), so the table is also stable across reorderings of unrelated
sub-configs.

Notes
-----
For each scalar (non-``BaseModel``) leaf, the script reports

* **parameter** — the dotted path from ``MasterConfig`` (e.g.
  ``vehicle.hcv_k`` or ``network.warehouse_capacities``);
* **value** — the resolved default, taken from the live
  ``MasterConfig()`` instance so that ``default_factory`` callables
  are evaluated;
* **units** — extracted from the pydantic ``Field(description=...)``
  metadata when present, otherwise empty (per Appendix A spec);
* **source** — the inline ``# ...`` comment that sits on the same
  source line as the field assignment in ``config.py`` (one-line
  AST extract; multi-line citation blocks are not flattened).

The MasterConfig docstring (Audit 2.1, parameter taxonomy: PHYSICS
DERIVED / PROBLEM SCALED / TUNED) tags every parameter; this script
preserves those tags via the *source* column whenever the inline
comment carries them. See
:class:`supply_chain_research.config.MasterConfig` for the
authoritative parameter inventory.

Examples
--------
>>> python scripts/generate_appendix_a.py
Wrote 213 parameter rows to .../docs/appendix_a_parameters.md
"""
from __future__ import annotations

import ast
import re
from pathlib import Path
from typing import Any

import supply_chain_research.config as config_module
from pydantic import BaseModel
from supply_chain_research.config import MasterConfig

REPO_ROOT = Path(__file__).resolve().parents[1]
OUTPUT_PATH = REPO_ROOT / "docs" / "appendix_a_parameters.md"
CONFIG_PATH = Path(config_module.__file__)

# Units pattern: matches a parenthesised group containing common
# physical / economic unit tokens. The regex is intentionally
# conservative — when no parenthetical with a known unit appears in
# the field description, the units column is left empty (per the
# Appendix A specification).
UNITS_RE = re.compile(
    r"\(([^()]*?(?:kg|km/h|km|INR|day|hour|tonne|TJ|degree|%|kWh|MJ"
    r"|/litre|litre|/km|/kg)[^()]*?)\)",
    re.IGNORECASE,
)

# String-value truncation guard: long URLs / API keys still render as
# a single markdown cell but are abbreviated to keep the table
# readable on standard journal page widths.
MAX_STR_VALUE_LEN = 80
MAX_LIST_PREVIEW = 3


_MAX_PRECEDING_COMMENT_LINES = 8  # cap on preceding-block lookback
_MAX_SOURCE_TEXT_LEN = 240  # truncate long source strings for table width


def _strip_hash(line: str) -> str:
    """Return the comment text after the leading ``#``, or empty for non-comments.

    Parameters
    ----------
    line : str
        A single source line.

    Returns
    -------
    str
        The text following the first ``#`` with surrounding whitespace
        stripped, or an empty string when *line* is not a pure-comment
        line (i.e., contains code before the ``#``).
    """
    stripped = line.lstrip()
    if stripped.startswith("#"):
        return stripped[1:].lstrip().rstrip()
    return ""


def _collect_preceding_comments(
    lines: list[str], assign_lineno: int
) -> str:
    """Walk upward from *assign_lineno - 1* and collect a contiguous comment block.

    Stops at the first non-comment, non-blank line or after
    :data:`_MAX_PRECEDING_COMMENT_LINES` lines, whichever comes first.
    Blank lines terminate the block (they separate semantically
    distinct comments). The result is a single space-joined string,
    truncated to :data:`_MAX_SOURCE_TEXT_LEN` characters.

    Parameters
    ----------
    lines : list[str]
        Source split by ``splitlines``.
    assign_lineno : int
        1-indexed line number of the assignment whose preceding
        comment block we want.

    Returns
    -------
    str
        The flattened comment block, possibly empty.
    """
    collected: list[str] = []
    idx = assign_lineno - 2  # one above the assignment line (0-indexed)
    visited = 0
    while idx >= 0 and visited < _MAX_PRECEDING_COMMENT_LINES:
        raw = lines[idx]
        if raw.strip() == "":
            break  # [PEP8-2001 §"comments"] blank line ends a comment block
        comment = _strip_hash(raw)
        if not comment:
            break  # hit a code line; stop walking up
        collected.append(comment)
        idx -= 1
        visited += 1
    if not collected:
        return ""
    collected.reverse()  # restore source order
    flattened = " ".join(collected)
    if len(flattened) > _MAX_SOURCE_TEXT_LEN:
        flattened = flattened[: _MAX_SOURCE_TEXT_LEN - 3].rstrip() + "..."
    return flattened


def _build_inline_comment_index(source: str) -> dict[tuple[str, str], str]:
    """Index citation comments by ``(class_name, field_name)``.

    Walks the ``config.py`` AST for every :class:`ast.ClassDef` whose
    body contains either annotated assignments (``name: T = expr``)
    or plain assignments (``name = expr``). For each top-level field
    inside the class the function records, in order of preference:

    1. The inline ``# ...`` comment that sits on the assignment's
       *end* line (multi-line ``default_factory`` expressions push
       the comment to the closing parenthesis line);
    2. The contiguous block of pure-comment lines immediately above
       the assignment, joined into one string and truncated to
       :data:`_MAX_SOURCE_TEXT_LEN` characters.

    Lines without either form of citation map to the empty string.

    Parameters
    ----------
    source : str
        Full text of ``supply_chain_research/config.py``.

    Returns
    -------
    dict[tuple[str, str], str]
        Lookup table keyed by ``(class_name, field_name)``.
    """
    tree = ast.parse(source)
    lines = source.splitlines()
    out: dict[tuple[str, str], str] = {}
    for node in ast.walk(tree):
        if not isinstance(node, ast.ClassDef):
            continue
        for body_node in node.body:
            field_name: str | None = None
            lineno: int | None = None
            if isinstance(body_node, ast.AnnAssign) and isinstance(
                body_node.target, ast.Name
            ):
                field_name = body_node.target.id
                lineno = body_node.lineno
            elif (
                isinstance(body_node, ast.Assign)
                and len(body_node.targets) == 1
                and isinstance(body_node.targets[0], ast.Name)
            ):
                field_name = body_node.targets[0].id
                lineno = body_node.lineno
            if field_name is None or lineno is None:
                continue
            # AST line numbers are 1-indexed; the *end* line of the
            # assignment is where any trailing inline comment lives
            # (multi-line default_factory expressions push the comment
            # to the closing ``)`` line).
            end_lineno = getattr(body_node, "end_lineno", lineno) or lineno
            line = lines[end_lineno - 1]
            # Inline comment: only count ``#`` outside string literals.
            # We use a simple heuristic — find ``#`` not enclosed in
            # quotes — which is sufficient for ``config.py`` (no
            # f-strings or raw strings carry literal ``#`` here).
            hash_idx = _find_inline_hash(line)
            inline_comment = (
                line[hash_idx + 1 :].strip() if hash_idx != -1 else ""
            )
            if inline_comment:
                out[(node.name, field_name)] = inline_comment
                continue
            # Fallback: walk upward to capture the preceding comment
            # block — most citations in ``config.py`` (MEET, IPCC,
            # Schulman, Haarnoja, ...) live there rather than inline.
            preceding = _collect_preceding_comments(lines, lineno)
            out[(node.name, field_name)] = preceding
    return out


def _find_inline_hash(line: str) -> int:
    """Return the index of the first inline ``#`` *not* inside a string.

    A lightweight scanner sufficient for ``config.py``: tracks
    single- and double-quoted runs but does not handle triple-
    quoted literals (the file has none on assignment lines).

    Parameters
    ----------
    line : str
        A single source line.

    Returns
    -------
    int
        Index of the first code-level ``#``, or ``-1`` when none is
        present (or when the line begins with a comment, which the
        caller treats separately).
    """
    in_single = False
    in_double = False
    for i, ch in enumerate(line):
        if ch == "'" and not in_double:
            in_single = not in_single
        elif ch == '"' and not in_single:
            in_double = not in_double
        elif ch == "#" and not in_single and not in_double:
            # Skip the leading-comment case: comment-only lines are
            # handled by the preceding-block collector, not inline.
            stripped_prefix = line[:i].strip()
            if stripped_prefix == "":
                return -1
            return i
    return -1


def _extract_units(description: str | None) -> str:
    """Return the first parenthesised unit token in *description*.

    Parameters
    ----------
    description : str or None
        The pydantic ``Field(description=...)`` metadata, if any.

    Returns
    -------
    str
        The matched unit token (without the enclosing parens) or
        an empty string when *description* is missing or carries no
        recognisable unit.
    """
    if not description:
        return ""
    match = UNITS_RE.search(description)
    return match.group(1).strip() if match else ""


def _format_value(value: Any) -> str:
    """Render *value* as a compact, table-friendly string."""
    if isinstance(value, str):
        if len(value) > MAX_STR_VALUE_LEN:
            return f'"{value[: MAX_STR_VALUE_LEN - 3]}..."'
        return f'"{value}"'
    if isinstance(value, list):
        if not value:
            return "[]"
        if len(value) > MAX_LIST_PREVIEW:
            head = ", ".join(repr(v) for v in value[:MAX_LIST_PREVIEW])
            return f"[{head}, ...] ({len(value)} items)"
        return repr(value)
    if isinstance(value, tuple):
        return repr(value)
    if isinstance(value, bool):
        return repr(value)
    return repr(value)


def _walk_model(
    model_cls: type[BaseModel],
    instance: BaseModel,
    prefix: str,
    comment_index: dict[tuple[str, str], str],
    rows: list[tuple[str, str, str, str]],
) -> None:
    """Recursively flatten *instance* into ``(path, value, units, source)`` rows.

    Sub-models are descended into; every other field becomes a leaf
    row. Field declaration order is preserved.

    Parameters
    ----------
    model_cls : type[BaseModel]
        The model class whose ``model_fields`` drive the iteration.
    instance : BaseModel
        The live instance whose attributes provide the resolved
        default values (after ``default_factory`` evaluation).
    prefix : str
        Dotted prefix accumulated from outer models; empty at the
        root.
    comment_index : dict[tuple[str, str], str]
        Output of :func:`_build_inline_comment_index`.
    rows : list[tuple[str, str, str, str]]
        Accumulator (mutated in place).
    """
    for field_name, field_info in model_cls.model_fields.items():
        full_path = f"{prefix}.{field_name}" if prefix else field_name
        value = getattr(instance, field_name)
        if isinstance(value, BaseModel):
            _walk_model(
                type(value), value, full_path, comment_index, rows
            )
            continue
        description = field_info.description or ""
        units = _extract_units(description)
        source = comment_index.get((model_cls.__name__, field_name), "")
        rows.append((full_path, _format_value(value), units, source))


def _escape_md_pipes(text: str) -> str:
    """Escape literal ``|`` characters so the markdown table parses."""
    return text.replace("|", r"\|")


def main() -> int:
    """Render ``docs/appendix_a_parameters.md`` and report the row count."""
    config_source = CONFIG_PATH.read_text(encoding="utf-8")
    comment_index = _build_inline_comment_index(config_source)

    cfg = MasterConfig()
    rows: list[tuple[str, str, str, str]] = []
    _walk_model(MasterConfig, cfg, "", comment_index, rows)

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    out_lines: list[str] = []
    out_lines.append("# Appendix A — Complete Parameter Tables")
    out_lines.append("")
    out_lines.append(
        "Auto-generated from `supply_chain_research/config.py` via "
        "`scripts/generate_appendix_a.py`. Every scalar field of "
        "`MasterConfig` is enumerated below with its current default "
        "value, the units inferred from the pydantic field "
        "description (when present), and the inline citation "
        "captured from the source file. The taxonomy tags PHYSICS "
        "DERIVED / PROBLEM SCALED / TUNED that appear in the source "
        "column follow the convention declared in the `MasterConfig` "
        "docstring (Audit 2.1)."
    )
    out_lines.append("")
    out_lines.append(
        "Regenerate after a config change with "
        "`python scripts/generate_appendix_a.py`."
    )
    out_lines.append("")
    out_lines.append(f"Total parameters listed: **{len(rows)}**.")
    out_lines.append("")
    out_lines.append("| Parameter | Value | Units | Source |")
    out_lines.append("|-----------|-------|-------|--------|")
    for path, value, units, source in rows:
        out_lines.append(
            "| `{0}` | `{1}` | {2} | {3} |".format(
                _escape_md_pipes(path),
                _escape_md_pipes(value),
                _escape_md_pipes(units),
                _escape_md_pipes(source),
            )
        )
    out_lines.append("")
    OUTPUT_PATH.write_text("\n".join(out_lines), encoding="utf-8")
    print(f"Wrote {len(rows)} parameter rows to {OUTPUT_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
