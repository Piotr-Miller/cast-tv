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
    body: 'GoPro has no public sign-in for apps. The token comes from a logged-in browser and lasts a few hours; the list shows how old it is.',
    cta: 'Paste a token',
    note: 'gopro.com → F12 → Network → the Authorization header',
  },
  onedrive: {
    title: 'Connect OneDrive',
    body: 'Sign in once with a code you type on any device. The token refreshes itself for about 90 days.',
    cta: 'Connect',
    note: 'Files.Read · offline_access',
  },
  gphotos: {
    title: 'Connect Google Photos',
    body: 'Google Photos cannot be browsed. Consent once in this machine’s browser; then pick photos in Google’s own picker from any device.',
    cta: 'Connect',
    note: 'photospicker.mediaitems.readonly',
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
    status: { tv: null, tvs: [], cast: null, show: null, sources: {}, session: [], errors: 0, settings: { interval: 8 }, firewall_hint: '' },
    errors: [],
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
    busy: { discover: false, connect: false, show: false, stop: false },
    gateNote: {},
    dismissedCast: null,
    dismissedShowId: null,
    sourceTabs: SOURCES,
    _timer: null,
    _toastTimer: null,
    _refreshing: false,
    _retryAt: 0,
    _errorsSeq: 0,           // errors_seq of the list last fetched successfully

    async init() {
      await this.refresh();
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
    connected(name) {
      const s = this.status.sources && this.status.sources[name];
      return !!s && s.state === 'connected';
    },
    sourceHint(name) {
      const s = this.status.sources && this.status.sources[name];
      if (!s) return 'not connected';
      if (s.state === 'connected') return (s.detail && (s.detail.account || s.detail.age)) || 'connected';
      if (s.state === 'expired') return 'token expired';
      if (s.state === 'connecting') return 'connecting…';
      return 'not connected';
    },
    gate(name) { return GATES[name] || { title: 'Connect ' + name, body: '', cta: 'Connect', note: '' }; },
    async connect(name) {
      this.busy.connect = true;
      try {
        await api('POST', '/api/sources/' + name + '/connect');
        await this.refresh();
      } catch (e) {
        this.gateNote[name] = e.code === 'unknown_source'
          ? 'This source is not wired up in this build yet.'
          : e.message;
      }
      this.busy.connect = false;
    },
    items(name) {
      const s = this.status.sources && this.status.sources[name];
      return (s && s.items) || [];
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
    async castNow(it) {
      try {
        await api('POST', '/api/cast', { source: it.source, id: it.id });
        this.dismissedCast = null;
        await this.refresh();
      } catch (e) { this.flash(e.message); }
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
      if (c.state === 'preparing') return c.kind === 'photo' ? 'converting…' : 'resolving…';
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
      if (['dts_audio', 'token_rejected', 'no_token'].includes(e.code)) return 'warn';
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
