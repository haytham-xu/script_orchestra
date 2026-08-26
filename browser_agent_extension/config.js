// Browser Agent — shared config + feature registry.
// The popup is a thin, extensible launcher: each feature registers itself
// with an id, a label, and a run() function. To add a feature later, drop a
// new file in features/, call registerFeature(...), and reference it in
// popup.html's <script> list — no changes to the core needed.

const BACKEND_BASE = 'http://127.0.0.1:50001';

const _features = [];

function registerFeature(feature) {
  // feature: { id: string, label: string, run: (ctx) => Promise<string> }
  _features.push(feature);
}

function getFeatures() {
  return _features.slice();
}

// Small helper features use to POST JSON to the backend.
async function postJson(path, body) {
  const res = await fetch(BACKEND_BASE + path, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body)
  });
  if (!res.ok) throw new Error('HTTP ' + res.status);
  return res.json();
}
