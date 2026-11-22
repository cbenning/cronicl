// Drives a built cronicl map page in headless Chrome against a local tile server.
// Usage: node map.mjs <chrome-binary> <site-base-url> <tile-base-url> <screenshot-dir>
import { spawn } from 'node:child_process';
import { mkdirSync, writeFileSync } from 'node:fs';
import http from 'node:http';

const [chrome, base, tiles, shots] = process.argv.slice(2);
mkdirSync(shots, { recursive: true });
const port = 9700 + Math.floor(Math.random() * 200);
// A full Chrome needs --headless; chrome-headless-shell is always headless.
const headless = /headless[-_]shell/.test(chrome) ? [] : ['--headless=new'];
const proc = spawn(chrome, [...headless, '--no-sandbox', '--disable-gpu', '--hide-scrollbars', '--window-size=1200,800',
  `--remote-debugging-port=${port}`, 'about:blank'], { stdio: 'ignore' });
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const getJSON = (url) => new Promise((resolve, reject) => {
  http.get(url, (res) => { let d = ''; res.on('data', (c) => (d += c)); res.on('end', () => resolve(JSON.parse(d))); }).on('error', reject);
});
let failures = 0;
const check = (name, ok, detail = '') => { console.log(`${ok ? 'PASS' : 'FAIL'}  ${name}${ok ? '' : '  -> ' + detail}`); if (!ok) failures++; };

