"""
conftest.py — Pytest configuration for the shared nbe_schemas package.
Ensures nbe_schemas is importable from tests without installing.
"""

import sys
from pathlib import Path

# Add the shared schemas source onto the path for tests
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "shared" / "nbe_schemas" / "src"))
