"""The Google client a release carries: written by ``packaging/write_client.py`` at build time.

The repository keeps this stub. A Desktop-app client's secret cannot be kept
confidential (Google's own docs), but a public repo is still the wrong place for
it: GitHub's push protection blocks it and a leak reported to Google can revoke
it for every copy at once. So only a release build fills these in, from the
repository secrets ``GOOGLE_CLIENT_ID`` and ``GOOGLE_CLIENT_SECRET``.
"""
CLIENT_ID = None
CLIENT_SECRET = None
