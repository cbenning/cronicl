const test = require('node:test');
const assert = require('node:assert');
const g = require('../../src/cronicl/site/viewer/gallery.js');

const BASE = 'https://x.example/photos/';

function El(tag) { this.tag = tag; this.tagName = tag.toUpperCase(); this.children = []; this.attrs = {}; this.handlers = {}; this.textContent = ''; this.hidden = true; }
El.prototype.appendChild = function (c) { c.parentNode = this; this.children.push(c); return c; };
El.prototype.setAttribute = function (k, v) { this.attrs[k] = String(v); };
El.prototype.addEventListener = function (type, fn) { this.handlers[type] = fn; };
El.prototype.replaceChild = function (n, o) { n.parentNode = this; this.children[this.children.indexOf(o)] = n; this.replaced = [n, o]; };
El.prototype.find = function (pred) { if (pred(this)) return this; for (const c of this.children) { const f = c.find(pred); if (f) return f; } return null; };
const fakeDoc = (dialogs) => ({
  created: [],
  defaultView: dialogs ? { HTMLDialogElement: { prototype: { showModal() {} } } } : {},
  createElement(tag) {
    const e = new El(tag);
    this.created.push(e);
    if (tag === 'dialog') { e.shown = 0; e.showModal = function () { this.shown++; }; e.close = function () { this.closed = true; }; }
    return e;
  },
});
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


test('normalizeBase gives the canonical address the browser will compare against', () => {
  assert.strictEqual(g.normalizeBase('https://Example.com/photos'), 'https://example.com/photos/');
  assert.strictEqual(g.normalizeBase('HTTPS://host/photos/'), 'https://host/photos/');
  assert.strictEqual(g.normalizeBase('https://host:443/photos/'), 'https://host/photos/');
  assert.strictEqual(g.normalizeBase('http://host:80/p'), 'http://host/p/');
  assert.strictEqual(g.normalizeBase('https://b\u00fccher.de/p/'), 'https://xn--bcher-kva.de/p/');
  assert.strictEqual(g.normalizeBase('https://host/\u00e9/'), 'https://host/%C3%A9/');
  assert.strictEqual(g.normalizeBase('https://host/a/../b/'), 'https://host/b/');
  for (const bad of ['https://u:p@host/p', 'https://host/p/?', 'https://host/p/#', 'https://host/a b/']) assert.strictEqual(g.normalizeBase(bad), null, bad);
});

test('a non-canonical gallery address still shows photos', async () => {
  const deps = Object.assign({ fetch: (url) => { assert.strictEqual(url, 'https://example.com/photos/people.json'); return Promise.resolve(okResponse(manifest())); } }, noTimers);
  const s = await g.load({ type: 'fussel', url: 'https://Example.com:443/photos' }, { key: 'jane-doe', explicit: false, name: 'Jane Doe' }, deps);
  assert.strictEqual(s.photos[0].thumbSrc, 'https://example.com/photos/static/_gallery/p1.jpg');
});

test('names with letters that cannot be folded never match by name', () => {
  assert.strictEqual(g.fold('\u0418\u0432\u0430\u043d Smith'), '');
  assert.strictEqual(g.fold('O\u2019Brien'), 'o brien');
  assert.strictEqual(g.fold('Zo\u00eb'), 'zoe');
  const people = [{ name: '\u041c\u0430\u0440\u0438\u044f Smith', slug: 'maria-smith' }];
  assert.strictEqual(g.pickEntry(people, 'smith', false, '\u0418\u0432\u0430\u043d Smith'), null);
  assert.strictEqual(g.pickEntry(people, 'maria-smith', true, ''), people[0]);
});


const six = () => ({ count: 6, seeAllHref: BASE + '#/c', photos: [1, 2, 3, 4, 5, 6].map((n) => ({ name: 'p' + n, thumbSrc: BASE + 't' + n + '.jpg', viewSrc: BASE + 'v' + n + '.jpg', href: BASE + '#/p' + n })) });

test('stepIndex wraps in both directions', () => {
  assert.strictEqual(g.stepIndex(0, -1, 6), 5);
  assert.strictEqual(g.stepIndex(5, 1, 6), 0);
  assert.strictEqual(g.stepIndex(2, 1, 6), 3);
  assert.strictEqual(g.stepIndex(0, 1, 0), 0);
});

