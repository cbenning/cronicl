// Drives a built famsite in headless Chrome over the DevTools protocol and checks real behaviour.
// Usage: node smoke.mjs <chrome-binary> <base-url> <screenshot-dir>
import { spawn } from 'node:child_process';
import { mkdirSync, writeFileSync } from 'node:fs';
import http from 'node:http';

const [chrome, base, shots] = process.argv.slice(2);
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
  await send('Page.enable');
  const ev = async (expr) => (await send('Runtime.evaluate', { expression: expr, returnByValue: true })).result.result.value;
  const shot = async (name) => {
    const r = await send('Page.captureScreenshot', { format: 'png' });
    writeFileSync(`${shots}/${name}.png`, Buffer.from(r.result.data, 'base64'));
  };
  const click = (sel) => ev(`(() => { const e = document.querySelector(${JSON.stringify(sel)}); if (!e) return false; e.dispatchEvent(new MouseEvent('click', {bubbles: true})); return true; })()`);
  const goto = async (hash) => { await ev(`location.hash = ${JSON.stringify(hash)}`); await sleep(500); };

  await send('Page.navigate', { url: base + '/#/tree' });
  await sleep(1500);

  // ---- tree
  const nodeCount = await ev(`document.querySelectorAll('.node').length`);
  check('tree renders nodes', nodeCount >= 5, nodeCount);
  const overflow = await ev(`(() => { const bad = []; document.querySelectorAll('.node').forEach((g) => { const r = g.querySelector('rect').getBBox(); g.querySelectorAll('text').forEach((t) => { if (!t.textContent) return; const b = t.getBBox(); if (b.x < r.x + 4 || b.x + b.width > r.x + r.width - 4) bad.push(g.dataset.id + ':' + t.textContent + ':' + Math.round(b.width) + '/' + r.width); }); }); return bad; })()`);
  check('no node text comes within 4px of its box edge', overflow.length === 0, overflow.join('; '));
  const sameRow = await ev(`(() => { const y = (id) => document.querySelector('.node[data-id="' + id + '"] rect')?.getAttribute('y'); return [y('smith-bob'), y('ellsworth-maude')]; })()`);
  check('siblings share a row', sameRow[0] && sameRow[0] === sameRow[1], JSON.stringify(sameRow));
  check('ended partnership draws a dashed spouse line', (await ev(`document.querySelectorAll('.edge.spouse.ended').length`)) >= 1);
  check('ended partnership has a hollow dot', (await ev(`document.querySelectorAll('.union.ended').length`)) >= 1);

  // ---- panel open / close / deselect
  await click('.node[data-id="smith-bob"]');
  await sleep(600);
  check('click opens the panel', (await ev(`!document.getElementById('panel').hidden`)) === true);
  check('panel shows the person', (await ev(`document.querySelector('#panel h2')?.textContent`)) === 'Bob Smith');
  check('node is highlighted', (await ev(`document.querySelectorAll('.node.selected').length`)) === 1);
  check('url records the selection', (await ev(`location.hash`)) === '#/tree/smith-bob');
  check('selected person lights up connectors', (await ev(`document.querySelectorAll('.edge.hi').length`)) >= 1);
  check('relatives are marked related', (await ev(`document.querySelectorAll('.node.related').length`)) >= 2);
  check('unrelated people and lines are faded', (await ev(`document.querySelectorAll('.node.dim').length`)) >= 1);
  await shot('tree-panel-open');
  await click('#panel .close');
  await sleep(300);
  check('close button hides the panel', (await ev(`document.getElementById('panel').hidden`)) === true);
  check('close deselects the node', (await ev(`document.querySelectorAll('.node.selected').length`)) === 0);
  check('close clears the url selection', (await ev(`location.hash`)) === '#/tree');
  check('close removes all highlighting', (await ev(`document.querySelectorAll('.edge.hi, .edge.dim, .node.dim, .node.related').length`)) === 0);
  await click('.node[data-id="smith-john"]');
  await sleep(500);
  await ev(`document.dispatchEvent(new KeyboardEvent('keydown', {key: 'Escape', bubbles: true}))`);
  await sleep(200);
  check('Escape closes the panel', (await ev(`document.getElementById('panel').hidden`)) === true);
  await click('.node[data-id="smith-john"]');
  await sleep(500);
  await click('#tree');
  await sleep(200);
  check('clicking empty canvas closes the panel', (await ev(`document.getElementById('panel').hidden`)) === true);

  await goto('#/tree/smith-john');
  await sleep(300);
  check('panel shows when the marriage ended', /divorced 1945/.test(await ev(`document.getElementById('panel').textContent`)));
  await click('#panel .close');
  await sleep(200);

  // ---- focused tree
  await goto('#/focus/smith-amy');
  await sleep(500);
  const focusIds = await ev(`[...document.querySelectorAll('.node')].map((n) => n.dataset.id).sort()`);
  check('focused tree shows only the line above and below', JSON.stringify(focusIds) === JSON.stringify(['brown-mary', 'jones-jane', 'smith-amy', 'smith-bob', 'smith-john']), JSON.stringify(focusIds));
  check('focused tree leaves siblings out', !focusIds.includes('smith-tom'));
  check('focus bar names the person', /Focused on Amy Smith/.test(await ev(`document.getElementById('focus-bar').textContent`)));
  check('focus person is marked', (await ev(`document.querySelectorAll('.node.focus').length`)) === 1);
  check('tree tab stays current in focus', (await ev(`document.querySelector('#tabs a[data-view="tree"]').getAttribute('aria-current')`)) === 'page');
  await shot('tree-focus');
  await click('.node[data-id="smith-bob"]');
  await sleep(500);
  check('selecting inside the focus keeps the focus url', (await ev(`location.hash`)) === '#/focus/smith-amy');
  check('selecting inside the focus highlights', (await ev(`document.querySelectorAll('.edge.hi').length`)) >= 1);
  await click('#panel .close');
  await sleep(200);
  check('closing the panel keeps the focus', (await ev(`location.hash`)) === '#/focus/smith-amy' && (await ev(`!document.getElementById('focus-bar').hidden`)));
  await ev(`(() => { const s = document.getElementById('search'); s.value = 'tom'; s.dispatchEvent(new Event('input')); })()`);
  await sleep(200);
  await ev(`document.querySelector('#results button').click()`);
  await sleep(600);
  check('searching for someone outside the focus refocuses', (await ev(`location.hash`)) === '#/focus/smith-tom');
  await ev(`document.querySelector('#focus-bar a.back').click()`);
  await sleep(600);
  check('"Show full tree" returns to the full tree on that person', (await ev(`location.hash`)) === '#/tree/smith-tom');
  check('full tree is back and the bar is gone', (await ev(`document.querySelectorAll('.node').length`)) > 5 && (await ev(`document.getElementById('focus-bar').hidden`)) === true);
  await goto('#/tree');
  await click('.node[data-id="smith-bob"]');
  await sleep(600);
  await ev(`document.querySelector('#panel a[href="#/focus/smith-bob"]').click()`);
  await sleep(600);
  check('panel "Focus tree" action focuses the person', (await ev(`location.hash`)) === '#/focus/smith-bob' && (await ev(`document.querySelectorAll('.node.focus').length`)) === 1);
  await ev(`document.querySelector('#focus-bar a.back').click()`);
  await sleep(400);

  // ---- timeline
  await ev(`document.querySelector('#tabs a[data-view="timeline"]').click()`);
  await sleep(800);
  check('timeline tab shows the timeline and really hides the tree', (await ev(`getComputedStyle(document.getElementById('timeline')).display !== 'none' && getComputedStyle(document.getElementById('tree')).display === 'none'`)) === true);
  check('timeline tab is marked current', (await ev(`document.querySelector('#tabs a[data-view="timeline"]').getAttribute('aria-current')`)) === 'page');
  const evCount = await ev(`document.querySelectorAll('#timeline-svg .ev').length`);
  check('timeline renders events', evCount >= 5, evCount);
  check('timeline shows the divorce', (await ev(`document.querySelectorAll('#timeline-svg .ev.divorce').length`)) >= 1);
  check('timeline header says family', (await ev(`document.querySelector('#timeline-head h2')?.textContent`)) === 'Family timeline');
  await shot('timeline-family');

  // ---- moving along the timeline
  const mouse = (type, x, y, extra = {}) => send('Input.dispatchMouseEvent', { type, x, y, ...extra });
  const readout = () => ev(`document.getElementById('tl-range').textContent`);
  const yearsInView = async () => Number(/·\s+(\d+) years/.exec(await readout())?.[1]);
  const r0 = await readout();
  check('timeline shows a position indicator', /years in view/.test(r0), r0);
  check('timeline has pan and zoom buttons', (await ev(`['tl-left','tl-right','tl-zoom-in','tl-zoom-out','tl-fit'].every((i) => !!document.getElementById(i))`)) === true);
  await mouse('mouseMoved', 700, 650);
  await mouse('mousePressed', 700, 650, { button: 'left', clickCount: 1 });
  await mouse('mouseMoved', 500, 650, { buttons: 1 });
  await mouse('mouseReleased', 500, 650, { button: 'left', clickCount: 1 });
  const r1 = await readout();
  check('dragging pans the timeline', r1 !== r0, `${r0} -> ${r1}`);
  await mouse('mouseMoved', 200, 650);
  await mouse('mouseMoved', 100, 650);
  check('the drag really releases', (await readout()) === r1);
  await mouse('mouseWheel', 700, 400, { deltaX: 200, deltaY: 0 });
  const r2 = await readout();
  check('sideways wheel pans', r2 !== r1, `${r1} -> ${r2}`);
  await mouse('mouseWheel', 700, 400, { deltaX: 0, deltaY: 200, modifiers: 8 });
  const r3 = await readout();
  check('Shift+wheel pans', r3 !== r2, `${r2} -> ${r3}`);
  const before = await yearsInView();
  await mouse('mouseWheel', 700, 400, { deltaX: 0, deltaY: -300 });
  check('plain wheel zooms in', (await yearsInView()) < before);
  await click('#tl-right');
  const r4 = await readout();
  check('right button moves along the timeline', r4 !== (await (async () => { await click('#tl-left'); await click('#tl-left'); return readout(); })()));
  const z0 = await yearsInView();
  await click('#tl-zoom-in');
  check('zoom-in button zooms in', (await yearsInView()) < z0);
  await click('#tl-zoom-out');
  await click('#tl-zoom-out');
  check('zoom-out button zooms out', (await yearsInView()) > z0);
  const thumbPct = await ev(`parseFloat(document.querySelector('#timeline-scroll .thumb').style.width)`);
  check('scrollbar thumb reflects the visible part', thumbPct > 0 && thumbPct <= 100, thumbPct);
  const k0 = await readout();
  await ev(`document.dispatchEvent(new KeyboardEvent('keydown', {key: 'ArrowRight', bubbles: true}))`);
  check('arrow keys move along the timeline', (await readout()) !== k0);
  await click('#tl-fit');
  check('Fit restores the overview', (await readout()) === r0);
  await mouse('mousePressed', 80, 770, { button: 'left', clickCount: 1 });
  await mouse('mouseReleased', 80, 770, { button: 'left', clickCount: 1 });
  const geom = await ev(`(() => { const r = document.getElementById('timeline-scroll').getBoundingClientRect(); return [r.left, r.top, r.width, r.height]; })()`);
  check('scrollbar is on screen', geom[2] > 100 && geom[1] > 0, JSON.stringify(geom));
  await click('#timeline-svg .ev');
  await sleep(500);
  check('clicking an event opens the panel', (await ev(`!document.getElementById('panel').hidden`)) === true);
  await click('#panel .close');
  await sleep(200);
  check('panel closes in the timeline too', (await ev(`document.getElementById('panel').hidden`)) === true);

  // ---- person timeline
  await goto('#/timeline/smith-bob');
  check('person timeline header', /Bob Smith — timeline/.test(await ev(`document.querySelector('#timeline-head h2')?.textContent`)));
  check('person timeline marks their own events', (await ev(`document.querySelectorAll('#timeline-svg .ev.self').length`)) >= 2);
  check('person timeline has a way back', (await ev(`!!document.querySelector('#timeline-head a.back')`)) === true);
  await shot('timeline-person');
  await goto('#/timeline/nobody-here');
  check('unknown person is reported, not crashed', /No such person/.test(await ev(`document.getElementById('timeline-head').textContent`)));

  // ---- navigation back and legacy route
  await goto('#/smith-bob');
  check('legacy #/<id> opens the tree selection', (await ev(`getComputedStyle(document.getElementById('tree')).display !== 'none' && getComputedStyle(document.getElementById('timeline')).display === 'none' && !!document.querySelector('.node.selected')`)) === true);

  // ---- search
  await goto('#/tree');
  await ev(`(() => { const s = document.getElementById('search'); s.value = 'tom'; s.dispatchEvent(new Event('input')); })()`);
  await sleep(200);
  check('search lists matches', (await ev(`document.querySelectorAll('#results li').length`)) >= 1);

  check('no script errors', errors.length === 0, errors.join(' | '));
  ws.close();
}

try { await main(); } catch (e) { console.log('FAIL  harness error -> ' + e.stack); failures++; }
proc.kill();
process.exit(failures ? 1 : 0);