async function main() {
  let targets;
  // a cold Chrome on a busy runner can take several seconds
  for (let i = 0; i < 200; i++) { try { targets = await getJSON(`http://127.0.0.1:${port}/json`); break; } catch { await sleep(100); } }
  if (!targets) throw new Error('Chrome did not start: ' + chrome);
  const page = targets.find((t) => t.type === 'page');
  const ws = new WebSocket(page.webSocketDebuggerUrl);
  let id = 0;
  const pending = new Map(), errors = [], requests = [];
  ws.onmessage = (e) => {
    const m = JSON.parse(e.data);
    if (m.id && pending.has(m.id)) { pending.get(m.id)(m); pending.delete(m.id); }
    else if (m.method === 'Runtime.exceptionThrown') errors.push(JSON.stringify(m.params.exceptionDetails.exception?.description || m.params.exceptionDetails.text));
    else if (m.method === 'Runtime.consoleAPICalled' && m.params.type === 'error') errors.push(m.params.args.map((a) => a.value).join(' '));
    else if (m.method === 'Network.requestWillBeSent') requests.push(m.params.request.url);
  };
  await new Promise((r) => (ws.onopen = r));
  const send = (method, params = {}) => new Promise((res) => { const i = ++id; pending.set(i, res); ws.send(JSON.stringify({ id: i, method, params })); });
  await send('Runtime.enable'); await send('Page.enable'); await send('Network.enable');
  const ev = async (expr) => (await send('Runtime.evaluate', { expression: expr, returnByValue: true, awaitPromise: true })).result.result.value;
  // Poll for what a step should have produced, instead of sleeping a fixed time and hoping it was enough.
  const until = async (expr, what) => {
    for (let i = 0; i < 300; i++) { if (await ev(expr)) return; await sleep(50); }
    throw new Error('timed out waiting for ' + what);
  };
  const tilesLoaded = `(() => { const t = [...document.querySelectorAll('.map-tile')]; return t.length > 0 && t.every((i) => i.complete); })()`;
  const settle = () => ev('new Promise((r) => requestAnimationFrame(() => requestAnimationFrame(() => r(true))))');
  const open = async (path, withMap = true) => {
    await send('Page.navigate', { url: 'about:blank' }); await until(`location.href === 'about:blank'`, 'about:blank');
    errors.length = 0; requests.length = 0;
    await send('Page.navigate', { url: base + path });
    await until(`location.href.startsWith(${JSON.stringify(base)}) && document.readyState === 'complete' && ${withMap ? tilesLoaded : 'true'}`, 'the page at ' + path);
  };
  const tileHost = new URL(tiles).host, siteHost = new URL(base).host;
  const state = () => ev(`(() => { const imgs = [...document.querySelectorAll('.map-tile')]; const ms = [...document.querySelectorAll('.map-marker')];
    const list = document.getElementById('map-list'); const st = document.getElementById('map-status');
    return { tiles: imgs.length, loaded: imgs.filter((i) => i.complete && i.naturalWidth > 0).length, srcs: imgs.map((i) => i.src),
      markers: ms.length, labels: ms.map((m) => m.getAttribute('aria-label')), pos: ms.map((m) => [m.offsetLeft, m.offsetTop]),
      listOpen: !!list && !list.hidden, listText: list ? list.textContent : '', links: list ? [...list.querySelectorAll('a')].map((a) => a.getAttribute('href')) : [],
      status: st ? (st.hidden ? '' : st.textContent) : null, credit: (document.querySelector('.map-attribution') || {}).textContent }; })()`);
  const zoomOf = (s) => Math.max(...s.srcs.map((u) => Number(new URL(u).pathname.split('/')[1])));

  await open('/map/');
  let s = await state();
  check('markers appear and the status is cleared', s.markers === 2 && s.status === '', JSON.stringify([s.markers, s.status]));
  check('tiles load from the tile server', s.tiles > 0 && s.loaded === s.tiles && s.srcs.every((u) => new URL(u).host === tileHost), JSON.stringify([s.tiles, s.loaded]));
  check('the attribution is shown', /Test tiles/.test(s.credit || ''), s.credit);
  const outside = requests.filter((u) => { const h = new URL(u).host; return h !== tileHost && h !== siteHost && !u.startsWith('data:'); });
  check('no request goes anywhere but the site and the tile server', outside.length === 0, outside.join(' '));
  check('the page has no script errors', errors.length === 0, errors.join(' | '));
  await ev(`document.getElementById('map-status') && 0`);
  const z0 = zoomOf(s);
  await ev(`document.querySelector('.map-view').focus()`);
  const key = (k) => send('Input.dispatchKeyEvent', { type: 'keyDown', key: k, text: k }).then(() => send('Input.dispatchKeyEvent', { type: 'keyUp', key: k }));
  // A zoom redraws the tiles; wait for the zoom level to arrive (a wrong level still falls through to the check).
  const zoomed = async (want) => { for (let i = 0; i < 100 && zoomOf(await state()) !== want; i++) await sleep(50); await until(tilesLoaded, 'tiles'); return state(); };
  await key('+');
  s = await zoomed(z0 + 1);
  check('+ zooms in', zoomOf(s) === z0 + 1, `${z0} -> ${zoomOf(s)}`);
  await key('-');
  s = await zoomed(z0);
  check('- zooms out', zoomOf(s) === z0, String(zoomOf(s)));
  await ev(`document.querySelectorAll('.map-controls button')[0].click()`);
  s = await zoomed(z0 + 1);
  check('the + button zooms in', zoomOf(s) === z0 + 1, String(zoomOf(s)));
  await ev(`document.querySelectorAll('.map-controls button')[2].click()`);
  s = await zoomed(z0);
  check('Fit goes back to showing every place', zoomOf(s) === z0, String(zoomOf(s)));

  const before = s.pos[0];
  const view = await ev(`(() => { const r = document.querySelector('.map-view').getBoundingClientRect(); return { x: Math.round(r.left + 100), y: Math.round(r.top + 100) }; })()`);
  await send('Input.dispatchMouseEvent', { type: 'mousePressed', x: view.x, y: view.y, button: 'left', clickCount: 1 });
  for (const d of [10, 30, 60]) { await send('Input.dispatchMouseEvent', { type: 'mouseMoved', x: view.x + d, y: view.y + d / 2, button: 'left' }); await sleep(30); }
  await send('Input.dispatchMouseEvent', { type: 'mouseReleased', x: view.x + 60, y: view.y + 30, button: 'left', clickCount: 1 });
  await settle();
  s = await state();
  check('dragging pans the map', Math.abs(s.pos[0][0] - before[0] - 60) <= 2 && Math.abs(s.pos[0][1] - before[1] - 30) <= 2, JSON.stringify([before, s.pos[0]]));

  await ev(`[...document.querySelectorAll('.map-marker')].find((m) => /London/.test(m.getAttribute('aria-label'))).click()`); await settle();
  s = await state();
  check('clicking a marker lists its people with links', s.listOpen && /London/.test(s.listText) && s.links.some((h) => h.endsWith('p/ada/')) && s.links.some((h) => h.endsWith('p/bob/')), JSON.stringify([s.listText, s.links]));
  check('the address now names the place', (await ev('location.hash')).length > 1);
  await send('Page.captureScreenshot', { format: 'png' }).then((r) => writeFileSync(`${shots}/map.png`, Buffer.from(r.result.data, 'base64')));

  await open('/map/#ockham-surrey');
  s = await state();
  check('a place address opens that place', s.listOpen && /Ockham/.test(s.listText), s.listText);
  check('and zooms in on it', zoomOf(s) >= 9, String(zoomOf(s)));

  await open('/places/index.html', false);
  const link = await ev(`(() => { const a = document.querySelector('a.on-map'); return a ? a.getAttribute('href') : null; })()`);
  check('the places page links to the map', !!link && link.startsWith('../map/#'), String(link));
  ws.close();
}

try { await main(); } catch (e) { console.log('FAIL  harness error -> ' + e.stack); failures++; }
proc.kill();
process.exit(failures ? 1 : 0);