test('shape keeps a larger size and a face only when they stay under the gallery', () => {
  const base = { url: '#/c', count: 2 };
  const ph = (extra) => Object.assign({ name: 'a', thumb: 't.jpg', url: '#/a' }, extra);
  assert.strictEqual(g.shape(BASE, Object.assign({ photos: [ph({ src: 'big.jpg' })] }, base)).photos[0].viewSrc, BASE + 'big.jpg');
  for (const src of [undefined, null, 5, 'https://evil/x', '../x', '//evil/x']) {
    assert.strictEqual(g.shape(BASE, Object.assign({ photos: [ph({ src })] }, base)).photos[0].viewSrc, BASE + 't.jpg', String(src));
  }
  assert.strictEqual(g.shape(BASE, Object.assign({ thumb: 'face.jpg', photos: [ph()] }, base)).face, BASE + 'face.jpg');
  for (const thumb of [undefined, null, 5, 'https://evil/x', '../x']) assert.strictEqual(g.shape(BASE, Object.assign({ thumb, photos: [ph()] }, base)).face, null, String(thumb));
});

test('render lays out a featured first photo from three photos up', () => {
  const section = fakeSection();
  g.render(section, six(), fakeDoc());
  const items = section._thumbs.children;
  assert.strictEqual(section._thumbs.attrs['data-count'], '6');
  assert.deepStrictEqual(items.map((li) => li.attrs.class || ''), ['featured', '', '', '', '', '']);
  assert.strictEqual(items[0].children[0].children[0].attrs.src, BASE + 'v1.jpg');
  assert.strictEqual(items[1].children[0].children[0].attrs.src, BASE + 't2.jpg');
  const two = fakeSection();
  const s2 = six(); s2.photos = s2.photos.slice(0, 2);
  g.render(two, s2, fakeDoc());
  assert.strictEqual(two._thumbs.attrs['data-count'], '2');
  assert.deepStrictEqual(two._thumbs.children.map((li) => li.attrs.class || ''), ['', '']);
  assert.strictEqual(two._thumbs.children[0].children[0].children[0].attrs.src, BASE + 't1.jpg');
});

test('clicking a tile opens one reusable lightbox; modified clicks and old browsers keep the plain link', () => {
  const doc = fakeDoc(true);
  const section = fakeSection();
  g.render(section, six(), doc);
  const link = (i) => section._thumbs.children[i].children[0];
  const click = (i, extra) => { const ev = Object.assign({ prevented: false, preventDefault() { this.prevented = true; } }, extra); link(i).handlers.click(ev); return ev; };

  assert.strictEqual(click(2, { ctrlKey: true }).prevented, false);
  assert.strictEqual(click(2, { button: 1 }).prevented, false);
  assert.strictEqual(doc.created.filter((e) => e.tag === 'dialog').length, 0);

  assert.strictEqual(click(2).prevented, true);
  const dialogs = () => doc.created.filter((e) => e.tag === 'dialog');
  assert.strictEqual(dialogs().length, 1);
  const dlg = dialogs()[0];
  assert.strictEqual(dlg.shown, 1);
  const counter = dlg.find((e) => e.attrs.class === 'gallery-count');
  const photoLink = dlg.find((e) => e.attrs.class === 'gallery-open');
  const img = dlg.find((e) => e.tag === 'img' && e.attrs.class === 'gallery-big');
  assert.strictEqual(counter.textContent, '3 / 6');
  assert.strictEqual(photoLink.attrs.href, BASE + '#/p3');
  assert.match(photoLink.attrs.rel, /noopener/);
  assert.strictEqual(img.attrs.src, BASE + 'v3.jpg');

  dlg.handlers.keydown({ key: 'ArrowRight', preventDefault() {} });
  assert.strictEqual(counter.textContent, '4 / 6');
  click(0);
  assert.strictEqual(dialogs().length, 1);
  assert.strictEqual(dlg.shown, 2);
  assert.strictEqual(counter.textContent, '1 / 6');
  dlg.handlers.keydown({ key: 'ArrowLeft', preventDefault() {} });
  assert.strictEqual(counter.textContent, '6 / 6');
  assert.strictEqual(img.attrs.src, BASE + 'v6.jpg');
  img.handlers.error();
  assert.strictEqual(img.attrs.src, BASE + 't6.jpg');
  img.handlers.error();
  assert.strictEqual(img.attrs.src, BASE + 't6.jpg');
  dlg.handlers.click({ target: dlg });
  assert.strictEqual(dlg.closed, true);

  const old = fakeDoc(false);
  const s2 = fakeSection();
  g.render(s2, six(), old);
  assert.strictEqual(s2._thumbs.children[0].children[0].handlers.click({ preventDefault() { throw new Error('must not intercept'); } }), undefined);
});

