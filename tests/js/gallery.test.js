const test = require('node:test');
const assert = require('node:assert');
const g = require('../../src/famsite/viewer/gallery.js');

const BASE = 'https://x.example/photos/';

function El(tag) { this.tag = tag; this.children = []; this.attrs = {}; this.textContent = ''; this.hidden = true; }
El.prototype.appendChild = function (c) { this.children.push(c); return c; };
El.prototype.setAttribute = function (k, v) { this.attrs[k] = String(v); };
const fakeDoc = () => ({ created: [], createElement(tag) { const e = new El(tag); this.created.push(e); return e; } });
function fakeSection(data) {
  const s = new El('section');
  s.dataset = data || {};
  s._thumbs = new El('ul');
  s._more = new El('a');
  s.querySelector = (sel) => (sel === '.gallery-thumbs' ? s._thumbs : sel === '.gallery-more a' ? s._more : null);
  return s;
}
const okResponse = (body) => ({ ok: true, status: 200, json: () => Promise.resolve(body) });
const photo = (n) => ({ name: 'p' + n + '.jpg', thumb: 'static/_gallery/p' + n + '.jpg', url: '#/collections/people/jane/p' + n });
const manifest = (extra) => Object.assign({
  version: 1,
  people: [{ name: 'Jane Doe', slug: 'jane-doe', url: '#/collections/people/jane-doe', count: 12, thumb: null, photos: [photo(1), photo(2)] }],
}, extra);
const noTimers = { setTimeout: () => 1, clearTimeout: () => {} };

test('normalizeBase keeps http(s) addresses and ends them in one slash', () => {
  assert.strictEqual(g.normalizeBase('https://x/p'), 'https://x/p/');
  assert.strictEqual(g.normalizeBase('https://x/p//'), 'https://x/p/');
  for (const bad of ['ftp://x/', 'javascript:1', 'https://x/?a', 'https://x/#a', '', 5, null]) assert.strictEqual(g.normalizeBase(bad), null, String(bad));
});

test('confine resolves under the base and refuses everything that could leave it', () => {
  assert.strictEqual(g.confine(BASE, 'static/a b.jpg'), BASE + 'static/a%20b.jpg');
  assert.strictEqual(g.confine(BASE, '#/collections/people/jane'), BASE + '#/collections/people/jane');
  for (const bad of ['https://evil/x', '//evil/x', '\\\\evil\\x', '../x', 'a/../../x', '%2e%2e/x', 'javascript:alert(1)', 'data:text/html,x', '', null, 5]) {
    assert.strictEqual(g.confine(BASE, bad), null, String(bad));
  }
});

test('fold lowercases, strips accents and folds special letters', () => {
  assert.strictEqual(g.fold('Zoë  Müller'), 'zoe muller');
  assert.strictEqual(g.fold('Straße Ørsted'), 'strasse orsted');
});

test('pickEntry finds by slug, then by exactly one matching name unless the id was explicit', () => {
  const people = [{ name: 'Zoë Müller', slug: 'zoe-muller-1' }, { name: 'Jane Doe', slug: 'jane-doe' }, null, 5];
  assert.strictEqual(g.pickEntry(people, 'jane-doe', false, 'Someone').slug, 'jane-doe');
  assert.strictEqual(g.pickEntry(people, 'zoe-muller', false, 'zoe muller').slug, 'zoe-muller-1');
  assert.strictEqual(g.pickEntry(people, 'zoe-muller', true, 'zoe muller'), null);
  const twins = [{ name: 'John Smith', slug: 'john-smith' }, { name: 'John Smith', slug: 'john-smith-1' }];
  assert.strictEqual(g.pickEntry(twins, 'smith-john', false, 'John Smith'), null);
  assert.strictEqual(g.pickEntry([{ name: '', slug: 'a' }], 'b', false, ''), null);
  assert.strictEqual(g.pickEntry([{ name: '山田', slug: 'a' }], 'b', false, '山田'), null);
});

test('shape caps at 6, drops hostile photos and rejects bad counts', () => {
  const many = { url: '#/c/jane', count: 10, photos: [1, 2, 3, 4, 5, 6, 7, 8, 9, 10].map(photo) };
  const s = g.shape(BASE, many);
  assert.strictEqual(s.photos.length, 6);
  assert.strictEqual(s.count, 10);
  assert.strictEqual(s.seeAllHref, BASE + '#/c/jane');
  assert.strictEqual(s.photos[0].thumbSrc, BASE + 'static/_gallery/p1.jpg');
  const hostile = { url: '#/c/jane', count: 3, photos: [photo(1), { name: 'x', thumb: 'https://evil.invalid/x.png', url: '#/a' }, { name: 'y', thumb: '../x.png', url: '#/a' }] };
  assert.strictEqual(g.shape(BASE, hostile).photos.length, 1);
  for (const count of [0, '3', -1, 1.5, NaN, undefined]) assert.strictEqual(g.shape(BASE, { url: '#/c', count, photos: [photo(1)] }), null, String(count));
  assert.strictEqual(g.shape(BASE, { url: '#/c', count: 2, photos: [{ name: 'x', thumb: '//evil/x', url: '#/a' }] }), null);
  assert.strictEqual(g.shape(BASE, { url: 'https://evil/x', count: 2, photos: [photo(1)] }), null);
  assert.strictEqual(g.shape(BASE, { url: '#/c', count: 1, photos: [photo(1), photo(2)] }).count, 2);
});

