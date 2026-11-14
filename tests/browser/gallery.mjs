// Drives a built famsite with a gallery configured in headless Chrome and checks the photos block against a stub gallery.
// Usage: node gallery.mjs <chrome-binary> <site-base-url> <gallery-base-url> <screenshot-dir>
import { spawn } from 'node:child_process';
import { mkdirSync, writeFileSync } from 'node:fs';
import http from 'node:http';

const [chrome, base, gallery, shots] = process.argv.slice(2);
mkdirSync(shots, { recursive: true });
const port = 9300 + Math.floor(Math.random() * 400);
const proc = spawn(chrome, ['--no-sandbox', '--disable-gpu', '--hide-scrollbars', '--window-size=1400,820',
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

  // ---- a gallery that fails in every way leaves the page alone
  for (const [mode, wait] of [['notfound', 1000], ['badjson', 1000], ['badversion', 1000], ['nocors', 1000], ['hang', 6500]]) {
    await open(mode, '/p/jane-doe/', wait);
    s = await state();
    check(`${mode}: the block stays hidden and takes no space`, s.exists && s.hidden === true && s.height === 0 && s.thumbs === 0, JSON.stringify(s));
    check(`${mode}: no uncaught errors`, errors.length === 0, errors.join('\n'));
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
  await send('Emulation.setDeviceMetricsOverride', { width: 1400, height: 820, deviceScaleFactor: 1, mobile: false });

  ws.close();
}

try { await main(); } catch (e) { console.log('FAIL  harness error -> ' + e.stack); failures++; }
proc.kill();
process.exit(failures ? 1 : 0);
