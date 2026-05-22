from __future__ import annotations

import sys
from pathlib import Path

from .app import run


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("usage: python -m logseq.tui <vault>", file=sys.stderr)
        sys.exit(2)
    sys.exit(run(Path(sys.argv[1])))