test('load (fussel) returns absolute, confined links', async () => {
  const calls = [];
  const deps = Object.assign({ fetch: (url, opts) => { calls.push([url, opts]); return Promise.resolve(okResponse(manifest())); } }, noTimers);
  const s = await g.load({ type: 'fussel', url: BASE }, { key: 'jane-doe', explicit: false, name: 'Jane Doe' }, deps);
  assert.strictEqual(calls[0][0], BASE + 'people.json');
  assert.strictEqual(calls[0][1].credentials, 'omit');
  assert.strictEqual(s.count, 12);
  assert.strictEqual(s.photos[0].thumbSrc, BASE + 'static/_gallery/p1.jpg');
  assert.strictEqual(s.seeAllHref, BASE + '#/collections/people/jane-doe');
});

test('load resolves null, never rejects, for every kind of bad answer', async () => {
  const person = { key: 'jane-doe', explicit: false, name: 'Jane Doe' };
  const run = (fetch, type) => g.load({ type: type || 'fussel', url: BASE }, person, Object.assign({ fetch }, noTimers));
  assert.strictEqual(await run(() => Promise.resolve(okResponse(manifest({ version: 2 })))), null);
  assert.strictEqual(await run(() => Promise.resolve(okResponse(manifest({ people: {} })))), null);
  assert.strictEqual(await run(() => Promise.resolve(okResponse(null))), null);
  assert.strictEqual(await run(() => Promise.resolve({ ok: false, status: 404, json: () => Promise.resolve(manifest()) })), null);
  assert.strictEqual(await run(() => Promise.resolve({ ok: true, json: () => Promise.reject(new Error('not json')) })), null);
  assert.strictEqual(await run(() => Promise.reject(new Error('cors'))), null);
  assert.strictEqual(await run(() => { throw new Error('sync'); }), null);
  assert.strictEqual(await run(() => Promise.resolve(okResponse(manifest())), 'immich'), null);
  assert.strictEqual(await g.load({ type: 'fussel', url: 'javascript:1' }, person, Object.assign({ fetch: () => Promise.reject(new Error('no')) }, noTimers)), null);
});

test('load gives up on a request that never answers once the timer fires', async () => {
  const timers = [];
  const deps = { fetch: () => new Promise(() => {}), setTimeout: (fn, ms) => { timers.push([fn, ms]); return timers.length; }, clearTimeout: () => {} };
  const pending = g.load({ type: 'fussel', url: BASE }, { key: 'jane-doe', explicit: false, name: 'Jane Doe' }, deps);
  assert.strictEqual(timers[0][1], 5000);
  timers[0][0]();
  assert.strictEqual(await pending, null);
});

test('render builds thumbnails with DOM calls only, then reveals the section', () => {
  const doc = fakeDoc();
  const section = fakeSection();
  const evil = '<img src=x onerror=alert(1)>';
  g.render(section, { count: 12, seeAllHref: BASE + '#/c/jane', photos: [{ name: evil, thumbSrc: BASE + 'a.jpg', href: BASE + '#/a' }, { name: 'b.jpg', thumbSrc: BASE + 'b.jpg', href: BASE + '#/b' }] }, doc);
  assert.strictEqual(section._thumbs.children.length, 2);
  const link = section._thumbs.children[0].children[0];
  assert.strictEqual(link.attrs.target, '_blank');
  assert.match(link.attrs.rel, /noopener/);
  const img = link.children[0];
  assert.strictEqual(img.attrs.loading, 'lazy');
  assert.strictEqual(img.attrs.alt, evil);
  assert.strictEqual(img.attrs.src, BASE + 'a.jpg');
  assert.ok(doc.created.every((e) => ['li', 'a', 'img'].includes(e.tag)));
  assert.strictEqual(section._more.textContent, 'See all 12 photos in the gallery');
  assert.strictEqual(section._more.attrs.href, BASE + '#/c/jane');
  assert.match(section._more.attrs.rel, /noopener/);
  assert.strictEqual(section.hidden, false);
  const one = fakeSection();
  g.render(one, { count: 1, seeAllHref: BASE + '#/c', photos: [{ name: 'a', thumbSrc: BASE + 'a.jpg', href: BASE + '#/a' }] }, fakeDoc());
  assert.strictEqual(one._more.textContent, 'See the photo in the gallery');
});

test('init shows the block on success and leaves it hidden on failure', async () => {
  const data = { galleryType: 'fussel', galleryUrl: BASE, galleryKey: 'jane-doe', galleryExplicit: '0', galleryName: 'Jane Doe' };
  const good = fakeSection(data);
  const doc = Object.assign(fakeDoc(), { getElementById: () => good });
  await g.init(doc, Object.assign({ fetch: () => Promise.resolve(okResponse(manifest())) }, noTimers));
  assert.strictEqual(good.hidden, false);
  assert.strictEqual(good._thumbs.children.length, 2);

  const bad = fakeSection(data);
  const doc2 = Object.assign(fakeDoc(), { getElementById: () => bad });
  await g.init(doc2, Object.assign({ fetch: () => Promise.reject(new Error('down')) }, noTimers));
  assert.strictEqual(bad.hidden, true);

  await g.init(Object.assign(fakeDoc(), { getElementById: () => null }), noTimers);
});
