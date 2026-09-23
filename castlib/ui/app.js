/* cast-tv UI: one Alpine component over /api. Polls /api/status every 1.5 s
   (one request in flight at a time, 5 s between retries while the server is
   away). The selection lives here only, in memory, in the order it was ticked. */

const POLL_MS = 1500;
const OFFLINE_POLL_MS = 5000;
const POLL_TIMEOUT_MS = 8000;
const SOURCES = [
  { name: 'gopro', label: 'GoPro' },
  { name: 'onedrive', label: 'OneDrive' },
  { name: 'gphotos', label: 'Google Photos' },
];
const GATES = {
  gopro: {
    title: 'Connect GoPro',
    body: 'A gopro.com window opens on the computer running cast-tv. Sign in in that window. cast-tv then uses that browser session to access your GoPro media and closes the window.',
    cta: 'Open gopro.com',
    again: 'Open gopro.com again',
    note: 'The session is kept in ~/.config/cast-tv (Windows: %APPDATA%\\cast-tv), readable by you only.',
    window: true,            // the hand-off: a window on the host; the paste appears only on detail.fallback
    expired: 'cast-tv couldn’t access your GoPro media with this session.',
    expiredBody: 'Open gopro.com again to reconnect.',
  },
  onedrive: {
    title: 'Connect OneDrive',
    body: 'Sign in once with a code you type on any device — this phone included. The sign-in refreshes itself for about 90 days.',
    cta: 'Connect',
    note: 'Files.Read · offline_access · User.Read',
    expired: 'The OneDrive sign-in expired',
    expiredBody: 'Microsoft no longer accepts the stored sign-in (revoked, or older than 90 days). This list is what was fetched last; connect again to keep going.',
  },
  gphotos: {
    title: 'Connect Google Photos',
    body: 'Google Photos cannot be browsed. Consent in this computer’s browser; then pick photos in Google’s own picker from any device, this phone included. While cast-tv’s Google app is in testing, Google asks again about once a week.',
    cta: 'Connect',
    note: 'photospicker.mediaitems.readonly',
    expired: 'The Google Photos consent expired',
    expiredBody: 'Google no longer accepts the stored consent (revoked, or the test-user token ran out). These are the picks of this session; connect again to keep going.',
  },
};
const ACTIVE = ['preparing', 'starting', 'playing', 'paused'];

async function api(method, path, body, opts) {
  const init = { method, headers: { 'Accept': 'application/json' }, credentials: 'same-origin' };
  if (body !== undefined) {
    init.headers['Content-Type'] = 'application/json';
    init.body = JSON.stringify(body);
  } else if (method === 'POST') {
    init.headers['Content-Type'] = 'application/json';
    init.body = '{}';
  }
  let timer = null;
  if (opts && opts.timeout) {              // the polls give up; user actions (discover, cast) wait
    const ctl = new AbortController();
    init.signal = ctl.signal;
    timer = setTimeout(() => ctl.abort(), opts.timeout);
  }
  let r;
  try { r = await fetch(path, init); } finally { if (timer) clearTimeout(timer); }
  let data = null;
  try { data = await r.json(); } catch (e) { data = null; }
  if (!r.ok) {
    const err = (data && data.error) || { code: 'http_' + r.status, message: 'cast-tv answered ' + r.status };
    throw err;
  }
  return data;
}

