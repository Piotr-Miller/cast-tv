// Runs the castTv() component of castlib/ui/app.js in node against scripted /api answers, so a
// test can drive the page's own logic (refresh, connect, listVisible) without a browser or Alpine.
//
//   node tests/ui_driver.js castlib/ui/app.js < script.json
//
// stdin: {"steps": [...]}; each step is one of
//   {"status": {...}}                       the answer to every GET /api/status from now on
//   {"answer": {"path": "/api/...", "body": {...}}}   the answer to that path from now on (any method;
//                                           a body with "error" answers 400)
//   {"call": "<method>", "args": [...]}     await component.<method>(...args), then let the
//                                           un-awaited fetches it started (loadList) settle
//   {"read": "<method or field>", "args": [...]}   record the value (a method is called with args)
// stdout: {"reads": [...], "requests": ["GET /api/status", "POST /api/sources/gopro/connect", ...]}
'use strict';
const fs = require('fs');

const src = fs.readFileSync(process.argv[2], 'utf8');
const script = JSON.parse(fs.readFileSync(0, 'utf8'));
const requests = [];
let status = { sources: {}, session: [], errors: 0, settings: { interval: 8 } };
const answers = {};

async function fetch(path, init) {
  const method = (init && init.method) || 'GET';
  requests.push(method + ' ' + path);
  const key = path.split('?')[0];
  let body;
  if (key === '/api/status') body = status;
  else if (answers[key] !== undefined) body = answers[key];
  else body = { error: { code: 'not_scripted', message: 'not scripted: ' + method + ' ' + path } };
  const ok = !(body && body.error);
  return { ok, status: ok ? 200 : 400, json: async () => body };
}

const document = { addEventListener() {}, visibilityState: 'visible' };
const window = { matchMedia: () => ({ matches: false }) };
const castTv = new Function('fetch', 'document', 'window', src + '\nreturn castTv;')(fetch, document, window);
const app = castTv();
const settle = () => new Promise(resolve => setTimeout(resolve, 0));

(async () => {
  const reads = [];
  for (const step of script.steps) {
    if (step.status !== undefined) status = step.status;
    else if (step.answer) answers[step.answer.path] = step.answer.body;
    else if (step.call) { await app[step.call](...(step.args || [])); await settle(); }
    else if (step.read) {
      const v = app[step.read];
      reads.push(typeof v === 'function' ? v.apply(app, step.args || []) : v);
    } else throw new Error('unknown step: ' + JSON.stringify(step));
  }
  process.stdout.write(JSON.stringify({ reads, requests }));
})().catch(e => { process.stderr.write(String((e && e.stack) || e)); process.exit(1); });