test('swapPortrait replaces the initials only once the face has loaded', () => {
  const parent = new El('div');
  const initials = new El('div');
  parent.appendChild(initials);
  const doc = Object.assign(fakeDoc(), { querySelector: (sel) => (sel === '.hero .avatar' ? initials : null) });
  g.swapPortrait(doc, BASE + 'face.jpg', 'Jane Doe');
  const img = doc.created.find((e) => e.tag === 'img');
  assert.strictEqual(img.attrs.src, BASE + 'face.jpg');
  assert.strictEqual(img.attrs.alt, 'Jane Doe');
  assert.match(img.attrs.class, /avatar avatar-lg/);
  assert.strictEqual(parent.children[0], initials);
  img.handlers.load();
  assert.strictEqual(parent.children[0], img);
});

test('swapPortrait leaves an existing portrait, a missing face and a missing avatar alone', () => {
  const photoAvatar = new El('img'); photoAvatar.parentNode = new El('div');
  let doc = Object.assign(fakeDoc(), { querySelector: () => photoAvatar });
  g.swapPortrait(doc, BASE + 'face.jpg', 'x');
  assert.strictEqual(doc.created.length, 0);
  const div = new El('div'); div.parentNode = new El('div');
  doc = Object.assign(fakeDoc(), { querySelector: () => div });
  g.swapPortrait(doc, null, 'x');
  assert.strictEqual(doc.created.length, 0);
  doc = Object.assign(fakeDoc(), { querySelector: () => null });
  g.swapPortrait(doc, BASE + 'face.jpg', 'x');
  assert.strictEqual(doc.created.length, 0);
});

test('init swaps the portrait only when the page asked for it', async () => {
  const run = async (flag) => {
    const section = fakeSection({ galleryType: 'fussel', galleryUrl: BASE, galleryKey: 'jane-doe', galleryExplicit: '0', galleryName: 'Jane Doe', galleryPortrait: flag });
    const parent = new El('div'); const initials = new El('div'); parent.appendChild(initials);
    const doc = Object.assign(fakeDoc(), { getElementById: () => section, querySelector: () => initials });
    const withFace = manifest(); withFace.people[0].thumb = 'static/_gallery/face.jpg';
    await g.init(doc, Object.assign({ fetch: () => Promise.resolve(okResponse(withFace)) }, noTimers));
    return doc.created.filter((e) => e.tag === 'img' && /avatar/.test(e.attrs.class || '')).length;
  };
  assert.strictEqual(await run('1'), 1);
  assert.strictEqual(await run('0'), 0);
});

test('a swipe steps the lightbox, and a cancelled touch does not', () => {
  const doc = fakeDoc(true);
  const section = fakeSection();
  g.render(section, six(), doc);
  section._thumbs.children[0].children[0].handlers.click({ preventDefault() {} });
  const dlg = doc.created.find((e) => e.tag === 'dialog');
  const counter = dlg.find((e) => e.attrs.class === 'gallery-count');
  dlg.handlers.pointerdown({ clientX: 300 });
  dlg.handlers.pointerup({ clientX: 100 });
  assert.strictEqual(counter.textContent, '2 / 6');
  dlg.handlers.pointerdown({ clientX: 100 });
  dlg.handlers.pointerup({ clientX: 220 });
  assert.strictEqual(counter.textContent, '1 / 6');
  dlg.handlers.pointerdown({ clientX: 300 });
  dlg.handlers.pointercancel({});
  dlg.handlers.pointerup({ clientX: 100 });
  assert.strictEqual(counter.textContent, '1 / 6');
  dlg.handlers.pointerdown({ clientX: 300 });
  dlg.handlers.pointerup({ clientX: 290 });
  assert.strictEqual(counter.textContent, '1 / 6');
});

test('a featured photo whose large size will not load falls back to its small size, once', () => {
  const section = fakeSection();
  g.render(section, six(), fakeDoc());
  const img = (i) => section._thumbs.children[i].children[0].children[0];
  assert.strictEqual(img(0).attrs.src, BASE + 'v1.jpg');
  img(0).handlers.error();
  assert.strictEqual(img(0).attrs.src, BASE + 't1.jpg');
  img(0).handlers.error();
  assert.strictEqual(img(0).attrs.src, BASE + 't1.jpg');
  img(1).handlers.error();
  assert.strictEqual(img(1).attrs.src, BASE + 't2.jpg');
});
