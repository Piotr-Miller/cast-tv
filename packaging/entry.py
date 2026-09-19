"""The release binary's entry point: ``cast-tv`` as the console script runs it."""
import sys

from castlib import platform

platform.use_system_ca_bundle()     # before any HTTPS: the bundled OpenSSL looks where Ubuntu keeps it

from castlib.cli import main_tv     # noqa: E402

sys.exit(main_tv())
