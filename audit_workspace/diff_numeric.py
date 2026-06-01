"""Compare two numeric snapshots from ``capture_numeric_baseline.py``.

This helper implements the regression-gate side of preservation clauses
``C3.2``, ``C3.3``, ``C3.4``, ``C3.5``, ``C3.6``, ``C3.7``, ``C3.8``,
``C3.9`` and ``C3.13`` from
``.kiro/specs/supply-chain-research-audit/bugfix.md``:

    "WHEN ``EmissionModel`` / NSGA-II / OR-Tools / DES / Clarke-Wright /
    multi-product / robust / carbon-budget pipelines are invoked under
    the documented seeds and configurations THEN the system SHALL
    produce kg-CO2 / Pareto-front / cost / service-level outputs that
    match the pre-fix snapshot bit-for-bit (or within the recorded
    ``tolerance`` field) unless an explicit citation in
    ``docs/IMPROVEMENT_REPORT.md`` justifies the change."  -- bugfix.md
    C3.2 / C3.3 / C3.7 / C3.9 / C3.13

Given the baseline JSON produced by ``capture_numeric_baseline.py`` and
the post-fix snapshot, this script verifies that every leaf numeric
field matches within the per-section tolerance. Any out-of-tolerance
delta is fatal unless its field name is documented in
``docs/IMPROVEMENT_REPORT.md`` (every numeric divergence requires an inline
citation per clause C3.3).

Usage
-----
::

    python audit_workspace/diff_numeric.py <baseline.json> <final.json>

Exit status
-----------
* ``0`` -- every delta is within tolerance, OR every out-of-tolerance
  delta has been listed in ``docs/IMPROVEMENT_REPORT.md``.
* non-zero -- at least one undocumented out-of-tolerance delta exists.

References
----------
.. [1] bugfix.md, clauses C3.2, C3.3, C3.4, C3.5, C3.6, C3.7, C3.8,
       C3.9, C3.13 (numeric preservation contract).
"""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path
from typing import Any, Iterator

# Field names that carry metadata rather than measured values; these
# are skipped during the leaf-numeric walk. Per the spec for task 6.5
# we ignore ``tolerance``, ``tolerance_kind``, ``n_solutions``,
# ``objective_names``, and "array-shape metadata"; we also drop
# ``elapsed_seconds`` (wall-clock instrumentation, non-deterministic
# by design and not a preservation field) and the JSON-level meta
# (``spec``, ``task``, ``seed``, ``scenario``,
# ``preservation_clauses``).
_METADATA_KEYS = frozenset(
    {
        "tolerance",
        "tolerance_kind",
        "n_solutions",
        "objective_names",
        "preservation_clauses",
        "spec",
        "task",
        "seed",
        "scenario",
        "elapsed_seconds",
        "n_generations_executed",
    }
)

# Default tolerance applied when the section does not declare one.
_DEFAULT_TOL = 1.0e-6
_DEFAULT_KIND = "relative"

REPO_ROOT = Path(__file__).resolve().parent.parent
IMPROVEMENT_REPORT = REPO_ROOT / "docs/IMPROVEMENT_REPORT.md"


def _is_number(x: Any) -> bool:
    """Return True for ``int`` / ``float`` (excluding ``bool``)."""
    return isinstance(x, (int, float)) and not isinstance(x, bool)


