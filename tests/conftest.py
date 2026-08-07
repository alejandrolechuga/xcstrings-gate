"""Test-suite bootstrapping.

Adds the tool directory to ``sys.path`` so tests can ``import xcstrings_gate``
and ``import xcstrings_io`` regardless of where pytest is invoked from.
"""
import sys
from pathlib import Path

TOOL_DIR = Path(__file__).resolve().parent.parent
if str(TOOL_DIR) not in sys.path:
    sys.path.insert(0, str(TOOL_DIR))
