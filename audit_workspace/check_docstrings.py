"""Docstring compliance checker for supply_chain_research.

Walks every module under ``supply_chain_research`` via ``pkgutil.walk_packages``
and asserts every public symbol (name not starting with ``_``) has a non-empty
docstring containing at minimum a ``Parameters`` (or ``Returns`` for properties)
section, matching the NumPy docstring style.

This implements the inventory check described in tasks.md FIX-004.
"""

from __future__ import annotations

import importlib
import inspect
import pkgutil
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
PACKAGE_NAME = "supply_chain_research"

# Some symbols are public re-exports / aliases / 3rd-party objects we cannot
# annotate. Anything explicitly listed here is exempt from the docstring rule.
ALLOWLIST: set[str] = set()


def _is_public(name: str) -> bool:
    return not name.startswith("_")


def _module_owns(obj: object, module_name: str) -> bool:
    """Return True iff ``obj`` was defined in the given module (not imported)."""
    obj_module = getattr(obj, "__module__", None)
    return obj_module == module_name


def _check_docstring(qualname: str, obj: object, *, is_property: bool = False) -> list[str]:
    """Return a list of error strings for a single object."""
    if qualname in ALLOWLIST:
        return []
    doc = inspect.getdoc(obj)
    if doc is None or not doc.strip():
        return [f"MISSING: {qualname}"]
    required = "Returns" if is_property else "Parameters"
    # Pydantic models / dataclasses without parameters are still acceptable if
    # they explain Returns / Attributes — tolerate Attributes as a stand-in.
    if (
        required not in doc
        and "Attributes" not in doc
        and "Returns" not in doc
    ):
        return [f"NO_PARAMETERS_SECTION: {qualname}"]
    return []


def check_module(module_name: str) -> list[str]:
    """Return a list of error strings for a single module."""
    errors: list[str] = []
    try:
        module = importlib.import_module(module_name)
    except Exception as exc:  # pragma: no cover - import failure is reported
        return [f"IMPORT_FAILED: {module_name}: {exc!r}"]

    for name, obj in inspect.getmembers(module):
        if not _is_public(name):
            continue
        if inspect.ismodule(obj):
            continue
        if not _module_owns(obj, module_name):
            # Skip names that the module re-exports from elsewhere.
            continue

        if inspect.isclass(obj):
            errors.extend(_check_docstring(f"{module_name}.{name}", obj))
            for member_name, member in inspect.getmembers(obj):
                if not _is_public(member_name):
                    continue
                # Skip inherited methods (only check those defined on this class).
                owner = getattr(member, "__qualname__", "")
                if not owner.startswith(obj.__name__ + "."):
                    continue
                if inspect.isfunction(member) or inspect.ismethod(member):
                    errors.extend(
                        _check_docstring(f"{module_name}.{name}.{member_name}", member)
                    )
                elif isinstance(member, (staticmethod, classmethod)):
                    errors.extend(
                        _check_docstring(
                            f"{module_name}.{name}.{member_name}",
                            member.__func__,
                        )
                    )
                elif isinstance(member, property):
                    errors.extend(
                        _check_docstring(
                            f"{module_name}.{name}.{member_name}",
                            member,
                            is_property=True,
                        )
                    )
        elif inspect.isfunction(obj):
            errors.extend(_check_docstring(f"{module_name}.{name}", obj))
    return errors


def main() -> int:
    sys.path.insert(0, str(REPO_ROOT))
    package = importlib.import_module(PACKAGE_NAME)

    errors: list[str] = []
    errors.extend(check_module(PACKAGE_NAME))

    for _, modname, _is_pkg in pkgutil.walk_packages(
        package.__path__, prefix=f"{PACKAGE_NAME}."
    ):
        errors.extend(check_module(modname))

    if errors:
        print(f"FAIL: {len(errors)} docstring violations:")
        for err in errors:
            print(f"  {err}")
        return 1
    print("OK: every public symbol has a NumPy-style docstring.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
