"""Compare two function-signature snapshots for the supply-chain project.

This helper implements the regression-gate side of preservation clause
``C3.12`` from ``.kiro/specs/supply-chain-research-audit/bugfix.md``:

    "WHEN any user code imports a public symbol from
    ``supply_chain_research`` ... THEN the system SHALL CONTINUE TO expose
    that symbol with the same signature; new optional arguments SHALL have
    default values that preserve original behavior."  -- bugfix.md C3.12

Given the baseline JSON produced by ``capture_signatures.py`` and the
post-fix snapshot, the script verifies that every public signature
recorded in the baseline still exists in the final snapshot with either:

* Identical parameters (same names, kinds, and defaults), OR
* Strictly added optional parameters of kind
  ``POSITIONAL_OR_KEYWORD`` or ``KEYWORD_ONLY`` carrying a default value.

The exit status is ``0`` only if no breaking change is detected.

Parameters are extracted from the signature strings produced by
``str(inspect.signature(...))`` by wrapping each string in a ``def``
stub and walking the resulting :class:`ast.arguments` node.

Usage
-----
::

    python audit_workspace/diff_signatures.py <baseline.json> <final.json>

References
----------
.. [1] bugfix.md, clause C3.12 (signature preservation contract).
"""

from __future__ import annotations

import ast
import json
import re
import sys
from pathlib import Path
from typing import Dict, List, Tuple

# Sentinels for non-Python default reprs emitted by ``inspect.Signature``.
_FACTORY_RE = re.compile(r"<factory>")
_FUNC_RE = re.compile(r"<function [^>]+>")
_BUILTIN_RE = re.compile(r"<built-in function [^>]+>")
_OBJECT_RE = re.compile(r"<[A-Za-z_][\w\.]* object at 0x[0-9a-fA-F]+>")


def _sanitize(sig: str) -> str:
    """Replace non-Python default reprs with parseable placeholders."""
    out = _FACTORY_RE.sub("__FACTORY__", sig)
    out = _FUNC_RE.sub("__FUNCTION__", out)
    out = _BUILTIN_RE.sub("__BUILTIN__", out)
    out = _OBJECT_RE.sub("__OBJECT__", out)
    return out


def _default_text(node: ast.AST | None) -> str | None:
    """Return the source text of a default-value AST node, or ``None``."""
    if node is None:
        return None
    return ast.unparse(node)


def parse_signature(sig: str) -> List[Dict[str, object]]:
    """Parse an ``inspect.signature`` string into structured parameters.

    Parameters
    ----------
    sig : str
        Raw signature text such as ``"(a, b: int = 0) -> None"``.

    Returns
    -------
    list of dict
        One dict per parameter with keys ``name``, ``kind``,
        ``has_default``, and ``default`` (the source text of the default,
        or ``None``).
    """
    src = f"def __sig__{_sanitize(sig)}: pass"
    fn = ast.parse(src).body[0]
    assert isinstance(fn, ast.FunctionDef)
    args = fn.args

    params: List[Dict[str, object]] = []

    flat_pos = list(args.posonlyargs) + list(args.args)
    n_pos = len(flat_pos)
    pos_defaults: List[ast.AST | None] = (
        [None] * (n_pos - len(args.defaults)) + list(args.defaults)
    )
    for i, a in enumerate(flat_pos):
        kind = "POSITIONAL_ONLY" if i < len(args.posonlyargs) else "POSITIONAL_OR_KEYWORD"
        d = pos_defaults[i]
        params.append({
            "name": a.arg,
            "kind": kind,
            "has_default": d is not None,
            "default": _default_text(d),
        })

    if args.vararg is not None:
        params.append({
            "name": args.vararg.arg,
            "kind": "VAR_POSITIONAL",
            "has_default": False,
            "default": None,
        })

    for a, d in zip(args.kwonlyargs, args.kw_defaults):
        params.append({
            "name": a.arg,
            "kind": "KEYWORD_ONLY",
            "has_default": d is not None,
            "default": _default_text(d),
        })

    if args.kwarg is not None:
        params.append({
            "name": args.kwarg.arg,
            "kind": "VAR_KEYWORD",
            "has_default": False,
            "default": None,
        })

    return params


def _load(path: Path) -> Dict[str, str]:
    """Load a signature snapshot, dropping the ``_import_errors`` block."""
    raw = json.loads(path.read_text())
    return {k: v for k, v in raw.items() if not k.startswith("_") and isinstance(v, str)}


