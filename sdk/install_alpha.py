"""Private executable Alpha installer; no build or native replay."""
from pathlib import Path
import sys

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parent))
from rhook_alpha.install import main

if __name__ == '__main__': raise SystemExit(main())
