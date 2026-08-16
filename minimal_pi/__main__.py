"""python -m minimal_pi 入口（转发到 cli.main）。"""

import sys

from minimal_pi.cli import main

if __name__ == "__main__":
    sys.exit(main())