def _classify(
    base_params: List[Dict[str, object]],
    final_params: List[Dict[str, object]],
) -> Tuple[List[str], List[str], List[str]]:
    """Return (breaking, additive, identical_notes) for one signature."""
    breaking: List[str] = []
    additive: List[str] = []
    notes: List[str] = []

    base_by_name = {p["name"]: p for p in base_params}
    final_by_name = {p["name"]: p for p in final_params}

    # Positional rename detection: same index, same kind, different name,
    # AND the baseline name is not anywhere in final (genuine rename).
    base_pos = [p for p in base_params if p["kind"] in ("POSITIONAL_ONLY", "POSITIONAL_OR_KEYWORD")]
    final_pos = [p for p in final_params if p["kind"] in ("POSITIONAL_ONLY", "POSITIONAL_OR_KEYWORD")]
    renamed: set = set()
    for i in range(min(len(base_pos), len(final_pos))):
        bn, fn_ = base_pos[i]["name"], final_pos[i]["name"]
        if bn != fn_ and bn not in final_by_name and fn_ not in base_by_name:
            breaking.append(f"renamed positional parameter at index {i}: '{bn}' -> '{fn_}'")
            renamed.add(bn)
            renamed.add(fn_)

    for name, bp in base_by_name.items():
        if name in renamed:
            continue
        if name not in final_by_name:
            label = "optional" if bp["has_default"] else "required"
            breaking.append(f"removed {label} parameter '{name}'")
            continue
        fp = final_by_name[name]
        if fp["kind"] != bp["kind"]:
            breaking.append(f"parameter '{name}' kind changed: {bp['kind']} -> {fp['kind']}")
            continue
        if bp["has_default"] != fp["has_default"]:
            if bp["has_default"] and not fp["has_default"]:
                breaking.append(f"parameter '{name}' became required (default removed)")
            else:
                additive.append(f"parameter '{name}' became optional (default {fp['default']})")
        elif bp["default"] != fp["default"]:
            breaking.append(
                f"parameter '{name}' default changed: {bp['default']} -> {fp['default']}"
            )

    for name, fp in final_by_name.items():
        if name in renamed or name in base_by_name:
            continue
        if not fp["has_default"]:
            breaking.append(f"added required parameter '{name}' (kind={fp['kind']})")
        elif fp["kind"] not in ("POSITIONAL_OR_KEYWORD", "KEYWORD_ONLY"):
            breaking.append(f"added parameter '{name}' has disallowed kind {fp['kind']}")
        else:
            additive.append(f"added optional parameter '{name}' (default {fp['default']})")

    return breaking, additive, notes


def main(argv: List[str]) -> int:
    if len(argv) != 3:
        print("usage: diff_signatures.py <baseline.json> <final.json>", file=sys.stderr)
        return 2
    base = _load(Path(argv[1]))
    final = _load(Path(argv[2]))

    removed_signatures: List[str] = []
    breaking_changes: Dict[str, List[str]] = {}
    additive_changes: Dict[str, List[str]] = {}
    unchanged = 0

    for qualname, base_sig in sorted(base.items()):
        if qualname not in final:
            removed_signatures.append(qualname)
            continue
        try:
            base_params = parse_signature(base_sig)
            final_params = parse_signature(final[qualname])
        except SyntaxError as exc:
            breaking_changes.setdefault(qualname, []).append(f"unparseable signature: {exc}")
            continue
        breaking, additive, _ = _classify(base_params, final_params)
        if breaking:
            breaking_changes[qualname] = breaking
            if additive:
                breaking_changes[qualname].extend(f"(also additive) {a}" for a in additive)
        elif additive:
            additive_changes[qualname] = additive
        else:
            unchanged += 1

    print("Signature preservation diff (bugfix.md C3.12)")
    print("=" * 60)
    if removed_signatures:
        print("\nRemoved signatures (BREAKING):")
        for q in removed_signatures:
            print(f"  - {q}")
    breaking_qualnames = list(breaking_changes)
    if breaking_qualnames:
        print("\nSignatures with breaking parameter changes (BREAKING):")
        for q in sorted(breaking_qualnames):
            print(f"  - {q}")
            for line in breaking_changes[q]:
                print(f"      {line}")
    if additive_changes:
        print("\nSignatures with additive optional-parameter changes (OK):")
        for q in sorted(additive_changes):
            print(f"  - {q}")
            for line in additive_changes[q]:
                print(f"      {line}")

    print("\nTotal:")
    print(f"  signatures unchanged             : {unchanged}")
    print(f"  signatures with additive changes : {len(additive_changes)}")
    print(f"  signatures with breaking changes : {len(breaking_qualnames) + len(removed_signatures)}")

    has_breaking = bool(removed_signatures or breaking_qualnames)
    return 1 if has_breaking else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
