"""Capture the function-signature baseline for ``supply_chain_research``.

This script implements task 0.3 of ``supply-chain-research-audit``: it walks
every module under :mod:`supply_chain_research` using :func:`pkgutil.walk_packages`,
collects :func:`inspect.signature` for every public function, class, and method,
and writes a sorted JSON snapshot to ``audit_workspace/CURRENT_SIGNATURES.json``.

The resulting file is the ground truth for preservation clause C3.12
(public-API signatures must not change unless an additive optional argument is
introduced with a default that preserves the original behaviour).

Usage
-----
Run from the repository root::

    python audit_workspace/capture_signatures.py

The script is intentionally tolerant of import failures: any module that fails
to import is recorded under a ``_import_errors`` entry so reviewers can see
which sub-trees were skipped, rather than aborting the whole snapshot.
"""

from __future__ import annotations

import importlib
import inspect
import json
import pkgutil
import sys
import traceback
from pathlib import Path
from typing import Any, Dict

# Repo root = parent of this script's directory.
REPO_ROOT = Path(__file__).resolve().parent.parent
PACKAGE_NAME = "supply_chain_research"
OUTPUT_PATH = REPO_ROOT / "audit_workspace" / "CURRENT_SIGNATURES.json"


def _is_public(name: str) -> bool:
    """Return True for public symbols (does not start with an underscore)."""
    return not name.startswith("_")


def _safe_signature(obj: Any) -> str | None:
    """Return ``str(inspect.signature(obj))`` or ``None`` if not introspectable."""
    try:
        return str(inspect.signature(obj))
    except (TypeError, ValueError):
        return None


def _record_callable(
    out: Dict[str, str], qualname: str, obj: Any
) -> None:
    """Record the signature of ``obj`` under ``qualname`` if available."""
    sig = _safe_signature(obj)
    if sig is not None:
        out[qualname] = sig


def _collect_class_members(
    out: Dict[str, str], module_name: str, cls: type
) -> None:
    """Record public methods/staticmethods/classmethods/properties of ``cls``.

    Only members defined on the class itself (not inherited) are recorded so the
    baseline reflects what the project owns rather than the standard library.
    """
    cls_qualname = f"{module_name}.{cls.__name__}"

    # The class signature itself (i.e. ``__init__`` surface).
    _record_callable(out, cls_qualname, cls)

    own_attrs = vars(cls)
    for attr_name, raw in own_attrs.items():
        if not _is_public(attr_name):
            continue
        member_qualname = f"{cls_qualname}.{attr_name}"

        if isinstance(raw, (staticmethod, classmethod)):
            _record_callable(out, member_qualname, raw.__func__)
        elif isinstance(raw, property):
            if raw.fget is not None:
                _record_callable(out, member_qualname, raw.fget)
        elif inspect.isfunction(raw) or inspect.ismethod(raw):
            _record_callable(out, member_qualname, raw)
        elif inspect.isclass(raw):
            # Nested class: recurse so nested public methods are captured too.
            _collect_class_members(out, cls_qualname, raw)


def _collect_module(out: Dict[str, str], module: Any) -> None:
    """Record public functions and classes defined in ``module``."""
    module_name = module.__name__
    for attr_name, raw in vars(module).items():
        if not _is_public(attr_name):
            continue
        # Skip re-exports: only record symbols that originate in this module.
        owner = getattr(raw, "__module__", None)
        if owner != module_name:
            continue

        qualname = f"{module_name}.{attr_name}"
        if inspect.isclass(raw):
            _collect_class_members(out, module_name, raw)
        elif inspect.isfunction(raw) or inspect.isbuiltin(raw):
            _record_callable(out, qualname, raw)


def capture() -> Dict[str, Any]:
    """Walk ``supply_chain_research`` and return a sorted signature mapping."""
    # Make sure the repo root is on ``sys.path`` so ``import supply_chain_research``
    # works no matter where the script is invoked from.
    if str(REPO_ROOT) not in sys.path:
        sys.path.insert(0, str(REPO_ROOT))

    package = importlib.import_module(PACKAGE_NAME)
    signatures: Dict[str, str] = {}
    import_errors: Dict[str, str] = {}

    # Top-level package symbols.
    try:
        _collect_module(signatures, package)
    except Exception:  # pragma: no cover - defensive
        import_errors[PACKAGE_NAME] = traceback.format_exc()

    # Recurse into every sub-module.
    package_paths = getattr(package, "__path__", [])
    for module_info in pkgutil.walk_packages(
        package_paths, prefix=f"{PACKAGE_NAME}."
    ):
        module_name = module_info.name
        try:
            module = importlib.import_module(module_name)
        except Exception:
            import_errors[module_name] = traceback.format_exc()
            continue

        try:
            _collect_module(signatures, module)
        except Exception:  # pragma: no cover - defensive
            import_errors[module_name] = traceback.format_exc()

    # Build sorted output (dict insertion order = alphabetical key order).
    sorted_signatures = {key: signatures[key] for key in sorted(signatures)}
    payload: Dict[str, Any] = dict(sorted_signatures)
    if import_errors:
        payload["_import_errors"] = {
            key: import_errors[key] for key in sorted(import_errors)
        }
    return payload


def main() -> int:
    payload = capture()
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    n_signatures = sum(1 for k in payload if not k.startswith("_"))
    n_errors = len(payload.get("_import_errors", {}))
    print(
        f"Wrote {n_signatures} signatures to {OUTPUT_PATH} "
        f"({n_errors} import error(s))."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
