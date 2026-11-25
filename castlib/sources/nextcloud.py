"""Nextcloud over WebDAV: Login Flow v2 sign-in, folder browsing, media fetched with the app password.

The owner types the server address and grants access in the browser
(``castlib.auth.loginflow``); cast-tv receives its own app password, kept in
``config_dir()/nextcloud.json`` (mode 0600 on POSIX), listed and revocable
under the server's Settings -> Security. There is no refresh: a 401 on a call
the source makes itself means the password was revoked, and the tab turns
expired.

Folders are ``PROPFIND`` listings under ``/remote.php/dav/files/<user id>/``.
A folder id is its path relative to that root; a file id is its ``oc:fileid``.
Every URL that carries the password is built here from the canonical base
plus an encoded path, never taken from the server. The server's XML is read
through ``defusedxml`` with DTDs, entities and external references refused.
"""
from __future__ import annotations

import collections
import datetime
import email.utils
import re
import threading
import time
import urllib.parse
from xml.etree.ElementTree import ParseError
from xml.sax.saxutils import escape

import defusedxml
import defusedxml.ElementTree

from castlib.auth import loginflow
from castlib.auth.apppassword import AppPasswordStore
from castlib.errors import AuthError, CastError, ConfigError, NotMedia, UpstreamError
from castlib.items import MediaItem, Upstream
from castlib.media import kind_from_facets, note_hidden_kind
from castlib.sources.base import Entry, Folder, Listing

NAME = "nextcloud"
PAGE_SIZE = 200
CACHE_ITEMS = 4000              # files remembered per process (LRU); an evicted one is found again with SEARCH
SNAPSHOTS = 8                   # folder listings kept for their later pages
XML_LIMIT = 32 << 20            # bytes of XML read from the server; one byte more is refused unparsed
PREVIEW = "/index.php/core/preview?fileId=%s&x=512&y=512&a=1"
DAV, OC, NC = "DAV:", "http://owncloud.org/ns", "http://nextcloud.org/ns"
ID_RE = re.compile(r"[0-9]{1,20}")
PAGE_RE = re.compile(r"[0-9]{1,9}")
ROOT_CRUMB = {"id": None, "name": "Nextcloud"}
PROPS = ("<d:getlastmodified/><d:getcontenttype/><d:getcontentlength/><d:resourcetype/>"
         "<d:getetag/><oc:fileid/><oc:size/><nc:has-preview/>")
XMLNS = 'xmlns:d="DAV:" xmlns:oc="http://owncloud.org/ns" xmlns:nc="http://nextcloud.org/ns"'
PROPFIND = ('<?xml version="1.0" encoding="UTF-8"?><d:propfind %s><d:prop>%s</d:prop></d:propfind>'
            % (XMLNS, PROPS)).encode("utf-8")


# ---------------------------------------------------------------- paths
def check_path(path) -> str:
    """A folder path relative to the files root: ``""`` for the root; ``ConfigError("bad_path")`` otherwise."""
    if path is None or path == "":
        return ""
    if (not isinstance(path, str) or path.startswith("/")
            or any(ord(c) < 32 or ord(c) == 127 for c in path)
            or any(seg in ("", ".", "..") for seg in path.split("/"))):
        raise ConfigError("bad_path", "Not a Nextcloud folder path.", source=NAME)
    return path


def _clean_relative(path: str) -> str | None:
    try:
        return check_path(path)
    except ConfigError:
        return None


def parse_xml(data: bytes):
    """The root element of a server answer; hostile or malformed XML is ``UpstreamError``, never parsed loosely."""
    if len(data) > XML_LIMIT:
        raise UpstreamError("nextcloud_too_large", "The Nextcloud server's answer is too large to read.",
                            source=NAME)
    try:
        return defusedxml.ElementTree.fromstring(data, forbid_dtd=True, forbid_entities=True,
                                                 forbid_external=True)
    except (defusedxml.DefusedXmlException, ParseError, ValueError):
        raise UpstreamError("nextcloud_xml", "The Nextcloud server's answer is not readable WebDAV.",
                            source=NAME) from None


