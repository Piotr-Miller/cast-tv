"""The release binary's entry point: ``cast-tv`` as the console script runs it."""
import sys

from castlib.cli import main_tv

sys.exit(main_tv())