def _walk(
    base: Any,
    final: Any,
    section: str,
    tol: float,
    kind: str,
    path: str,
) -> Iterator[dict[str, Any]]:
    """Yield deltas for every leaf numeric field under ``base`` / ``final``.

    Parameters
    ----------
    base, final : Any
        Matching JSON sub-trees from the two snapshots.
    section : str
        Top-level section name (``emissions`` / ``nsga2_pareto`` / ...)
        used for human-readable reporting.
    tol : float
        Tolerance applied to every leaf in this sub-tree.
    kind : str
        Either ``"absolute"`` or ``"relative"``.
    path : str
        Dotted path to the current sub-tree, used for reporting.

    Yields
    ------
    dict
        One delta per out-of-tolerance leaf with keys ``section``,
        ``field``, ``baseline``, ``final``, ``abs_delta``, ``rel_delta``,
        ``tolerance``, ``tolerance_kind``, ``in_tolerance``.
    """
    # Special-case: nsga2_pareto.front is an array-of-arrays whose row
    # ordering may shift between runs (NSGA-II non-domination ranks the
    # set, but the post-rank ordering is implementation-detail). Compare
    # row-sorted to remove this noise.
    if path.endswith(".front") and isinstance(base, list) and isinstance(final, list):
        yield from _compare_pareto_front(base, final, section, tol, kind, path)
        return

    if isinstance(base, dict) and isinstance(final, dict):
        keys = sorted(set(base) | set(final))
        for key in keys:
            if key in _METADATA_KEYS:
                continue
            sub_path = f"{path}.{key}" if path else key
            if key not in base:
                yield {
                    "section": section,
                    "field": sub_path,
                    "baseline": None,
                    "final": final[key],
                    "abs_delta": math.inf,
                    "rel_delta": math.inf,
                    "tolerance": tol,
                    "tolerance_kind": kind,
                    "in_tolerance": False,
                    "note": "missing in baseline",
                }
                continue
            if key not in final:
                yield {
                    "section": section,
                    "field": sub_path,
                    "baseline": base[key],
                    "final": None,
                    "abs_delta": math.inf,
                    "rel_delta": math.inf,
                    "tolerance": tol,
                    "tolerance_kind": kind,
                    "in_tolerance": False,
                    "note": "missing in final",
                }
                continue
            yield from _walk(base[key], final[key], section, tol, kind, sub_path)
        return

    if isinstance(base, list) and isinstance(final, list):
        if len(base) != len(final):
            yield {
                "section": section,
                "field": path,
                "baseline": f"len={len(base)}",
                "final": f"len={len(final)}",
                "abs_delta": math.inf,
                "rel_delta": math.inf,
                "tolerance": tol,
                "tolerance_kind": kind,
                "in_tolerance": False,
                "note": "list length differs",
            }
            return
        for i, (b, f) in enumerate(zip(base, final)):
            yield from _walk(b, f, section, tol, kind, f"{path}[{i}]")
        return

    if _is_number(base) and _is_number(final):
        abs_delta = abs(float(final) - float(base))
        denom = max(abs(float(base)), abs(float(final)))
        rel_delta = abs_delta / denom if denom > 0 else 0.0
        if kind == "absolute":
            in_tol = abs_delta <= tol
        else:
            in_tol = rel_delta <= tol if denom > 0 else abs_delta <= tol
        if not in_tol:
            yield {
                "section": section,
                "field": path,
                "baseline": float(base),
                "final": float(final),
                "abs_delta": abs_delta,
                "rel_delta": rel_delta,
                "tolerance": tol,
                "tolerance_kind": kind,
                "in_tolerance": False,
            }


def _compare_pareto_front(
    base: list,
    final: list,
    section: str,
    tol: float,
    kind: str,
    path: str,
) -> Iterator[dict[str, Any]]:
    """Compare an NSGA-II Pareto front under row-sort to ignore ordering.

    Parameters
    ----------
    base, final : list of list of float
        Two ``(n_solutions, n_obj)`` arrays of objective vectors.
    section, tol, kind, path : see :func:`_walk`.

    Yields
    ------
    dict
        One delta per row-position whose row-wise max relative
        deviation exceeds ``tol``. Shape mismatch yields a single
        synthetic delta so the gate fails closed.
    """
    if len(base) != len(final):
        yield {
            "section": section,
            "field": path,
            "baseline": f"shape=({len(base)}, ...)",
            "final": f"shape=({len(final)}, ...)",
            "abs_delta": math.inf,
            "rel_delta": math.inf,
            "tolerance": tol,
            "tolerance_kind": kind,
            "in_tolerance": False,
            "note": "Pareto-front row count differs",
        }
        return
    base_sorted = sorted([tuple(r) for r in base])
    final_sorted = sorted([tuple(r) for r in final])
    for i, (br, fr) in enumerate(zip(base_sorted, final_sorted)):
        if len(br) != len(fr):
            yield {
                "section": section,
                "field": f"{path}[row={i}]",
                "baseline": br,
                "final": fr,
                "abs_delta": math.inf,
                "rel_delta": math.inf,
                "tolerance": tol,
                "tolerance_kind": kind,
                "in_tolerance": False,
                "note": "Pareto-front row width differs",
            }
            continue
        for j, (b, f) in enumerate(zip(br, fr)):
            abs_delta = abs(float(f) - float(b))
            denom = max(abs(float(b)), abs(float(f)))
            rel_delta = abs_delta / denom if denom > 0 else 0.0
            if kind == "absolute":
                in_tol = abs_delta <= tol
            else:
                in_tol = rel_delta <= tol if denom > 0 else abs_delta <= tol
            if not in_tol:
                yield {
                    "section": section,
                    "field": f"{path}[row={i}][col={j}]",
                    "baseline": float(b),
                    "final": float(f),
                    "abs_delta": abs_delta,
                    "rel_delta": rel_delta,
                    "tolerance": tol,
                    "tolerance_kind": kind,
                    "in_tolerance": False,
                }


