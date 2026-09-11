"""The static UI: four files, exact match, nothing else."""
from tests.conftest import request


def test_static_exact_match_only(server):
    srv, base = server
    status, headers, body, conn = request(base, "GET", "/ui/")
    assert status == 200
    assert headers["Content-Type"].startswith("text/html")
    assert headers["Content-Length"] == str(len(body))
    assert b"cast-tv" in body and b"x-data" in body
    for path, ctype in (("/ui/app.js", "application/javascript"),
                        ("/ui/style.css", "text/css"),
                        ("/ui/alpine.min.js", "application/javascript")):
        status, headers, body, _ = request(base, "GET", path, conn=conn)
        assert status == 200, path
        assert headers["Content-Type"].startswith(ctype)
        assert headers["Content-Length"] == str(len(body)) and body
    for path in ("/ui/index.html", "/ui/../castlib/server.py", "/ui/app.js/", "/ui/x",
                 "/ui/%2e%2e/pyproject.toml", "/ui/APP.JS"):
        status, headers, body, _ = request(base, "GET", path, conn=conn)
        assert status == 404, path
        assert headers["Content-Type"].startswith("application/json")
    status, headers, _, _ = request(base, "GET", "/ui", conn=conn)
    assert status == 302 and headers["Location"] == "/ui/"
    s1, h1, b1, _ = request(base, "HEAD", "/ui/", conn=conn)
    assert s1 == 200 and b1 == b"" and h1["Content-Length"] == str(len(open_ui_bytes()))
    status, _, _, _ = request(base, "POST", "/ui/", conn=conn)
    assert status == 404


def test_root_redirects(server):
    srv, base = server
    status, headers, _, _ = request(base, "GET", "/")
    assert status == 302 and headers["Location"] == "/ui/"


def test_ui_needs_a_local_host_header(server):
    srv, base = server
    status, _, _, _ = request(base, "GET", "/ui/", {"Host": "evil.example"})
    assert status == 403


def test_ui_is_self_contained():
    """The LAN UI loads nothing from the internet: no fonts, no preconnect, no CDN."""
    from castlib.server import UI_DIR
    import os
    for name in ("index.html", "style.css", "app.js"):
        with open(os.path.join(UI_DIR, name), encoding="utf-8") as fh:
            text = fh.read()
        assert "https://" not in text and "http://" not in text, name
        assert "preconnect" not in text, name


def open_ui_bytes():
    from castlib.server import UI_DIR
    import os
    with open(os.path.join(UI_DIR, "index.html"), "rb") as fh:
        return fh.read()
