'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const { api } = require('../shiftguard/static/dashboard.js');

function browserStubs(t) {
  const redirects = [];
  global.document = { querySelector: () => ({ content: 'session-token' }) };
  global.window = { location: { replace: path => redirects.push(path) } };
  t.after(() => { delete global.document; delete global.window; delete global.fetch; });
  return redirects;
}

test('dashboard sends CSRF with same-origin cookies', async t => {
  browserStubs(t);
  global.fetch = async (_path, options) => {
    assert.equal(options.headers.get('X-CSRFToken'), 'session-token');
    assert.equal(options.credentials, 'same-origin');
    return { ok: true, status: 204 };
  };
  assert.equal(await api('/api/example', { method: 'POST' }), null);
});

test('expired dashboard sessions return to login', async t => {
  const redirects = browserStubs(t);
  global.fetch = async () => ({
    ok: false, status: 401,
    json: async () => ({ error: 'Authentication required' })
  });
  await assert.rejects(api('/api/employees'), /Authentication required/);
  assert.deepEqual(redirects, ['/login']);
});