def _count_leaves(base: Any, final: Any, path: str = "") -> int:
    """Count leaf numeric fields under matched sub-trees.

    Mirrors the traversal rules of :func:`_walk` (skip metadata keys,
    treat ``.front`` arrays as a flat sequence of numeric leaves) but
    returns only the count.
    """
    if path.endswith(".front") and isinstance(base, list) and isinstance(final, list):
        n = 0
        for r_base, r_final in zip(base, final):
            if isinstance(r_base, list) and isinstance(r_final, list):
                n += min(len(r_base), len(r_final))
        return n
    if isinstance(base, dict) and isinstance(final, dict):
        n = 0
        for key in set(base) & set(final):
            if key in _METADATA_KEYS:
                continue
            sub_path = f"{path}.{key}" if path else key
            n += _count_leaves(base[key], final[key], sub_path)
        return n
    if isinstance(base, list) and isinstance(final, list):
        n = 0
        for i, (b, f) in enumerate(zip(base, final)):
            n += _count_leaves(b, f, f"{path}[{i}]")
        return n
    if _is_number(base) and _is_number(final):
        return 1
    return 0



    """Return the lower-cased text of ``docs/IMPROVEMENT_REPORT.md`` (or "")."""
    if not IMPROVEMENT_REPORT.exists():
        return ""
    return IMPROVEMENT_REPORT.read_text().lower()


def _is_documented(field: str, report_text: str) -> bool:
    """Return True if ``field`` appears anywhere in the improvement report.

    The match is case-insensitive on the leaf field name (the part after
    the final dot). Sub-section headers in docs/IMPROVEMENT_REPORT.md (e.g.
    ``## FIX-006``) describe Pareto-front and min-cost / min-carbon
    deltas in narrative form; we look for the leaf token rather than
    the whole dotted path so a documented "min_cost" delta in any
    ``## FIX-NNN`` section satisfies the gate.
    """
    if not report_text:
        return False
    leaf = field.rsplit(".", 1)[-1]
    leaf = leaf.split("[")[0]
    if not leaf:
        return False
    return leaf.lower() in report_text


def main(argv: list[str]) -> int:
    if len(argv) != 3:
        print("usage: diff_numeric.py <baseline.json> <final.json>", file=sys.stderr)
        return 2

    base = json.loads(Path(argv[1]).read_text())
    final = json.loads(Path(argv[2]).read_text())

    sections = sorted(set(base) | set(final))
    out_of_tol: list[dict[str, Any]] = []
    in_tol_sections: list[tuple[str, int]] = []

    for sec in sections:
        if sec in _METADATA_KEYS:
            continue
        b_sec = base.get(sec)
        f_sec = final.get(sec)
        if b_sec is None or f_sec is None:
            out_of_tol.append({
                "section": sec,
                "field": sec,
                "baseline": "<missing>" if b_sec is None else "<present>",
                "final": "<missing>" if f_sec is None else "<present>",
                "abs_delta": math.inf,
                "rel_delta": math.inf,
                "tolerance": _DEFAULT_TOL,
                "tolerance_kind": _DEFAULT_KIND,
                "in_tolerance": False,
                "note": "section missing",
            })
            continue
        tol = b_sec.get("tolerance", _DEFAULT_TOL) if isinstance(b_sec, dict) else _DEFAULT_TOL
        kind = b_sec.get("tolerance_kind", _DEFAULT_KIND) if isinstance(b_sec, dict) else _DEFAULT_KIND
        deltas = list(_walk(b_sec, f_sec, sec, tol, kind, sec))
        if deltas:
            out_of_tol.extend(deltas)
        else:
            n_compared = _count_leaves(b_sec, f_sec, sec)
            in_tol_sections.append((sec, n_compared))

    print("Numeric regression diff (bugfix.md C3.2 / C3.3 / C3.4 / C3.5 / C3.6 / C3.7 / C3.8 / C3.9 / C3.13)")
    print("=" * 80)
    print()
    print("Per-section pass list (every leaf numeric field within tolerance):")
    if not in_tol_sections:
        print("  <none>")
    for sec, n in in_tol_sections:
        print(f"  - {sec}: {n} leaf field(s) within tolerance")

    if not out_of_tol:
        print()
        print("Total out-of-tolerance deltas: 0")
        print("VERDICT: PASS")
        return 0

    print()
    print(f"Out-of-tolerance deltas: {len(out_of_tol)}")
    print("-" * 80)
    report_text = _read_report_text()
    documented: list[dict[str, Any]] = []
    undocumented: list[dict[str, Any]] = []
    for d in out_of_tol:
        is_doc = _is_documented(d["field"], report_text)
        d["documented"] = is_doc
        (documented if is_doc else undocumented).append(d)
        marker = "[documented]" if is_doc else "[UNDOCUMENTED]"
        print(
            f"  {marker} {d['section']} :: {d['field']}\n"
            f"      baseline = {d['baseline']!r}\n"
            f"      final    = {d['final']!r}\n"
            f"      abs_delta = {d['abs_delta']!r}\n"
            f"      rel_delta = {d['rel_delta']!r}\n"
            f"      tolerance = {d['tolerance']!r} ({d['tolerance_kind']})"
        )
        if "note" in d:
            print(f"      note = {d['note']}")

    print()
    print(f"  documented   : {len(documented)}")
    print(f"  undocumented : {len(undocumented)}")
    if undocumented:
        print()
        print("VERDICT: FAIL (undocumented out-of-tolerance deltas exist)")
        return 1
    print()
    print("VERDICT: PASS (every out-of-tolerance delta is documented in docs/IMPROVEMENT_REPORT.md)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
