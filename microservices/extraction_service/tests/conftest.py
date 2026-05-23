"""
conftest.py — Pytest configuration for extraction_service tests.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "shared" / "nbe_schemas" / "src"))
