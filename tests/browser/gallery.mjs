// Drives a built cronicl with a gallery configured in headless Chrome and checks the photos block against a stub gallery.
// Usage: node gallery.mjs <chrome-binary> <site-base-url> <gallery-base-url> <screenshot-dir>
import { spawn } from 'node:child_process';
import { mkdirSync, writeFileSync } from 'node:fs';
import http from 'node:http';

const [chrome, base, gallery, shots] = process.argv.slice(2);
mkdirSync(shots, { recursive: true });
const port = 9300 + Math.floor(Math.random() * 400);
// A full Chrome needs --headless; chrome-headless-shell is always headless.
const headless = /headless[-_]shell/.test(chrome) ? [] : ['--headless=new'];
const proc = spawn(chrome, [...headless, '--no-sandbox', '--disable-gpu', '--hide-scrollbars', '--window-size=1400,820',
  `--remote-debugging-port=${port}`, 'about:blank'], { stdio: 'ignore' });
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const getJSON = (url) => new Promise((resolve, reject) => {
  http.get(url, (res) => { let d = ''; res.on('data', (c) => (d += c)); res.on('end', () => resolve(JSON.parse(d))); }).on('error', reject);
});

let failures = 0;
const check = (name, ok, detail = '') => {
  console.log(`${ok ? 'PASS' : 'FAIL'}  ${name}${ok ? '' : '  -> ' + detail}`);
  if (!ok) failures++;
};

