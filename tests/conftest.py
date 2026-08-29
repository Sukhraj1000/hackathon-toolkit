import sys, os
# Ensure project `src/` directory and migrated package path are on sys.path for tests
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
SRC = os.path.join(ROOT, 'src')
MIGRATED = os.path.join(ROOT, 'hackathon-toolkit')
if SRC not in sys.path:
    sys.path.insert(0, SRC)
if MIGRATED not in sys.path:
    sys.path.insert(0, MIGRATED)
