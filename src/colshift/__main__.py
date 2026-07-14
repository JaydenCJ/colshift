"""Allow ``python -m colshift`` to run the CLI without installing."""

import sys

from colshift.cli import main

if __name__ == "__main__":
    sys.exit(main())
