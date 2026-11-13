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

  await send('Page.navigate', { url: base + '/tree.html#/tree' });
  await sleep(1500);

  // ---- tree
  const nodeCount = await ev(`document.querySelectorAll('.node').length`);
  check('tree renders nodes', nodeCount >= 5, nodeCount);
  const strokes = await ev(`(() => { const css = (sel, prop) => { const e = document.querySelector(sel); return e ? getComputedStyle(e)[prop] : null; }; return { childW: parseFloat(css('.edge.child', 'strokeWidth')), spouseW: parseFloat(css('.edge.spouse', 'strokeWidth')), edgeFx: css('.edge.child', 'vectorEffect'), nodeFx: css('.node rect', 'vectorEffect'), nodeW: parseFloat(css('.node rect', 'strokeWidth')), dotR: parseFloat((document.querySelector('.union') || {getAttribute: () => '0'}).getAttribute('r')) }; })()`);
  check('edges keep a constant on-screen width at any zoom', strokes.edgeFx === 'non-scaling-stroke' && strokes.nodeFx === 'non-scaling-stroke', JSON.stringify(strokes));
  check('parent-to-child lines are heavier than spouse links and never hairlines', strokes.childW >= 1.25 && strokes.spouseW >= 1 && strokes.childW > strokes.spouseW, JSON.stringify(strokes));
  const outline = await ev(`(() => { const m = getComputedStyle(document.querySelector('.node rect')).stroke.match(/\\d+/g).map(Number); return (0.2126 * m[0] + 0.7152 * m[1] + 0.0722 * m[2]) / 255; })()`);
  check('box outlines are light and quiet at rest', outline > 0.62 && strokes.nodeW <= 1, outline + ' / ' + strokes.nodeW);
  check('couple junction dots stay visible when zoomed out', strokes.dotR >= 3, JSON.stringify(strokes));
  const overflow = await ev(`(() => { const bad = []; document.querySelectorAll('.node').forEach((g) => { const r = g.querySelector('rect').getBBox(); g.querySelectorAll('text').forEach((t) => { if (!t.textContent) return; const b = t.getBBox(); if (b.x < r.x + 4 || b.x + b.width > r.x + r.width - 4) bad.push(g.dataset.id + ':' + t.textContent + ':' + Math.round(b.width) + '/' + r.width); }); }); return bad; })()`);
  check('no node text comes within 4px of its box edge', overflow.length === 0, overflow.join('; '));
  const sameRow = await ev(`(() => { const y = (id) => document.querySelector('.node[data-id="' + id + '"] rect')?.getAttribute('y'); return [y('smith-bob'), y('ellsworth-maude')]; })()`);
  check('siblings share a row', sameRow[0] && sameRow[0] === sameRow[1], JSON.stringify(sameRow));
  check('ended partnership draws a dashed spouse line', (await ev(`document.querySelectorAll('.edge.spouse.ended').length`)) >= 1);
  check('ended partnership has a hollow dot', (await ev(`document.querySelectorAll('.union.ended').length`)) >= 1);

  // ---- unconnected people are set apart
  check('people with no relatives sit in a labelled group below the tree', (await ev(`(() => { const label = [...document.querySelectorAll('#tree .group-label')].find((t) => /Not connected/.test(t.textContent)); const lone = document.querySelector('.node[data-id="lone-person"] rect'); const bob = document.querySelector('.node[data-id="smith-bob"] rect'); return !!label && !!lone && Number(lone.getAttribute('y')) > Number(bob.getAttribute('y')) + 64; })()`)) === true);

  // ---- resting state: quiet and uniform
  check('at rest every connector is one neutral colour, with no per-family rainbow', (await ev(`new Set([...document.querySelectorAll('.edge')].map((e) => getComputedStyle(e).stroke)).size === 1 && document.querySelectorAll('.edge[class*="fam-"]').length === 0`)) === true);
  check('no legend and no highlight mode when nothing is selected', (await ev(`document.getElementById('legend').hidden && !document.getElementById('tree').classList.contains('has-hl')`)) === true);

  // ---- hover only accents the node under the pointer (recolouring the whole tree on hover made panning lag)
  const centre = (id) => ev(`(() => { const r = document.querySelector('.node[data-id="${id}"] rect').getBoundingClientRect(); return [r.x + r.width / 2, r.y + r.height / 2]; })()`);
  const restStroke = await ev(`getComputedStyle(document.querySelector('.node[data-id="smith-bob"] rect')).stroke`);
  const [bx, by] = await centre('smith-bob');
  await send('Input.dispatchMouseEvent', { type: 'mouseMoved', x: bx, y: by });
  await sleep(250);
  const hoverStroke = await ev(`getComputedStyle(document.querySelector('.node[data-id="smith-bob"] rect')).stroke`);
  check('the hovered person is accented', hoverStroke !== restStroke, restStroke + ' -> ' + hoverStroke);
  check('hovering does not recolour the rest of the tree or open anything', (await ev(`!document.getElementById('tree').classList.contains('has-hl') && document.getElementById('legend').hidden && document.getElementById('panel').hidden && document.querySelectorAll('.node.lin, .node.dim, .node.related, .edge.hi').length === 0`)) === true);
  await send('Input.dispatchMouseEvent', { type: 'mouseMoved', x: 5, y: 5 });
  await sleep(250);
  check('moving off restores the resting look', (await ev(`getComputedStyle(document.querySelector('.node[data-id="smith-bob"] rect')).stroke`)) === restStroke);

  // ---- panel open / close / deselect
  await click('.node[data-id="smith-bob"]');
  await sleep(600);
  check('click opens the panel', (await ev(`!document.getElementById('panel').hidden`)) === true);
  check('panel shows the person', (await ev(`document.querySelector('#panel h2')?.textContent`)) === 'Bob Smith');
  check('panel avatar shows initials', (await ev(`document.querySelector('#panel .avatar')?.textContent`)) === 'BS');
  check('panel groups relatives as chips', (await ev(`document.querySelectorAll('#panel .chip').length`)) >= 2);
  check('panel lists siblings', /Siblings/.test(await ev(`document.getElementById('panel').textContent`)));
  check('panel has action pills', (await ev(`document.querySelectorAll('#panel .pill').length`)) >= 3);
  check('node is highlighted', (await ev(`document.querySelectorAll('.node.selected').length`)) === 1);
  check('url records the selection', (await ev(`location.hash`)) === '#/tree/smith-bob');
  check('selected person lights up connectors', (await ev(`document.querySelectorAll('.edge.hi').length`)) >= 1);
  check('relatives are marked', (await ev(`document.querySelectorAll('.node.lin, .node.related').length`)) >= 2);
  check('unrelated people and lines are faded', (await ev(`document.querySelectorAll('.node.dim').length`)) >= 1);
  // ---- default: lineage colours
  const hsvSat = (sel) => ev(`(() => { const css = getComputedStyle(document.querySelector(${JSON.stringify(sel)})).stroke; const c = document.createElement('canvas').getContext('2d', { willReadFrequently: true }); c.fillStyle = '#000'; c.fillStyle = css; c.fillRect(0, 0, 1, 1); const m = c.getImageData(0, 0, 1, 1).data; return (Math.max(m[0], m[1], m[2]) - Math.min(m[0], m[1], m[2])) / Math.max(m[0], m[1], m[2], 1); })()`);
  check('highlighted lines and outlines are slim', (await ev(`parseFloat(getComputedStyle(document.querySelector('.edge.lin')).strokeWidth) <= 1.75 && parseFloat(getComputedStyle(document.querySelector('.node.lin rect')).strokeWidth) <= 1.75`)) === true);
  const satOld = await hsvSat('.node.lin-old rect');
  const satNew = await hsvSat('.node.lin-new rect');
  check('the generation colours are muted, not saturated', satOld <= 0.62 && satNew <= 0.62, satOld.toFixed(2) + ' / ' + satNew.toFixed(2));
  check('the generation ramp is the default colouring', (await ev(`document.querySelectorAll('.node.lin-old').length >= 1 && document.querySelectorAll('.node.lin-new').length >= 1 && document.querySelectorAll('.edge.lin').length >= 1`)) === true);
  check('oldest and youngest are different colours', (await ev(`(() => { const c = (sel) => getComputedStyle(document.querySelector(sel + ' rect')).stroke; return c('.node.lin-old') !== c('.node.lin-new'); })()`)) === true);
  check('relatives off the line fade', (await ev(`document.querySelector('.node[data-id="ellsworth-maude"]').classList.contains('dim')`)) === true);
  check('the selected person keeps their own outline', (await ev(`document.querySelectorAll('.node.selected').length`)) === 1);
  check('the legend shows the ramp and its ends', (await ev(`(() => { const l = document.getElementById('legend'); return !l.hidden && !!l.querySelector('.legend-ramp') && /generations? (up|down)/.test(l.textContent); })()`)) === true);
  check('node tooltips say how many generations away someone is', (await ev(`[...document.querySelectorAll('.node.lin-old title')].some((t) => /generations? above/.test(t.textContent))`)) === true);
  check('the legend offers both colour modes', (await ev(`!!document.querySelector('#legend [data-mode="family"]') && !!document.querySelector('#legend [data-mode="lineage"]')`)) === true);
  // ---- relationship colours, one click away
  await click('#legend [data-mode="family"]');
  await sleep(300);
  check('parents, siblings and children are told apart by role', (await ev(`document.querySelectorAll('.node.role-parent').length >= 2 && document.querySelectorAll('.node.role-sibling').length >= 1 && document.querySelectorAll('.node.lin').length === 0`)) === true);
  check('the connectors carry the same roles', (await ev(`document.querySelectorAll('.edge.role-parent').length >= 1 && document.querySelectorAll('.edge.role-sibling').length >= 1`)) === true);
  check('roles are different colours', (await ev(`(() => { const c = (sel) => getComputedStyle(document.querySelector(sel)).stroke; return c('.edge.role-parent') !== c('.edge.role-sibling'); })()`)) === true);
  check('the legend names the roles on screen', (await ev(`(() => { const l = document.getElementById('legend'); return !l.hidden && /Parents/.test(l.textContent) && /Siblings/.test(l.textContent); })()`)) === true);
  check('the chosen mode is remembered', (await ev(`localStorage.getItem('famsite.colourMode')`)) === 'family');
  await click('#legend [data-mode="lineage"]');
  await sleep(300);
  check('switching back restores the generation ramp', (await ev(`document.querySelectorAll('.node.lin-old').length >= 1 && document.querySelectorAll('.node.role-parent').length === 0`)) === true);
  await shot('tree-panel-open');
  await click('#panel .close');
  await sleep(300);
  check('close button hides the panel', (await ev(`document.getElementById('panel').hidden`)) === true);
  check('close deselects the node', (await ev(`document.querySelectorAll('.node.selected').length`)) === 0);
  check('close clears the url selection', (await ev(`location.hash`)) === '#/tree');
  check('close removes all highlighting', (await ev(`document.querySelectorAll('.edge.hi, .edge.dim, .node.dim, .node.related, .node.lin').length`)) === 0);
  check('close hides the legend', (await ev(`document.getElementById('legend').hidden`)) === true);
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
  check('tree tab is current in focus', (await ev(`document.querySelector('#tabs a[data-view="focus"]').getAttribute('aria-current')`)) === 'page');
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
  check('the relationship legend never shows over the timeline', (await ev(`document.getElementById('legend').hidden`)) === true);
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

  // ---- opening view
  await send('Page.navigate', { url: 'about:blank' }); await sleep(100);
  await send('Page.navigate', { url: base + '/tree.html' }); await sleep(1500);
  const home = await ev(`document.querySelector('meta[name="famsite-home"]').content`);
  check('with no route the viewer opens the home person\'s focused tree', (await ev('location.hash')) === '#/focus/' + home, await ev('location.hash'));
  check('the Tree tab is current in a focused tree', (await ev(`document.querySelector('#tabs a[aria-current="page"]').textContent`)) === 'Tree');
  const openH = await ev(`document.querySelector('.node rect').getBoundingClientRect().height`);
  check('nodes open at a readable size', openH >= 64 * 0.6, openH);
  await goto('#/tree');
  for (let i = 0; i < 12; i++) await ev(`document.getElementById('tree').dispatchEvent(new WheelEvent('wheel', { deltaY: 600, clientX: 600, clientY: 400, bubbles: true, cancelable: true }))`);
  check('the tree can be zoomed far out', (await ev(`document.querySelector('.node rect').getBoundingClientRect().height`)) < 64 * 0.35);
  await goto('#/tree/smith-bob');
  const selH = await ev(`document.querySelector('.node.selected rect').getBoundingClientRect().height`);
  check('selecting a person from far out zooms in to them', Math.abs(selH - 64) < 1, selH);

  // ---- controls
  await goto('#/tree');
  const h0 = await ev(`document.querySelector('.node rect').getBoundingClientRect().height`);
  await click('#tree-controls [data-act="zoom-in"]');
  const h1 = await ev(`document.querySelector('.node rect').getBoundingClientRect().height`);
  check('the + button zooms in by one step', Math.abs(h1 / h0 - 1.4) < 0.02 || h1 === 64 * 3, h0 + ' -> ' + h1);
  await click('#tree-controls [data-act="home"]');
  check('Home opens the home person\'s focused tree', (await ev('location.hash')) === '#/focus/' + home);
  await goto('#/tree/smith-bob');
  const p0 = await ev(`document.querySelector('.node.selected rect').getBoundingClientRect().height`);
  await ev(`(() => { const t = document.getElementById('tree'); const pe = (type, id, x, target) => (target || t).dispatchEvent(new PointerEvent(type, { pointerId: id, clientX: x, clientY: 400, bubbles: true })); pe('pointerdown', 1, 500); pe('pointerdown', 2, 600); pe('pointermove', 2, 800, window); pe('pointerup', 1, 500, window); pe('pointerup', 2, 800, window); })()`);
  await sleep(100);
  const p1 = await ev(`document.querySelector('.node.selected rect').getBoundingClientRect().height`);
  check('two pointers moving apart zoom in, and the panel stays open', p1 > p0 * 1.5 && (await ev(`!document.getElementById('panel').hidden`)) === true, p0 + ' -> ' + p1);
  await ev(`document.dispatchEvent(new KeyboardEvent('keydown', { key: '0', bubbles: true }))`);
  check('the 0 key fits the tree', (await ev(`document.querySelector('.node.selected rect').getBoundingClientRect().height`)) < p1);
  check('controls are hidden on the timeline', (await goto('#/timeline'), await ev(`document.getElementById('tree-controls').hidden`)) === true);

  // ---- level of detail
  await goto('#/tree');
  for (let i = 0; i < 12; i++) await ev(`document.getElementById('tree').dispatchEvent(new WheelEvent('wheel', { deltaY: 600, clientX: 600, clientY: 400, bubbles: true, cancelable: true }))`);
  check('far out, names give way to family labels', (await ev(`(() => { const t = document.getElementById('tree'); const name = document.querySelector('.node text'); const label = document.querySelector('.group-label.island'); return t.classList.contains('lod-far') && getComputedStyle(name).display === 'none' && !!label && getComputedStyle(label).display !== 'none'; })()`)) === true);
  await click('#tree-controls [data-act="fit"]');
  check('island labels are hidden when names are readable', (await ev(`(() => { const l = document.querySelector('.group-label.island'); return document.getElementById('tree').classList.contains('lod-near') && (!l || getComputedStyle(l).display === 'none'); })()`)) === true);

  // ---- focus extras
  await goto('#/focus/smith-bob');
  const badge = await ev(`(() => { const b = document.querySelector('.node .more'); return b ? b.textContent : null; })()`);
  check('a focused tree marks nodes with relatives it leaves out', /^\+\d+$/.test(badge || ''), badge);
  check('the focus node and a selected node share one accent', (await ev(`(() => { const f = getComputedStyle(document.querySelector('.node.focus rect')).stroke; document.querySelector('.node:not(.focus)').dispatchEvent(new MouseEvent('click', { bubbles: true })); return f === getComputedStyle(document.querySelector('.node.selected rect')).stroke; })()`)) === true);
  check('the legend counts generations in words', /generations? (up|down)/.test(await ev(`document.getElementById('legend').textContent`)));

  check('no script errors', errors.length === 0, errors.join(' | '));

  // ---- full person page (static, no JS)
  await send('Emulation.setDeviceMetricsOverride', { width: 390, height: 800, deviceScaleFactor: 1, mobile: false });
  await send('Page.navigate', { url: base + '/p/smith-bob/' });
  await sleep(800);
  check('person page has the name and avatar', (await ev(`document.querySelector('.hero h1')?.textContent`)) === 'Bob Smith' && (await ev(`document.querySelector('.hero .avatar')?.textContent`)) === 'BS');
  check('person page lists life events', (await ev(`document.querySelectorAll('.events li').length`)) >= 2);
  check('person page has no horizontal overflow at 390px', (await ev(`document.documentElement.scrollWidth <= window.innerWidth`)) === true);
  await send('Emulation.clearDeviceMetricsOverride');
  check('relative chips link to their pages', (await ev(`[...document.querySelectorAll('.chip')].every((a) => /^\\.\\.\\/[a-z0-9-]+\\/$/.test(a.getAttribute('href')))`)) === true);
  check('person page embeds the lifeline and the family tree', (await ev(`!!document.querySelector('.lifeline') && !!document.querySelector('.mini-tree a')`)) === true);
  check('person page has no horizontal overflow at 1280px', (await ev(`document.documentElement.scrollWidth <= window.innerWidth`)) === true);
  const nodeHref = await ev(`(() => { const a = [...document.querySelectorAll('.mini-tree a')].find((x) => x.getAttribute('href') !== '../smith-bob/'); return a ? a.getAttribute('href') : null; })()`);
  check('a family tree node links to a relative page', /^\.\.\/[a-z0-9-]+\/$/.test(nodeHref || ''), nodeHref);
  await send('Page.navigate', { url: base + '/p/' + (nodeHref || '../smith-bob/').replace(/^\.\.\//, '') });
  await sleep(600);
  check('the relative page opens with its own name', (await ev(`document.querySelector('.hero h1')?.textContent`)) !== 'Bob Smith' && !!(await ev(`document.querySelector('.hero h1')?.textContent`)));

  await send('Page.navigate', { url: base + '/index.html#/tree/smith-bob' }); await sleep(1500);
  check('an old viewer link is forwarded to tree.html', /\/tree\.html#\/tree\/smith-bob$/.test(await ev('location.href')), await ev('location.href'));

  // ---- phone
  await send('Emulation.setDeviceMetricsOverride', { width: 390, height: 844, deviceScaleFactor: 1, mobile: true });
  await send('Page.navigate', { url: base + '/tree.html#/tree/ellsworth-maude' });
  await sleep(1500);
  const phone = await ev(`(() => { const p = document.getElementById('panel').getBoundingClientRect(); const h = document.querySelector('#panel h2').getBoundingClientRect(); const s = document.getElementById('search').getBoundingClientRect(); return { panelW: p.width, panelBottom: p.bottom, panelH: p.height, titleW: h.width, searchRight: s.right, pageW: document.documentElement.scrollWidth }; })()`);
  check('phone: the panel is a full-width bottom sheet', phone.panelW === 390 && Math.round(phone.panelBottom) === 844 && phone.panelH <= 844 * 0.6 + 1, JSON.stringify(phone));
  check('phone: the panel title has room to read', phone.titleW >= 200, JSON.stringify(phone));
  check('phone: nothing is wider than the screen', phone.searchRight <= 390 && phone.pageW <= 390, JSON.stringify(phone));
  await ev(`document.querySelector('#panel h2').textContent = 'W'.repeat(40)`);
  check('phone: a long unbroken name wraps inside the sheet', (await ev(`document.documentElement.scrollWidth <= 390 && document.getElementById('panel').scrollWidth <= 390`)) === true);
  await shot('phone-panel');
  await send('Emulation.setDeviceMetricsOverride', { width: 1400, height: 820, deviceScaleFactor: 1, mobile: false });

  ws.close();
}

try { await main(); } catch (e) { console.log('FAIL  harness error -> ' + e.stack); failures++; }
proc.kill();
process.exit(failures ? 1 : 0);
