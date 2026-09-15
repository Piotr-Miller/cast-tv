"""``python -m castlib`` behaves like the ``cast-tv`` command."""
import sys

from castlib.cli import main_tv

sys.exit(main_tv(sys.argv[1:]))