def multistatus(root) -> list[dict]:
    """``[{href, props}]`` in the server's order; only ``propstat`` blocks with status 200 count."""
    out = []
    for response in root.iter("{%s}response" % DAV):
        href = response.findtext("{%s}href" % DAV)
        if not href:
            continue
        props: dict = {}
        for propstat in response.findall("{%s}propstat" % DAV):
            status = (propstat.findtext("{%s}status" % DAV) or "").split()
            if len(status) < 2 or status[1] != "200":
                continue
            prop = propstat.find("{%s}prop" % DAV)
            if prop is None:
                continue
            for el in prop:
                if el.tag == "{%s}resourcetype" % DAV:
                    props[el.tag] = el.find("{%s}collection" % DAV) is not None
                else:
                    props[el.tag] = (el.text or "").strip()
        out.append({"href": href.strip(), "props": props})
    return out


def tile_date(value) -> str | None:
    """The UTC date of an RFC 1123 ``getlastmodified``; ``None`` when missing or unreadable."""
    if not value:
        return None
    try:
        when = email.utils.parsedate_to_datetime(value)
    except (TypeError, ValueError, IndexError):
        return None
    if when is None:
        return None
    if when.tzinfo is not None:
        when = when.astimezone(datetime.timezone.utc)
    return when.strftime("%Y-%m-%d")


def _int(value) -> int | None:
    return int(value) if isinstance(value, str) and value.isdigit() else None


def _mime(value) -> str:
    return (value or "").split(";")[0].strip().lower()


