"""Write the owner's Google client into ``castlib/auth/_builtin_client.py`` for a release build.

Reads ``GOOGLE_CLIENT_ID`` and ``GOOGLE_CLIENT_SECRET`` from the environment (the
release workflow maps the repository secrets onto them) and fails when either is
empty, so a release never ships without a client. Prints neither value.
Run from the repository root; never commit the file it writes.
"""
import os
import sys

TARGET = os.path.join("castlib", "auth", "_builtin_client.py")


def main() -> int:
    cid = os.environ.get("GOOGLE_CLIENT_ID", "").strip()
    secret = os.environ.get("GOOGLE_CLIENT_SECRET", "").strip()
    if not cid or not secret:
        print("GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET must both be set.", file=sys.stderr)
        return 1
    with open(TARGET, "w", encoding="utf-8") as fh:
        fh.write('"""Written by packaging/write_client.py for a release build."""\n')
        fh.write("CLIENT_ID = %r\nCLIENT_SECRET = %r\n" % (cid, secret))
    print("Google client written to %s." % TARGET)
    return 0


if __name__ == "__main__":
    sys.exit(main())
