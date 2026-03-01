"""
WAR ROOM — Pytest Configuration
Adds the backend directory to sys.path for imports.
"""

import sys
import os

# Add backend root to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