# ---------------------------------------------------------------- source
class NextcloudSource:
    """The ``Source`` contract over WebDAV, one server and one account at a time.

    Like OneDrive: a generation counter bumped by every sign-in and
    disconnect, so a late answer from an older generation changes nothing;
    a sign-in thread with a stop event; a bounded memory of listed files.
    """

    name = NAME

    def __init__(self):
        self._lock = threading.Lock()
        self._flow_lock = threading.Lock()
        self._store = AppPasswordStore(NAME)
        self._gen = 0
        self._flow_epoch = 0                     # also invalidates starts still waiting for their first answer
        self._flow: dict | None = None            # the login in progress: {base, login_url, expires_at}
        self._flow_stop: threading.Event | None = None
        self._flow_error: dict | None = None
        self._revoke_error: dict | None = None
        self._last_server: str | None = None      # the address to prefill after a disconnect
        self._verified_at: float | None = None
        self._expired_at: float | None = None
        self._error: dict | None = None
        self._files: collections.OrderedDict[str, dict] = collections.OrderedDict()   # file id -> record, LRU
        self._snapshots: collections.OrderedDict[str, tuple] = collections.OrderedDict()   # path -> (folders, files)

    # ------------------------------------------------------- credential
    def _credential(self) -> tuple[dict, loginflow.Base, int]:
        with self._lock:
            gen, record = self._gen, self._store.load()
        if record is None:
            raise AuthError("no_token", "Not signed in.", source=NAME)
        try:
            base = loginflow.normalise(record["server"])
        except ConfigError:
            raise AuthError("no_token", "The stored Nextcloud address is unusable. Connect again.",
                            source=NAME) from None
        return record, base, gen

    def _check_generation(self, gen: int) -> None:
        """Reject an old account's result; caller holds _lock."""
        if gen != self._gen:
            raise AuthError("cancelled", "The Nextcloud connection changed. Try again.", source=NAME)

    def _mark_expired(self, err: AuthError, gen: int) -> None:
        with self._lock:
            if gen == self._gen:
                self._expired_at = time.time()
                self._error = err.as_dict()

    def _root(self, record: dict, base: loginflow.Base) -> str:
        """The files root's path on the server, percent-encoded, with a trailing ``/``."""
        return "%s/remote.php/dav/files/%s/" % (base.path, urllib.parse.quote(record["user_id"], safe=""))

    def _url(self, record: dict, base: loginflow.Base, rel: str, folder: bool = False) -> str:
        origin = loginflow.Base(base.scheme, base.host, base.port).url
        tail = urllib.parse.quote(rel, safe="/")
        return origin + self._root(record, base) + tail + ("/" if folder and rel else "")

    def _dav(self, method: str, url: str, headers: dict, body: bytes, record: dict, gen: int) -> bytes:
        """One WebDAV call with the app password; a 401 expires the sign-in, a non-207 is ``UpstreamError``."""
        status, data = loginflow.call(method, url, dict(
            {"Authorization": loginflow.basic(record["login"], record["password"]),
             "Content-Type": "application/xml; charset=utf-8"}, **headers), body, limit=XML_LIMIT + 1)
        if status == 401:
            err = loginflow._unauthorized()
            self._mark_expired(err, gen)
            raise err
        if status != 207:
            raise UpstreamError("nextcloud_http", "The Nextcloud server answered %d to %s." % (status, method),
                                source=NAME)
        return data

    # --------------------------------------------------------- the flow
    def _start_flow(self, base: loginflow.Base) -> dict:
        with self._flow_lock:
            with self._lock:
                running = self._flow
            if running is not None and running["base"] == base:
                return dict(self.status(), step="login")
            self._cancel_flow()
            with self._lock:
                epoch, gen = self._flow_epoch, self._gen
            flow = loginflow.start(base)
            stop = threading.Event()
            record = {"base": base, "login_url": flow["login"], "expires_at": flow["expires_at"]}
            with self._lock:
                if epoch != self._flow_epoch or gen != self._gen:
                    raise AuthError("cancelled", "The sign-in was cancelled while it was starting.", source=NAME)
                self._flow, self._flow_stop = record, stop
                self._flow_error = self._revoke_error = None
                self._last_server = base.url
            threading.Thread(target=self._wait_for_password, args=(flow, record, stop, gen),
                             name="nextcloud-loginflow", daemon=True).start()
        return dict(self.status(), step="login")

    def _end_flow(self, record: dict, gen: int, error: CastError | None) -> bool:
        """Clear the flow if it is still the current one; ``False`` when it was replaced or cancelled."""
        with self._lock:
            if self._gen != gen or self._flow is not record:
                return False
            self._flow, self._flow_stop = None, None
            if error is not None and error.code != "cancelled":
                self._flow_error = error.as_dict()
            return True

    def _wait_for_password(self, flow: dict, record: dict, stop: threading.Event, gen: int) -> None:
        try:
            self._finish_flow(flow, record, stop, gen)
        except Exception:                        # the thread must not die with the link still on show
            self._end_flow(record, gen, UpstreamError(
                "flow_failed", "The sign-in could not be completed.", source=NAME))

    def _finish_flow(self, flow: dict, record: dict, stop: threading.Event, gen: int) -> None:
        base = flow["base"]
        try:
            answer = loginflow.poll(flow, stop)
        except CastError as e:
            self._end_flow(record, gen, e)
            return
        login, password = answer["loginName"], answer["appPassword"]
        try:
            who = loginflow.user(base, login, password)
        except CastError as e:
            self._end_flow(record, gen, e)
            self._quiet_revoke(base, login, password)        # unusable or no longer wanted: never left live
            return
        with self._lock:
            current = self._gen == gen and self._flow is record
            replaced = self._store.load() if current else None
            if current:
                self._save_sign_in(base, login, password, who)
        if not current:                          # cancelled or replaced meanwhile: the answer is dropped,
            self._quiet_revoke(base, login, password)    # and its password, handed over once, revoked
            return
        if replaced is not None and replaced["password"] != password:
            try:                                 # a fresh sign-in over a stored one: the old password goes
                old = loginflow.normalise(replaced["server"])
            except ConfigError:
                return
            self._quiet_revoke(old, replaced["login"], replaced["password"])

    def _save_sign_in(self, base, login: str, password: str, who: dict) -> None:
        """Store a granted sign-in and make it current; caller holds _lock."""
        account = who["displayname"]
        self._store.save({"server": base.url, "login": login, "user_id": who["id"],
                          "password": password,
                          "account": "%s (%s)" % (account, login) if account and account != login else login})
        self._flow, self._flow_stop = None, None
        self._flow_error = self._revoke_error = None
        self._gen += 1
        self._verified_at, self._expired_at, self._error = time.time(), None, None
        self._last_server = base.url
        self._files.clear()
        self._snapshots.clear()

    @staticmethod
    def _quiet_revoke(base, login, password) -> None:
        try:
            loginflow.revoke(base, login, password)
        except Exception:
            pass

    def _cancel_flow_locked(self):
        self._flow_epoch += 1
        stop, self._flow, self._flow_stop = self._flow_stop, None, None
        return stop

    def _cancel_flow(self) -> None:
        with self._lock:
            stop = self._cancel_flow_locked()
        if stop is not None:
            stop.set()

    def close(self) -> None:
        self._cancel_flow()

    # ---------------------------------------------------------- contract
    def status(self) -> dict:
        with self._lock:
            flow, flow_error, revoke_error = self._flow, self._flow_error, self._revoke_error
            expired, verified, error, last = self._expired_at, self._verified_at, self._error, self._last_server
            record = self._store.load()
        if flow is not None:
            return {"state": "connecting", "detail": {
                "stored": record is not None, "step": "login", "login_url": flow["login_url"],
                "expires_in": max(0, int(flow["expires_at"] - time.time())),
                "server": flow["base"].url}}
        if record is None:
            detail: dict = {"stored": False}
            if last:
                detail["server"] = last
            if flow_error:
                detail["flow_error"] = flow_error
            if revoke_error:
                detail["revoke_error"] = revoke_error
            return {"state": "disconnected", "detail": detail}
        if expired is not None:
            state = "expired"
        elif verified is not None:
            state = "connected"
        else:
            state = "disconnected"               # stored but not yet verified in this process
        detail = {"stored": True, "account": record.get("account"), "server": record["server"],
                  "verified_at": verified, "error": error}
        if flow_error:
            detail["flow_error"] = flow_error
        return {"state": state, "detail": detail}

    def connect(self, params: dict) -> dict:
        """``{server}`` starts a fresh login for that address; ``{}`` verifies the stored password,
        or starts a login on the stored server when it expired; ``{cancel: true}`` ends a login."""
        params = params if isinstance(params, dict) else {}
        if params.get("cancel"):
            self._cancel_flow()
            return self.status()
        server = params.get("server")
        if server not in (None, ""):
            return self._start_flow(loginflow.normalise(server))
        with self._lock:
            running, expired = self._flow is not None, self._expired_at is not None
            record, gen, epoch = self._store.load(), self._gen, self._flow_epoch
        if running:
            return dict(self.status(), step="login")
        if record is None:
            raise ConfigError("no_server", "Type the address of your Nextcloud server, then press Connect.",
                              source=NAME)
        base = loginflow.normalise(record["server"])
        if expired:
            return self._start_flow(base)
        try:
            who = loginflow.user(base, record["login"], record["password"])
        except AuthError as e:
            self._mark_expired(e, gen)
            raise
        with self._lock:
            if self._gen == gen and self._flow_epoch == epoch:
                if who["id"] != record["user_id"]:
                    self._store.save(dict(record, user_id=who["id"]))
                self._gen += 1
                self._verified_at, self._expired_at, self._error = time.time(), None, None
                self._flow_error = self._revoke_error = None
                self._files.clear()
                self._snapshots.clear()
        return self.status()

    def disconnect(self) -> None:
        """Detach locally at once; revoke the detached password without touching a later sign-in."""
        with self._lock:
            stop = self._cancel_flow_locked()
            self._gen += 1
            gen, epoch = self._gen, self._flow_epoch
            record = self._store.load()
            self._store.clear()
            self._verified_at = self._expired_at = self._error = self._flow_error = None
            self._revoke_error = None
            self._files.clear()
            self._snapshots.clear()
            if record is not None:
                self._last_server = record["server"]
        if stop is not None:
            stop.set()
        problem = None
        if record is not None:
            try:
                base = loginflow.normalise(record["server"])
                loginflow.revoke(base, record["login"], record["password"])
            except AuthError:
                pass                             # 401: the password is already gone on the server
            except Exception:
                problem = {"code": "revoke_failed", "message":
                           "The Nextcloud server did not confirm that cast-tv's app password was removed; "
                           "cast-tv may still be listed under Settings -> Security on the server."}
        with self._lock:
            if gen == self._gen and epoch == self._flow_epoch:
                self._revoke_error = problem

    # ----------------------------------------------------------- listing
    def _records(self, record: dict, base: loginflow.Base, answer: list[dict]) -> list[tuple[str, dict]]:
        """``[(relative path, props)]`` for the hrefs that lie under the files root; others are dropped."""
        root = urllib.parse.unquote(self._root(record, base))
        out = []
        for entry in answer:
            href = entry["href"]
            if href.startswith("//"):
                continue
            if "://" in href:
                if not loginflow.same_origin(base, href):
                    continue
                href = urllib.parse.urlsplit(href).path
            if not href.startswith("/"):
                continue
            path = urllib.parse.unquote(href)
            if path + "/" == root:
                rel = ""
            elif path.startswith(root):
                rel = _clean_relative(path[len(root):].rstrip("/"))
                if rel is None:
                    continue
            else:
                continue
            out.append((rel, entry["props"]))
        return out

    def _file_record(self, rel: str, props: dict) -> dict | None:
        file_id = props.get("{%s}fileid" % OC) or ""
        if not ID_RE.fullmatch(file_id):
            return None
        return {"id": file_id, "path": rel, "name": rel.rsplit("/", 1)[-1],
                "mime": _mime(props.get("{%s}getcontenttype" % DAV)),
                "size": _int(props.get("{%s}getcontentlength" % DAV)),
                "etag": (props.get("{%s}getetag" % DAV) or "").strip('"') or None,
                "modified": props.get("{%s}getlastmodified" % DAV) or None,
                "preview": (props.get("{%s}has-preview" % NC) or "").lower() == "true"}

    @staticmethod
    def _kind(rec: dict) -> str | None:
        return kind_from_facets(NAME, {"getcontenttype": rec["mime"]})

    def _entry(self, rec: dict, kind: str) -> Entry:
        return Entry(source=NAME, id=rec["id"], name=rec["name"], kind=kind, date=tile_date(rec["modified"]),
                     size=rec["size"], mime=rec["mime"],
                     thumb="/api/sources/nextcloud/thumb/%s" % rec["id"] if rec["preview"] else None)

    def _remember(self, rec: dict) -> None:
        self._files[rec["id"]] = rec             # caller holds _lock
        self._files.move_to_end(rec["id"])
        while len(self._files) > CACHE_ITEMS:
            self._files.popitem(last=False)

    def _snapshot(self, rel: str) -> tuple[list[Folder], list[Entry]]:
        record, base, gen = self._credential()
        data = self._dav("PROPFIND", self._url(record, base, rel, folder=True), {"Depth": "1"},
                         PROPFIND, record, gen)
        answer = self._records(record, base, multistatus(parse_xml(data)))
        folders, files, records, seen = [], [], [], set()
        for path, props in answer:
            if path == rel:
                continue                         # the collection's own response
            if path.rsplit("/", 1)[0] != rel and (rel or "/" in path):
                continue                         # not a direct child
            file_id = props.get("{%s}fileid" % OC) or ""
            if ID_RE.fullmatch(file_id):
                if file_id in seen:
                    continue
                seen.add(file_id)
            if props.get("{%s}resourcetype" % DAV):
                folders.append(Folder(id=path, name=path.rsplit("/", 1)[-1]))
                continue
            rec = self._file_record(path, props)
            if rec is None:
                continue
            kind = self._kind(rec)
            if kind is None:
                note_hidden_kind(NAME, rec["mime"] or "no type")
                continue
            records.append(rec)
            files.append(self._entry(rec, kind))
        folders.sort(key=lambda f: f.name.casefold())
        files.sort(key=lambda e: e.name.casefold())
        with self._lock:
            self._check_generation(gen)
            for rec in records:
                self._remember(rec)
            self._snapshots[rel] = (folders, files, {rec["id"]: rec for rec in records})
            self._snapshots.move_to_end(rel)
            while len(self._snapshots) > SNAPSHOTS:
                self._snapshots.popitem(last=False)
        return folders, files

    def list(self, path=None, page=None) -> Listing:
        rel = check_path(path)
        _, _, gen = self._credential()
        offset = 0
        if page not in (None, ""):
            if not isinstance(page, str) or not PAGE_RE.fullmatch(page):
                raise ConfigError("bad_page", "Not a Nextcloud page.", source=NAME)
            offset = int(page)
        snap = None
        if offset:
            with self._lock:
                self._check_generation(gen)
                snap = self._snapshots.get(rel)
        folders, files = snap[:2] if snap is not None else self._snapshot(rel)
        chunk = files[offset:offset + PAGE_SIZE]
        end = offset + PAGE_SIZE
        with self._lock:
            self._check_generation(gen)
            return Listing(items=list(chunk), folders=list(folders) if offset == 0 else [],
                           next=str(end) if end < len(files) else None, crumbs=self._crumbs(rel))

    @staticmethod
    def _crumbs(rel: str) -> list[dict]:
        crumbs = [dict(ROOT_CRUMB)]
        if rel:
            parts = rel.split("/")
            for i, name in enumerate(parts):
                crumbs.append({"id": "/".join(parts[:i + 1]), "name": name})
        return crumbs

    # ------------------------------------------------------------- files
    def _search(self, file_id: str) -> dict | None:
        """The one ``SEARCH`` on ``oc:fileid`` for a file this process never listed."""
        record, base, gen = self._credential()
        scope = escape("/files/%s" % urllib.parse.quote(record["user_id"], safe=""))
        body = ('<?xml version="1.0" encoding="UTF-8"?><d:searchrequest %s><d:basicsearch>'
                '<d:select><d:prop>%s</d:prop></d:select>'
                '<d:from><d:scope><d:href>%s</d:href><d:depth>infinity</d:depth></d:scope></d:from>'
                '<d:where><d:eq><d:prop><oc:fileid/></d:prop><d:literal>%s</d:literal></d:eq></d:where>'
                '<d:orderby/></d:basicsearch></d:searchrequest>' % (XMLNS, PROPS, scope, file_id)).encode("utf-8")
        origin = loginflow.Base(base.scheme, base.host, base.port).url
        url = origin + base.path + "/remote.php/dav/"
        data = self._dav("SEARCH", url, {}, body, record, gen)
        for path, props in self._records(record, base, multistatus(parse_xml(data))):
            if not path or props.get("{%s}resourcetype" % DAV):
                continue
            rec = self._file_record(path, props)
            if rec is not None and rec["id"] == file_id:
                with self._lock:
                    self._check_generation(gen)
                    self._remember(rec)
                    return rec
        with self._lock:
            self._check_generation(gen)
        return None

    def _file(self, file_id: str) -> dict | None:
        """A listed file from the LRU or a kept folder snapshot; ``SEARCH`` only for one never listed here."""
        with self._lock:
            rec = self._files.get(file_id)
            if rec is None:
                for _, _, by_id in reversed(self._snapshots.values()):
                    rec = by_id.get(file_id)
                    if rec is not None:
                        break
            if rec is not None:
                self._remember(rec)
                return rec
        return self._search(file_id)

    def resolve(self, source_id: str, quality: str = "auto") -> MediaItem:
        """An unregistered item whose ``resolve`` gives the file's WebDAV URL with the app password;
        a video is marked ``download`` (fetched whole before the TV hears of it, ``castlib.downloads``)."""
        if not isinstance(source_id, str) or not ID_RE.fullmatch(source_id):
            raise NotMedia("bad_id", "Not a Nextcloud file id.", source=NAME, item=str(source_id)[:64])
        _, _, gen = self._credential()
        rec = self._file(source_id)
        with self._lock:
            self._check_generation(gen)
        kind = self._kind(rec) if rec is not None else None
        if kind is None:
            raise NotMedia("unknown_item", "That item is not a photo or video on this Nextcloud.",
                           source=NAME, item=source_id)
        source = self
        rel = rec["path"]

        def fresh() -> Upstream:
            record, base, _ = source._credential()
            with source._lock:
                source._check_generation(gen)
                return Upstream(source._url(record, base, rel),
                                {"Authorization": loginflow.basic(record["login"], record["password"])})

        return MediaItem(kind=kind, title=rec["name"], mime=rec["mime"], source=NAME, source_id=source_id,
                         version=rec["etag"] or "%s:%s" % (rec["modified"] or "", rec["size"] or ""),
                         resolve=fresh, size=rec["size"],
                         download=kind == "video")   # a film is fetched whole first: relayed over Wi-Fi it stalled

    def thumb(self, source_id: str) -> Upstream | None:
        """The server's preview of a photo (HEIC included) when ``nc:has-preview`` says it has one."""
        if not isinstance(source_id, str) or not ID_RE.fullmatch(source_id):
            return None
        record, base, gen = self._credential()
        rec = self._file(source_id)
        with self._lock:
            self._check_generation(gen)
            if rec is None or not rec["preview"]:
                return None
            return Upstream(base.url + PREVIEW % source_id,
                            {"Authorization": loginflow.basic(record["login"], record["password"])})
