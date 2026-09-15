from castlib.server import parse_range
from tests.conftest import request


def _url(srv, item):
    return "/m/%s/%s" % (srv.media_token, item.id)


def test_start_beyond_size_is_416(server, local_file):
    srv, base = server
    item, data = local_file(srv)
    status, headers, body, _ = request(base, "GET", _url(srv, item),
                                       {"Range": "bytes=99999-"})
    assert status == 416
    assert headers["Content-Range"] == "bytes */%d" % len(data)
    assert body == b""


def test_bare_dash_is_full_body(server, local_file):
    srv, base = server
    item, data = local_file(srv)
    status, headers, body, _ = request(base, "GET", _url(srv, item), {"Range": "bytes=-"})
    assert status == 200
    assert body == data
    assert "Content-Range" not in headers


def test_multirange_is_full_body(server, local_file):
    srv, base = server
    item, data = local_file(srv)
    status, headers, body, _ = request(base, "GET", _url(srv, item),
                                       {"Range": "bytes=0-99,200-299"})
    assert status == 200
    assert body == data


def test_partial_and_tail_ranges(server, local_file):
    srv, base = server
    item, data = local_file(srv)
    status, headers, body, _ = request(base, "GET", _url(srv, item), {"Range": "bytes=2-4"})
    assert status == 206
    assert body == data[2:5]
    assert headers["Content-Range"] == "bytes 2-4/%d" % len(data)
    status, headers, body, _ = request(base, "GET", _url(srv, item), {"Range": "bytes=-5"})
    assert status == 206
    assert body == data[-5:]
    assert headers["Content-Range"] == "bytes %d-%d/%d" % (len(data) - 5, len(data) - 1,
                                                          len(data))


def test_parse_range_edge_cases():
    assert parse_range(None, 500) == (0, 499, False)
    assert parse_range("bytes=0-", 500) == (0, 499, True)
    assert parse_range("bytes=100-999", 500) == (100, 499, True)
    assert parse_range("bytes=-1000", 500) == (0, 499, True)
    assert parse_range("bytes=500-", 500) is None
    assert parse_range("bytes=-0", 500) is None
    assert parse_range("bytes=5-3", 500) == (0, 499, False)
    assert parse_range("items=0-1", 500) == (0, 499, False)
