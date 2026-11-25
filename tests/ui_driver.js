// Runs the castTv() component of castlib/ui/app.js in node against scripted /api answers, so a
// test can drive the page's own logic (refresh, connect, listVisible) without a browser or Alpine.
//
//   node tests/ui_driver.js castlib/ui/app.js [castlib/ui/qrcode.js ...] < script.json
//
// Further files are scripts the page loads before app.js (qrcode.js), evaluated in the same scope.
//
// stdin: {"steps": [...]}; each step is one of
//   {"status": {...}}                       the answer to every GET /api/status from now on
//   {"answer": {"path": "/api/...", "body": {...}}}   the answer to that path from now on (any method;
//                                           a body with "error" answers 400)
//   {"call": "<method>", "args": [...]}     await component.<method>(...args), then let the
//                                           un-awaited fetches it started (loadList) settle
//   {"read": "<method or field>", "args": [...]}   record the value (a method is called with args)
//   {"copy": false}                         document.execCommand('copy') fails from now on
//   {"hold": "/api/..."}                    requests to that path wait from now on, until
//   {"release": "/api/..."}                 ... this answers them (and later ones at once)
//   {"fail": "/api/...", "value": true}     requests to that path fail like a dropped connection
//                                           (false: answer again)
//   {"start": "<method>", "args": [...]}    call component.<method>(...args) without awaiting it
//   {"wait": true}                          let timers, animation frames and fetches settle
//   {"set": {"tab": "onedrive"}}             change component state and notify registered watchers
//   {"requests": true}                      record a snapshot of the requests so far
// With top-level manualRender:true, $nextTick and requestAnimationFrame use controlled queues:
//   {"tick": true} / {"frame": true}          advance one render tick / one animation frame
// stdout: {"reads": [...], "requests": ["GET /api/status", "POST /api/sources/gopro/connect", ...],
//          "bodies": [["POST /api/sources/nextcloud/connect", {"server": "..."}], ...] (every request with a body),
//          "copied": ["copy: <text>" through execCommand, or "prompt: <label> <text>" when it was refused]}
'use strict';
const fs = require('fs');

const src = process.argv.slice(3).map(f => fs.readFileSync(f, 'utf8') + '\n').join('')
  + fs.readFileSync(process.argv[2], 'utf8');
const script = JSON.parse(fs.readFileSync(0, 'utf8'));
const requests = [];
const bodies = [];
let status = { sources: {}, session: [], errors: 0, settings: { interval: 8 } };
const answers = {};
const held = {};           // path -> resolvers of requests waiting for {"release": path}; absent when not held
const failing = {};

async function fetch(path, init) {
  const method = (init && init.method) || 'GET';
  requests.push(method + ' ' + path);
  if (init && init.body !== undefined) bodies.push([method + ' ' + path, JSON.parse(init.body)]);
  const key = path.split('?')[0];
  let body;
  if (key === '/api/status') body = status;
  else if (answers[key] !== undefined) body = answers[key];
  else body = { error: { code: 'not_scripted', message: 'not scripted: ' + method + ' ' + path } };
  const fail = failing[key];
  if (held[key]) await new Promise(resolve => held[key].push(resolve));
  if (fail) throw new TypeError('Failed to fetch');
  const ok = !(body && body.error);
  return { ok, status: ok ? 200 : 400, json: async () => body };
}

const copied = [];         // what copy() put on the clipboard through execCommand; {"copy": false} refuses it
let copyWorks = true;
let lastCreated = null;
const document = {
  addEventListener() {}, visibilityState: 'visible',
  body: { appendChild() {} },
  createElement: () => (lastCreated = { style: {}, setAttribute() {}, select() {}, remove() {} }),
  execCommand(cmd) {
    const ok = cmd === 'copy' && copyWorks;
    if (ok && lastCreated) copied.push('copy: ' + lastCreated.value);
    return ok;
  },
};
const window = { matchMedia: () => ({ matches: false }), prompt: (label, text) => copied.push('prompt: ' + label + ' ' + text) };
const ticks = [], frames = [], watchers = new Map();
const requestAnimationFrame = cb => script.manualRender ? frames.push(cb) : setTimeout(cb, 1);
const castTv = new Function('fetch', 'document', 'window', 'requestAnimationFrame', src + '\nreturn castTv;')(
  fetch, document, window, requestAnimationFrame);
const app = new Proxy(castTv(), {
  set(target, key, value) {
    const old = target[key];
    target[key] = value;
    if (old !== value) for (const cb of watchers.get(key) || []) queueMicrotask(() => cb(value, old));
    return true;
  },
});
app.$nextTick = cb => script.manualRender ? ticks.push(cb) : Promise.resolve().then(cb);
app.$watch = (key, cb) => watchers.set(key, [...(watchers.get(key) || []), cb]);
const settle = () => new Promise(resolve => setTimeout(resolve, 0));
const quiet = async () => { for (let i = 0; i < 10; i++) await new Promise(resolve => setTimeout(resolve, 5)); };
let backgroundError;

(async () => {
  const reads = [];
  for (const step of script.steps) {
    if (step.status !== undefined) status = step.status;
    else if (step.copy !== undefined) copyWorks = step.copy;
    else if (step.answer) answers[step.answer.path] = step.answer.body;
    else if (step.hold) held[step.hold] = held[step.hold] || [];
    else if (step.release) { const waiting = held[step.release] || []; delete held[step.release]; waiting.forEach(r => r()); await quiet(); }
    else if (step.fail) failing[step.fail] = step.value !== false;
    else if (step.start) Promise.resolve(app[step.start](...(step.args || []))).catch(e => { backgroundError = e; });
    else if (step.wait) await quiet();
    else if (step.set) { Object.assign(app, step.set); await settle(); }
    else if (step.requests) reads.push(requests.slice());
    else if (step.tick || step.frame) {
      const queue = step.tick ? ticks : frames;
      for (const cb of queue.splice(0)) cb();       // callbacks queued by this frame belong to the next frame
      await settle();
    }
    else if (step.call) { await app[step.call](...(step.args || [])); await settle(); }
    else if (step.read) {
      const v = app[step.read];
      reads.push(typeof v === 'function' ? v.apply(app, step.args || []) : v);
    } else throw new Error('unknown step: ' + JSON.stringify(step));
  }
  await settle();
  if (backgroundError) throw backgroundError;
  process.stdout.write(JSON.stringify({ reads, requests, bodies, copied }), () => process.exit(0));   // init() leaves its poll timer running
})().catch(e => { process.stderr.write(String((e && e.stack) || e)); process.exit(1); });