function castTv() {
  return {
    status: { tv: null, tvs: [], interfaces: [], cast: null, show: null, sources: {}, session: [], errors: 0, settings: { interval: 8 }, firewall_hint: '', firewall_blocked: null, firewall_advice: '' },
    errors: [],
    lists: {},               // per source: { items, next, loaded, loading, error }
    tokenInput: '',
    linkInput: '',
    pickNote: '',            // the outcome of the last pick that did not land (timeout, error)
    linkNote: '',            // why the last pasted share link was refused; the status poll leaves it alone
    _picksSeq: null,         // picks_seq of the Google Photos list this page has fetched
    chooser: null,           // key of the tile whose variant chooser is open
    selection: [],
    tab: 'gopro',
    filter: 'all',
    interval: 8,
    presets: [3, 5, 8, 12, 20],
    tvMenu: false,
    manualIp: '',
    panel: false,
    toast: '',
    offline: false,
    busy: { discover: false, connect: false, show: false, stop: false, cast: false },
    gateNote: {},
    dismissedCast: null,
    dismissedShowId: null,
    sourceTabs: SOURCES,
    _timer: null,
    _toastTimer: null,
    _refreshing: false,
    _retryAt: 0,
    _errorsSeq: 0,           // errors_seq of the list last fetched successfully
    _verified: {},           // sources whose stored token this page already asked to verify

    async init() {
      await this.refresh();
      this.$watch('tab', t => this.enterTab(t));
      this.enterTab(this.tab);
      this._timer = setInterval(() => {
        if (document.visibilityState === 'hidden') return;
        if (this.offline && Date.now() < this._retryAt) return;   // slower while the server is away
        this.refresh();
      }, POLL_MS);
      document.addEventListener('visibilitychange', () => { if (document.visibilityState === 'visible') this.refresh(); });
    },

    async refresh() {
      if (this._refreshing) return;         // one status request in flight: an old answer never lands on a newer one
      this._refreshing = true;
      try {
        const s = await api('GET', '/api/status', undefined, { timeout: POLL_TIMEOUT_MS });
        this.status = s;
        this.offline = false;
        if (s.settings && typeof s.settings.interval === 'number') this.interval = s.settings.interval;
        // errors_seq grows past the ring's size; a failed list fetch leaves _errorsSeq behind, so it is retried
        if (this.panel || (s.errors_seq || 0) !== this._errorsSeq) await this.loadErrors();
        this.watchPicks(s);
        this.ensureList(this.tab);
      } catch (e) {
        this.offline = true;
        this._retryAt = Date.now() + OFFLINE_POLL_MS;
      } finally {
        this._refreshing = false;
      }
    },

    async loadErrors() {
      try {
        const d = await api('GET', '/api/errors', undefined, { timeout: POLL_TIMEOUT_MS });
        this.errors = (d.errors || []).slice().reverse();
        this._errorsSeq = d.seq || 0;
      } catch (e) { /* the status poll reports the outage */ }
    },

    // ------------------------------------------------------------ TV
    tvLabel() {
      const tv = this.status.tv;
      if (!tv || !tv.ip) return this.busy.discover || this.status.discovering ? 'Searching…' : 'No TV';
      return tv.name || tv.ip;
    },
    tvTitle() {
      const tv = this.status.tv;
      if (!tv || !tv.ip) return 'No TV selected';
      return tv.name + ' · ' + tv.ip + ' · ' + tv.state;
    },
    tvDot() {
      const tv = this.status.tv;
      if (this.busy.discover || this.status.discovering) return 'busy';
      if (!tv || !tv.ip) return '';
      return tv.state === 'ready' ? 'ready' : (tv.state === 'unreachable' ? 'unreachable' : '');
    },
    async rediscover() {
      this.busy.discover = true;
      try {
        const d = await api('POST', '/api/tv/discover');
        this.status.tvs = d.tvs;
        this.status.tv = d.tv;
        this.status.interfaces = d.interfaces || [];
        if (!d.tv || !d.tv.ip) this.flash('No DLNA renderer answered.');
      } catch (e) { this.flash(e.message); }
      this.busy.discover = false;
      this.tvMenu = false;
    },
    async selectTv(ip) {
      if (!ip) return;
      try {
        const d = await api('POST', '/api/tv/select', { ip });
        this.status.tv = d.tv;
        this.tvMenu = false;
        this.manualIp = '';
      } catch (e) { this.flash(e.message); }
    },

    // ------------------------------------------------------------ sources
    source(name) { return (this.status.sources && this.status.sources[name]) || null; },
    connected(name) {
      const s = this.source(name);
      return !!s && s.state === 'connected';
    },
    expired(name) {
      const s = this.source(name);
      return !!s && s.state === 'expired';
    },
    sourceHint(name) {
      const s = this.source(name);
      if (!s) return 'not connected';
      if (s.state === 'connected') {
        const d = s.detail || {};
        if (d.account || d.age) return d.account || d.age;
        if (typeof d.picks === 'number') return d.picks ? d.picks + ' picked' : 'nothing picked yet';
        return 'connected';
      }
      if (s.state === 'expired') return this.gate(name).window ? 'reconnect needed' : 'sign-in expired';
      if (s.state === 'connecting') {
        const step = s.detail && s.detail.step;
        if (step === 'browser') return 'gopro.com window open…';
        return step === 'code' ? 'enter the code…' : (step === 'consent' ? 'waiting for consent…' : 'connecting…');
      }
      if (s.detail && s.detail.stored) return 'checking…';
      return 'not connected';
    },
    headerLine(name) {
      const d = this.source(name) && this.source(name).detail;
      if (!d) return '';
      return d.age || (d.account ? 'signed in as ' + d.account : '');
    },
    // a multi-step sign-in in progress: the gate shows the code (OneDrive), the consent link (Google)
    // or the waiting line for the gopro.com window on the host
    connecting(name) {
      const s = this.source(name);
      return !!s && s.state === 'connecting' && !!s.detail && ['code', 'consent', 'browser'].includes(s.detail.step);
    },
    connectStep(name) {
      const s = this.source(name);
      return (s && s.detail && s.detail.step) || '';
    },
    // how the last round ended, from the status poll (never a user-action message: that is gateNote)
    flowError(name) {
      const s = this.source(name);
      const d = s && s.detail;
      const e = d && d.flow_error;
      if (!e) return '';
      if (d.fallback && (e.code === 'no_browser' || e.code === 'browser_failed')) return '';   // the fallback block carries that reason
      return String(e.message || '').split('\n')[0];
    },
    // GoPro: no window could be opened here, so the paste applies; the steps come from the server, one source of truth
    fallback(name) {
      const s = this.source(name);
      return (s && s.detail && s.detail.fallback) || null;
    },
    fallbackText(name) {
      const f = this.fallback(name);
      if (!f) return '';
      const reason = String(f.reason || '').trim().replace(/\.$/, '');
      return 'cast-tv could not open a gopro.com window here: ' + reason + '. A token pasted from a signed-in browser works instead:';
    },
    openWindow(name) { this.connect(name, { fresh: true }); },
    expiredText(name) {
      const g = this.gate(name);
      if (g.window) return g.expired + ' ' + g.expiredBody;    // the decided sentence, no times
      const s = this.source(name);
      const e = s && s.detail && s.detail.error;
      return (e && String(e.message || '').split('\n')[0]) || 'The sign-in is no longer valid. Connect again.';
    },
    cancelConnect(name) { this.connect(name, { cancel: true }); },
    gate(name) { return GATES[name] || { title: 'Connect ' + name, body: '', cta: 'Connect', note: '' }; },
    // entering a tab verifies a stored-but-unverified token once, and fetches the list once connected
    enterTab(name) {
      this.chooser = null;
      const s = this.source(name);
      if (!s) return;
      if (s.state === 'disconnected' && s.detail && s.detail.stored && !this._verified[name]) {
        this._verified[name] = true;
        this.connect(name, {});
      } else {
        this.ensureList(name);
      }
    },
    async connect(name, params) {
      this.busy.connect = true;
      try {
        await api('POST', '/api/sources/' + name + '/connect', params || {});
        this.gateNote[name] = '';
        this.tokenInput = '';
        if (this.lists[name]) this.lists[name].loaded = false;   // a new token: list again
        await this.refresh();
        this.ensureList(name);
      } catch (e) {
        this.gateNote[name] = e.code === 'unknown_source'
          ? 'This source is not wired up in this build yet.'
          : String(e.message || '').split('\n')[0] + (e.hint ? ' ' + e.hint : '');   // the first line; the steps are on screen already
        await this.refresh();                                    // the state may have flipped to expired
      }
      this.busy.connect = false;
    },
    saveToken(name) {
      if (!this.tokenInput.trim()) return;
      this.connect(name, { token: this.tokenInput });
    },
    listOf(name) {
      if (!this.lists[name]) this.lists[name] = { items: [], folders: [], crumbs: [], path: null, next: null, loaded: false, loading: false, error: '' };
      return this.lists[name];
    },
    listVisible(name) {
      if (this.connecting(name)) return false;                   // the gate shows the code, whatever was listed before
      const l = this.lists[name];
      return this.connected(name) || !!(l && l.loaded);          // an expired token keeps the last list on screen
    },
    openFolder(name, id) {
      const l = this.listOf(name);
      l.path = id || null;
      l.items = [];
      l.folders = [];
      l.next = null;
      l.loaded = false;
      this.chooser = null;
      this.loadList(name);
    },
    ensureList(name) {
      const l = this.lists[name];
      const s = this.source(name);
      const listed = !!s && s.state !== 'expired' && !!s.detail && s.detail.picks > 0;   // pasted links list without a sign-in
      if (!(this.connected(name) || listed) || (l && (l.loaded || l.loading))) return;
      this.loadList(name);
    },
    async loadList(name, more) {
      const l = this.listOf(name);
      if (l.loading) return;
      l.loading = true;
      l.error = '';
      try {
        const q = [];
        if (l.path) q.push('path=' + encodeURIComponent(l.path));
        if (more && l.next) q.push('page=' + encodeURIComponent(l.next));
        const d = await api('GET', '/api/sources/' + name + '/list' + (q.length ? '?' + q.join('&') : ''));
        l.items = more ? l.items.concat(d.items || []) : (d.items || []);
        if (!more) l.folders = d.folders || [];
        l.crumbs = d.crumbs || [];
        l.next = d.next || null;
        l.loaded = true;
      } catch (e) {
        l.error = e.message;
        if (['token_rejected', 'no_token', 'refresh_rejected', 'graph_unauthorized', 'picker_unauthorized'].includes(e.code)) await this.refresh();   // the gate or banner takes over
      } finally {
        l.loading = false;
      }
    },
    items(name) {
      const l = this.lists[name];
      return (l && l.items) || [];
    },
    emptyText(name) {
      if (name === 'gphotos') return this.filter === 'all' ? 'Nothing picked yet. Pick in Google Photos, or paste a share link below.' : 'Nothing of that kind picked yet.';
      return 'Nothing castable here.';
    },

    // ------------------------------------------------------------ Google Photos: the pick
    pickState() {
      const s = this.source('gphotos');
      return (s && s.detail && s.detail.pick) || null;
    },
    pickWaiting() {
      const p = this.pickState();
      return !!p && p.state === 'waiting';
    },
    // the server's picks_seq moves when a pick lands, a session drops or a link is added: fetch the list again
    watchPicks(s) {
      const g = s.sources && s.sources.gphotos;
      const seq = g && g.detail && typeof g.detail.picks_seq === 'number' ? g.detail.picks_seq : null;
      if (seq === null) return;
      if (this._picksSeq !== null && seq !== this._picksSeq && this.lists.gphotos) this.lists.gphotos.loaded = false;
      this._picksSeq = seq;
      const p = g.detail.pick;
      if (p && p.state === 'timeout') this.pickNote = 'The picker timed out before anything was picked. Pick again when you are ready.';
      else if (p && p.state === 'error' && p.error) this.pickNote = String(p.error.message || '').split('\n')[0] + (p.error.hint ? ' ' + p.error.hint : '');
      else this.pickNote = '';
    },
    async startPick() {
      this.busy.connect = true;
      try {
        await api('POST', '/api/sources/gphotos/pick', {});
        this.pickNote = '';
        await this.refresh();
      } catch (e) {
        this.pickNote = String(e.message || '').split('\n')[0] + (e.hint ? ' ' + e.hint : '');
        await this.refresh();                                    // a 401 flips the tab to expired
      }
      this.busy.connect = false;
    },
    async cancelPick() {
      try {
        await api('POST', '/api/sources/gphotos/pick', { cancel: true });
        await this.refresh();
      } catch (e) { this.flash(e.message); }
    },
    async addLink() {
      const link = this.linkInput.trim();
      if (!link) return;
      this.busy.connect = true;
      try {
        await api('POST', '/api/sources/gphotos/link', { link });
        this.linkInput = '';
        this.linkNote = '';
        if (this.lists.gphotos) this.lists.gphotos.loaded = false;
        await this.refresh();
      } catch (e) {
        this.linkNote = String(e.message || '').split('\n')[0] + (e.hint ? ' ' + e.hint : '');
      }
      this.busy.connect = false;
    },
    visible(list) {
      if (this.filter === 'all') return list;
      return list.filter(it => it.kind === this.filter);
    },

    // ------------------------------------------------------------ selection
    key(it) { return it.source + ':' + it.id; },
    isSelected(it) { return this.selection.some(s => this.key(s) === this.key(it)); },
    toggle(it) {
      const k = this.key(it);
      const i = this.selection.findIndex(s => this.key(s) === k);
      if (i >= 0) this.selection.splice(i, 1);
      else this.selection.push({ source: it.source, id: it.id, name: it.name, kind: it.kind });
    },
    clearSelection() { this.selection = []; },

    // ------------------------------------------------------------ playback
    async castNow(it, quality) {
      if (it.variants && it.variants.length && !quality) {     // a heavy clip: the choice first
        this.chooser = this.chooser === this.key(it) ? null : this.key(it);
        return;
      }
      this.chooser = null;
      if (this.busy.cast) return;                 // a double tap sends one cast, not two
      this.busy.cast = true;
      try {
        const body = { source: it.source, id: it.id };
        if (quality) body.quality = quality;
        await api('POST', '/api/cast', body);
        this.dismissedCast = null;
        await this.refresh();
      } catch (e) { this.flash(e.message); }
      finally { this.busy.cast = false; }
    },
    async startShow() {
      if (!this.selection.length) return;
      this.busy.show = true;
      try {
        await api('POST', '/api/show', {
          items: this.selection.map(s => ({ source: s.source, id: s.id })),
          interval: this.interval,
        });
        this.selection = [];
        this.dismissedShowId = null;
        this.dismissedCast = null;
        await this.refresh();
      } catch (e) { this.flash(e.message); }
      this.busy.show = false;
    },
    async restartShow() {
      const show = this.status.show;
      if (!show || !show.items || !show.items.length) return;
      try {
        await api('POST', '/api/show', {
          items: show.items.map(s => ({ source: s.source, id: s.id })),
          interval: this.interval,
        });
        this.dismissedShowId = null;
        await this.refresh();
      } catch (e) { this.flash(e.message); }
    },
    async showCtl(what) {
      try {
        const d = await api('POST', '/api/show/' + what);
        this.status.show = d.show;
      } catch (e) { this.flash(e.message); }
    },
    async stopAll() {
      this.busy.stop = true;
      try {
        await api('POST', '/api/stop');
        await this.refresh();
      } catch (e) { this.flash(e.message); }
      this.busy.stop = false;
    },
    async setInterval(v) {
      v = Math.round(Number(v));
      if (!(v >= 2 && v <= 600)) return;
      this.interval = v;
      try {
        const d = await api('POST', '/api/settings', { interval: v });
        this.status.settings = d.settings;
      } catch (e) { this.flash(e.message); }
    },

    // ------------------------------------------------------------ derived state
    castActive() {
      const c = this.status.cast;
      return !!c && ACTIVE.includes(c.state);
    },
    castFailed() {
      const c = this.status.cast;
      return !!c && c.state === 'failed' && !!c.error && this.dismissedCast !== c.generation;
    },
    castStateLabel() {
      const c = this.status.cast;
      if (!c) return '';
      if (c.state === 'preparing') {
        if (c.kind === 'photo') return 'converting…';
        return c.progress != null ? 'downloading ' + Math.round(c.progress * 100) + '%' : 'resolving…';
      }
      if (c.state === 'starting') return 'waiting for the TV…';
      if (c.state === 'paused') return 'paused';
      if (c.state === 'playing') return c.kind === 'photo' ? 'on screen' : 'playing';
      return c.state;
    },
    castTimes() {
      const c = this.status.cast;
      if (!c) return '';
      if (c.kind === 'photo') {
        const r = this.status.show && this.status.show.remaining;
        return r == null ? (c.state === 'playing' ? 'on screen' : this.castStateLabel()) : Math.ceil(r) + ' s';
      }
      return (c.position || '-') + ' / ' + (c.duration || '-');
    },
    castProgress() {
      const c = this.status.cast;
      if (!c) return 0;
      if (c.kind === 'photo') return this.showProgress();
      const p = toSec(c.position), d = toSec(c.duration);
      return d > 0 ? Math.min(100, 100 * p / d) : 0;
    },
    showActive() {
      const s = this.status.show;
      return !!s && (s.state === 'playing' || s.state === 'paused') && !this.showDismissed();
    },
    showDismissed() {
      const s = this.status.show;
      return !s || (this.dismissedShowId !== null && this.dismissedShowId === s.id) || s.state === 'cancelled' || s.state === 'stopped';
    },
    dismissShow() { if (this.status.show) this.dismissedShowId = this.status.show.id; },
    showPos() {
      const s = this.status.show;
      if (!s) return '';
      return (Math.max(0, s.index) + 1) + ' / ' + s.total;
    },
    showStateLabel() {
      const s = this.status.show;
      if (!s) return '';
      if (s.state === 'paused') return 'paused';
      if (s.state === 'playing') return s.skipped ? s.skipped + ' skipped' : 'running';
      return s.state;
    },
    showProgress() {
      const s = this.status.show;
      if (!s || s.remaining == null || !s.interval) return 0;
      return Math.max(0, Math.min(100, 100 * (1 - s.remaining / s.interval)));
    },
    nextLabel() {
      const s = this.status.show;
      if (!s) return '';
      if (s.state === 'paused') return 'Paused';
      if (!s.next) return 'Last item';
      if (s.current && s.current.kind === 'video') return 'Next after the video';
      if (s.remaining == null) return 'Next';
      return 'Next in ' + Math.ceil(s.remaining) + ' s';
    },
    idleLabel() {
      const tv = this.status.tv;
      if (!tv || !tv.ip) return 'No TV selected';
      if (tv.state === 'unreachable') return 'The TV is not answering';
      return window.matchMedia('(hover: none)').matches ? 'Tap a tile to cast it' : 'Nothing playing — TV ready';
    },
    togglePanel() {
      this.panel = !this.panel;
      if (this.panel) this.loadErrors();
    },
    cardClass(e) {
      if (['tv_fetched_nothing', 'tv_unreachable', 'tv_rejected', 'tv_never_started', 'no_tv'].includes(e.code)) return 'bad';
      if (['dts_audio', 'token_rejected', 'no_token', 'refresh_rejected', 'graph_unauthorized', 'expired_token',
           'authorization_declined', 'bad_verification_code', 'no_client_id', 'picker_unauthorized',
           'consent_timeout', 'consent_declined', 'no_google_client', 'repick_needed',
           'no_browser', 'browser_failed', 'browser_closed', 'browser_timeout'].includes(e.code)) return 'warn';
      return '';
    },

    // ------------------------------------------------------------ helpers
    metaOf(it) {
      const parts = [];
      if (it.width && it.height) parts.push(it.width + ' × ' + it.height);
      if (it.size) parts.push(fmtSize(it.size));
      if (it.duration) parts.push(fmtDur(it.duration));
      if (!parts.length && it.mime) parts.push(it.mime);
      return parts.join(' · ');
    },
    fmtDur(sec) { return fmtDur(sec); },
    fmtTime(t) {
      if (!t) return '';
      const d = new Date(t * 1000);
      return d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' });
    },
    hueOf(name) {
      let h = 0;
      for (const ch of String(name || '')) h = (h * 31 + ch.charCodeAt(0)) % 360;
      return h;
    },
    flash(msg) {
      this.toast = msg || 'Something went wrong.';
      clearTimeout(this._toastTimer);
      this._toastTimer = setTimeout(() => { this.toast = ''; }, 5000);
    },
    async copy(text) {
      try {
        await navigator.clipboard.writeText(text);
        this.flash('Copied.');
      } catch (e) {
        window.prompt('Copy this command:', text);
      }
    },
  };
}

function fmtSize(n) {
  if (!n) return '';
  const units = ['B', 'KB', 'MB', 'GB'];
  let i = 0;
  while (n >= 1024 && i < units.length - 1) { n /= 1024; i++; }
  return (i >= 2 ? n.toFixed(1) : Math.round(n)) + ' ' + units[i];
}

function fmtDur(sec) {
  if (!sec && sec !== 0) return '';
  sec = Math.round(sec);
  const h = Math.floor(sec / 3600), m = Math.floor((sec % 3600) / 60), s = sec % 60;
  const mm = h ? String(m).padStart(2, '0') : String(m);
  return (h ? h + ':' : '') + mm + ':' + String(s).padStart(2, '0');
}

function toSec(text) {
  if (!text) return 0;
  const parts = String(text).split(':').map(Number);
  if (parts.some(isNaN)) return 0;
  return parts.reduce((acc, v) => acc * 60 + v, 0);
}

document.addEventListener('alpine:init', () => {
  Alpine.data('castTv', castTv);
});