async function main() {
  let targets;
  for (let i = 0; i < 50; i++) {
    try { targets = await getJSON(`http://127.0.0.1:${port}/json`); break; } catch { await sleep(100); }
  }
  if (!targets) throw new Error('Chrome did not start: ' + chrome);
  const page = targets.find((t) => t.type === 'page');
  const ws = new WebSocket(page.webSocketDebuggerUrl);
  let id = 0;
  const pending = new Map();
  const errors = [];
  ws.onmessage = (e) => {
    const m = JSON.parse(e.data);
    if (m.id && pending.has(m.id)) { pending.get(m.id)(m); pending.delete(m.id); }
    else if (m.method === 'Runtime.exceptionThrown') errors.push(JSON.stringify(m.params.exceptionDetails.exception?.description || m.params.exceptionDetails.text));
    else if (m.method === 'Runtime.consoleAPICalled' && m.params.type === 'error') errors.push(m.params.args.map((a) => a.value).join(' '));
  };
  await new Promise((r) => (ws.onopen = r));
  const send = (method, params = {}) => new Promise((res) => { const i = ++id; pending.set(i, res); ws.send(JSON.stringify({ id: i, method, params })); });
  await send('Runtime.enable');
  await send("Page.enable");
  await send("Network.enable");
  const requests = [];
  ws.addEventListener("message", (e) => { const m = JSON.parse(e.data); if (m.method === "Network.requestWillBeSent") requests.push(m.params.request.url); });
  const ev = async (expr) => (await send('Runtime.evaluate', { expression: expr, returnByValue: true })).result.result.value;
  const shot = async (name) => {
    const r = await send('Page.captureScreenshot', { format: 'png' });
    writeFileSync(`${shots}/${name}.png`, Buffer.from(r.result.data, 'base64'));
  };
  const setMode = (mode) => new Promise((resolve, reject) => { http.get(`${gallery}/__mode/${mode}`, (res) => { res.resume(); res.on('end', resolve); }).on('error', reject); });
  const open = async (mode, path, wait = 1000) => {
    await setMode(mode);
    await send('Page.navigate', { url: 'about:blank' }); await sleep(100);
    errors.length = 0; requests.length = 0;
    await send('Page.navigate', { url: base + path }); await sleep(wait);
  };
  const state = () => ev(`(() => { const s = document.getElementById('gallery'); if (!s) return { exists: false }; const r = s.getBoundingClientRect(); const imgs = [...s.querySelectorAll('img')]; const links = [...s.querySelectorAll('a')]; return { exists: true, hidden: s.hidden, height: r.height, heading: s.querySelector('h2').textContent, thumbs: s.querySelectorAll('.gallery-thumbs li').length, loaded: imgs.every((i) => i.complete && i.naturalWidth > 0), blank: links.every((a) => a.target === '_blank' && /noopener/.test(a.rel)), hrefs: links.map((a) => a.href), more: s.querySelector('.gallery-more a').textContent, srcs: imgs.map((i) => i.src) }; })()`);
  const galleryRequests = () => requests.filter((u) => u.includes('people.json'));
  const galleryHost = new URL(gallery).host;
  const index = await new Promise((resolve, reject) => http.get(base + '/index.json', (res) => { let d = ''; res.on('data', (c) => (d += c)); res.on('end', () => resolve(JSON.parse(d))); }).on('error', reject));
  const livingId = index.find((p) => p.name === 'Living').id;

  // ---- a gallery that answers
  await open('ok', '/p/jane-doe/');
  let s = await state();
  check('the photos block appears for a person in the gallery', s.exists && !s.hidden && s.height > 0, JSON.stringify(s));
  check('it is headed by the configured label', s.heading === 'Family photos', s.heading);
  check('it shows six thumbnails of the eight offered', s.thumbs === 6, String(s.thumbs));
  check('every thumbnail really loaded', s.loaded === true);
  check('links open in a new tab with noopener', s.blank === true);
  check('thumbnail links point into the gallery', s.hrefs.slice(0, 6).every((h) => h.startsWith(gallery + '/photos/#/collections/people/jane-doe/')), s.hrefs.join(' '));
  check('"See all" says how many photos there are', s.more === 'See all 12 photos in the gallery' && s.hrefs[s.hrefs.length - 1] === gallery + '/photos/#/collections/people/jane-doe', s.more + ' ' + s.hrefs[s.hrefs.length - 1]);
  check('no uncaught errors', errors.length === 0, errors.join('\n'));
  await shot('gallery-light');

  // ---- the mosaic, the lightbox and the portrait, on a gallery that answers
  const mosaic = await ev(`(() => { const li = [...document.querySelectorAll('#gallery .gallery-thumbs li')]; const rs = li.map((e) => e.getBoundingClientRect()); const box = document.getElementById('gallery').getBoundingClientRect(); return { featured: li[0].classList.contains('featured'), otherFeatured: li.slice(1).some((e) => e.classList.contains('featured')), w0: rs[0].width, h0: rs[0].height, w1: rs[1].width, h1: rs[1].height, gap: rs[2].top - rs[1].bottom, inside: rs.every((r) => r.right <= box.right + 1 && r.left >= box.left - 1), srcs: li.map((e) => e.querySelector('img').src) }; })()`);
  check('the first photo is featured and about twice as wide as a tile', mosaic.featured && !mosaic.otherFeatured && mosaic.w0 >= mosaic.w1 * 1.8, JSON.stringify(mosaic));
  check('no tile leaves the block', mosaic.inside === true);
  check('even with portrait photos the featured tile is square and the tiles sit flush against it', Math.abs(mosaic.h0 - mosaic.w0) < 3 && Math.abs(mosaic.h0 - (2 * mosaic.h1 + mosaic.gap)) < 2 && mosaic.gap < 20, JSON.stringify(mosaic));
  check('the featured photo uses the large size, the tiles the small one', mosaic.srcs[0].endsWith('/big1.jpg') && mosaic.srcs.slice(1).every((u, i) => u.endsWith('/p' + (i + 2) + '.jpg')), mosaic.srcs.join(' '));
  const lightbox = () => ev(`(() => { const d = document.querySelector('dialog.gallery-lightbox'); if (!d) return { exists: false, n: 0 }; const r = d.getBoundingClientRect(); const open = d.querySelector('.gallery-open'); return { exists: true, n: document.querySelectorAll('dialog.gallery-lightbox').length, open: d.open, h: r.height, w: r.width, imgW: d.querySelector('.gallery-big').getBoundingClientRect().width, src: d.querySelector('.gallery-big').src, counter: d.querySelector('.gallery-count').textContent, href: open.href, rel: open.rel }; })()`);
  const key = async (k, code, vk) => { for (const type of ['keyDown', 'keyUp']) await send('Input.dispatchKeyEvent', { type, key: k, code, windowsVirtualKeyCode: vk }); await sleep(250); };
  await ev(`document.querySelector('#gallery .gallery-thumbs li a').click()`); await sleep(400);
  let lb = await lightbox();
  check('clicking a photo opens the lightbox in the page, on the large photo', lb.exists && lb.open && lb.h > 0 && lb.src.endsWith('/big1.jpg') && lb.counter === '1 / 6', JSON.stringify(lb));
  check('the lightbox links to that photo in the gallery, in a new tab', lb.href.startsWith(gallery + '/photos/#/collections/people/jane-doe/p1') && /noopener/.test(lb.rel), JSON.stringify(lb));
  await shot('gallery-lightbox');
  await key('ArrowRight', 'ArrowRight', 39);
  lb = await lightbox();
  check('the right arrow key shows the next photo', lb.counter === '2 / 6' && lb.src.endsWith('/big2.jpg'), JSON.stringify(lb));
  await key('ArrowLeft', 'ArrowLeft', 37); await key('ArrowLeft', 'ArrowLeft', 37);
  lb = await lightbox();
  check('the left arrow wraps from the first photo to the last', lb.counter === '6 / 6' && lb.src.endsWith('/big6.jpg'), JSON.stringify(lb));
  await key('Escape', 'Escape', 27);
  lb = await lightbox();
  check('Escape closes the lightbox', lb.exists && lb.open === false, JSON.stringify(lb));
  check('focus returns to the photo that was opened', (await ev(`document.activeElement === document.querySelector('#gallery .gallery-thumbs li a')`)) === true);
  await ev(`document.querySelectorAll('#gallery .gallery-thumbs li a')[2].click()`); await sleep(400);
  lb = await lightbox();
  check('opening again reuses one lightbox, on the clicked photo', lb.n === 1 && lb.open && lb.counter === '3 / 6' && lb.src.endsWith('/big3.jpg'), JSON.stringify(lb));
  await ev(`document.querySelector('dialog.gallery-lightbox .gallery-next').click()`); await sleep(250);
  lb = await lightbox();
  check('the next button shows the next photo', lb.counter === '4 / 6' && lb.src.endsWith('/big4.jpg'), JSON.stringify(lb));
  const around = await ev(`(() => { const r = document.querySelector('dialog.gallery-lightbox').getBoundingClientRect(); return { left: r.left, right: r.right }; })()`);
  check('the lightbox hugs the photo, so there is no dead zone beside it', around.left > 300 && around.right < 1100, JSON.stringify(around));
  for (const type of ['mousePressed', 'mouseReleased']) await send('Input.dispatchMouseEvent', { type, x: 150, y: 400, button: 'left', clickCount: 1 });
  await sleep(250);
  lb = await lightbox();
  check('clicking the dark area beside the photo closes the lightbox', lb.open === false, JSON.stringify(lb));
  const avatar = () => ev(`(() => { const a = document.querySelector('.hero .avatar'); const r = a.getBoundingClientRect(); return { tag: a.tagName, src: a.src || '', w: Math.round(r.width), round: getComputedStyle(a).borderRadius }; })()`);
  let av = await avatar();
  check('with no portrait of its own the page shows the gallery face', av.tag === 'IMG' && av.src.endsWith('/face-jane.jpg') && av.w === 112 && parseInt(av.round, 10) >= 50, JSON.stringify(av));
  await open('ok', '/p/john-doe/');
  av = await avatar();
  s = await state();
  check('a portrait the owner chose is never replaced', av.tag === 'IMG' && av.src.includes('/media/john') && s.exists && !s.hidden && s.thumbs === 3, JSON.stringify([av, s.thumbs]));
  await open('ok', '/p/jane-doe/');

  // ---- the top bar carries the same link on every page, in the same place
  const bar = [];
  for (const path of ['/index.html', '/people/index.html', '/p/jane-doe/']) {
    await open('ok', path, 700);
    bar.push(await ev(`(() => { const a = document.querySelector('.site-gallery'); const n = document.querySelector('.site-bar nav').getBoundingClientRect(); return JSON.stringify([a && a.href, a && a.target, Math.round(n.left), Math.round(n.top), Math.round(n.width), Math.round(n.height)]); })()`));
    if (path !== '/p/jane-doe/') check('no request to the gallery from ' + path, galleryRequests().length === 0, requests.join(' '));
  }
  check('the header link goes to the gallery and the bar is identical on every page', new Set(bar).size === 1 && JSON.parse(bar[0])[0] === gallery + '/photos/' && JSON.parse(bar[0])[1] === '_blank', bar.join('\n'));

  // ---- people the gallery does not have, or that are private
  await open('ok', '/p/lone-person/');
  s = await state();
  check('a person missing from the gallery shows no block', s.exists && s.hidden === true && s.height === 0, JSON.stringify(s));
  await open('ok', '/p/' + livingId + '/');
  s = await state();
  check('a redacted living person has no block and causes no gallery request', s.exists === false && galleryRequests().length === 0, JSON.stringify(s) + requests.join(' '));

  // ---- a hostile gallery
  await open('hostile', '/p/jane-doe/');
  s = await state();
  check('hostile addresses are dropped, the good photo stays', s.exists && !s.hidden && s.thumbs === 1, JSON.stringify(s));
  check('nothing was requested from another host', requests.every((u) => !u.includes('evil.invalid')), requests.join(' '));
  check('hostile: no uncaught errors', errors.length === 0, errors.join('\n'));
  check('hostile: a bad large size falls back to the small one, a bad face is ignored', s.srcs.length === 1 && s.srcs[0].endsWith('/p1.jpg') && (await ev(`document.querySelector('.hero .avatar').tagName`)) === 'DIV', JSON.stringify(s.srcs));

  // ---- a large size that is listed but will not load
  await open('badsrc', '/p/jane-doe/', 1500);
  s = await state();
  const featuredImg = await ev(`(() => { const i = document.querySelector('#gallery .gallery-thumbs li.featured img'); return { w: i.naturalWidth, src: i.src }; })()`);
  check('badsrc: the featured photo falls back to its small size', s.exists && !s.hidden && featuredImg.w > 0 && featuredImg.src.endsWith('/p1.jpg'), JSON.stringify(featuredImg));

  // ---- a gallery from an older fussel (no large size, no face)
  await open('nosrc', '/p/jane-doe/');
  s = await state();
  check('nosrc: the featured photo falls back to the small size', s.exists && !s.hidden && s.srcs[0].endsWith('/p1.jpg'), JSON.stringify(s.srcs));
  await ev(`document.querySelector('#gallery .gallery-thumbs li a').click()`); await sleep(400);
  lb = await lightbox();
  check('nosrc: the lightbox still works', lb.open === true && lb.src.endsWith('/p1.jpg'), JSON.stringify(lb));
  await key('Escape', 'Escape', 27);
  check('nosrc: the initials stay', (await ev(`document.querySelector('.hero .avatar').tagName`)) === 'DIV');

  // ---- a gallery that fails in every way leaves the page alone
  for (const [mode, wait] of [['notfound', 1000], ['badjson', 1000], ['badversion', 1000], ['nocors', 1000], ['hang', 6500]]) {
    await open(mode, '/p/jane-doe/', wait);
    s = await state();
    check(`${mode}: the block stays hidden and takes no space`, s.exists && s.hidden === true && s.height === 0 && s.thumbs === 0, JSON.stringify(s));
    check(`${mode}: no uncaught errors`, errors.length === 0, errors.join('\n'));
    check(`${mode}: the initials stay`, (await ev(`document.querySelector('.hero .avatar').tagName`)) === 'DIV');
  }

  // ---- dark mode and phone
  await send('Emulation.setEmulatedMedia', { features: [{ name: 'prefers-color-scheme', value: 'dark' }] });
  await open('ok', '/p/jane-doe/');
  const dark = await ev(`getComputedStyle(document.querySelector('.gallery-thumbs a')).backgroundColor`);
  check('dark mode: thumbnails sit on a dark surface', dark !== 'rgb(255, 255, 255)' && dark !== 'rgba(0, 0, 0, 0)', dark);
  await shot('gallery-dark');
  await send('Emulation.setEmulatedMedia', { features: [{ name: 'prefers-color-scheme', value: 'light' }] });
  await send('Emulation.setDeviceMetricsOverride', { width: 390, height: 844, deviceScaleFactor: 1, mobile: true });
  await open('ok', '/p/jane-doe/');
  check('phone: nothing is wider than the screen', (await ev('document.documentElement.scrollWidth')) <= 390, await ev('document.documentElement.scrollWidth'));
  await shot('gallery-phone');
  const phoneMosaic = await ev(`(() => { const f = document.querySelector('#gallery .gallery-thumbs li.featured').getBoundingClientRect(); const b = document.getElementById('gallery').getBoundingClientRect(); return { f: f.width, b: b.width }; })()`);
  check('phone: the featured photo spans the block', phoneMosaic.f >= phoneMosaic.b * 0.95, JSON.stringify(phoneMosaic));
  await ev(`document.querySelector('#gallery .gallery-thumbs li a').click()`); await sleep(400);
  lb = await lightbox();
  check('phone: the lightbox fits the screen', lb.open && lb.w <= 390 && lb.imgW <= 390 && (await ev('document.documentElement.scrollWidth')) <= 390, JSON.stringify(lb));
  await shot('gallery-phone-lightbox');
  await send('Emulation.setTouchEmulationEnabled', { enabled: true, maxTouchPoints: 1 });
  const centre = await ev(`(() => { const r = document.querySelector('dialog.gallery-lightbox .gallery-big').getBoundingClientRect(); return { x: Math.round(r.left + r.width / 2), y: Math.round(r.top + r.height / 2) }; })()`);
  const touch = (type, x, y) => send('Input.dispatchTouchEvent', { type, touchPoints: type === 'touchEnd' ? [] : [{ x, y }] });
  await touch('touchStart', centre.x + 120, centre.y); await sleep(50);
  for (const dx of [80, 40, 0, -40, -80, -120]) { await touch('touchMove', centre.x + dx + 0, centre.y); await sleep(20); }
  await touch('touchEnd', 0, 0); await sleep(300);
  lb = await lightbox();
  check('phone: swiping left shows the next photo', lb.counter === '2 / 6', JSON.stringify(lb));
  await send('Emulation.setTouchEmulationEnabled', { enabled: false });
  await key('Escape', 'Escape', 27);
  await send('Emulation.setDeviceMetricsOverride', { width: 1400, height: 820, deviceScaleFactor: 1, mobile: false });

  ws.close();
}

try { await main(); } catch (e) { console.log('FAIL  harness error -> ' + e.stack); failures++; }
proc.kill();
process.exit(failures ? 1 : 0);
