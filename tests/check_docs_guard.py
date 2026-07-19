#!/usr/bin/env python3
"""CI-enforceable check that the docs/ boundary guard mechanism works.

Verifies that:
1. ``guard_path()`` raises ``PermissionError`` for paths under ``docs/``
2. ``guard_path()`` allows paths under ``data/``
3. ``DOCS_DIR`` resolves to the real ``docs/`` directory
4. ``swagger.html`` exists under ``DOCS_DIR``

Exits 0 on success, 1 on failure.
"""

import sys
from pathlib import Path

from soc_db.common import DOCS_DIR, guard_path

errors = 0


def check(name: str, ok: bool, detail: str = "") -> None:
    global errors
    if ok:
        print(f"  OK {name}")
    else:
        print(f"  FAIL {name}{': ' + detail if detail else ''}")
        errors += 1


# ---- DOCS_DIR resolution ----
check(
    "DOCS_DIR is a Path",
    isinstance(DOCS_DIR, Path),
)
check(
    "DOCS_DIR exists",
    DOCS_DIR.exists(),
    f"resolved to {DOCS_DIR}",
)
check(
    "swagger.html exists under DOCS_DIR",
    (DOCS_DIR / "swagger.html").exists(),
    f"looked at {DOCS_DIR / 'swagger.html'}",
)

# ---- guard_path allows data/ ----
data_path = DOCS_DIR.parent / "data" / "test_guard_check.json"
try:
    guard_path(data_path)
    check("guard_path allows data/ paths", True)
except PermissionError as e:
    check("guard_path allows data/ paths", False, str(e))

# ---- guard_path blocks docs/ ----
test_path = DOCS_DIR / "test_guard_check.txt"
try:
    guard_path(test_path)
    check("guard_path blocks docs/ paths", False, "should have raised PermissionError")
except PermissionError:
    check("guard_path blocks docs/ paths", True)

# ---- guard_path blocks exact DOCS_DIR ----
try:
    guard_path(DOCS_DIR)
    check("guard_path blocks exact DOCS_DIR", False, "should have raised PermissionError")
except PermissionError:
    check("guard_path blocks exact DOCS_DIR", True)

print()
if errors:
    print(f"FAILED: {errors} check(s) failed")
    sys.exit(1)
else:
    print("ALL OK — docs guard is working")
    sys.exit(0)
