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
  const strokes = await ev(`(() => { const css = (sel, prop) => { const e = document.querySelector(sel); return e ? getComputedStyle(e)[prop] : null; }; return { childW: parseFloat(css('.edge.child', 'strokeWidth')), spouseW: parseFloat(css('.edge.spouse', 'strokeWidth')), edgeFx: css('.edge.child', 'vectorEffect'), nodeFx: css('.node rect', 'vectorEffect'), nodeW: parseFloat(css('.node rect', 'strokeWidth')), dotR: parseFloat((document.querySelector('.union') || {getAttribute: () => '0'}).getAttribute('r')) }; })()`);
  check('edges keep a constant on-screen width at any zoom', strokes.edgeFx === 'non-scaling-stroke' && strokes.nodeFx === 'non-scaling-stroke', JSON.stringify(strokes));
  check('parent-to-child lines are heavier than spouse links and at least 2px', strokes.childW >= 2 && strokes.spouseW >= 1.5 && strokes.childW > strokes.spouseW, JSON.stringify(strokes));
  check('couple junction dots stay visible when zoomed out', strokes.dotR >= 3, JSON.stringify(strokes));
  const overflow = await ev(`(() => { const bad = []; document.querySelectorAll('.node').forEach((g) => { const r = g.querySelector('rect').getBBox(); g.querySelectorAll('text').forEach((t) => { if (!t.textContent) return; const b = t.getBBox(); if (b.x < r.x + 4 || b.x + b.width > r.x + r.width - 4) bad.push(g.dataset.id + ':' + t.textContent + ':' + Math.round(b.width) + '/' + r.width); }); }); return bad; })()`);
  check('no node text comes within 4px of its box edge', overflow.length === 0, overflow.join('; '));
  const sameRow = await ev(`(() => { const y = (id) => document.querySelector('.node[data-id="' + id + '"] rect')?.getAttribute('y'); return [y('smith-bob'), y('ellsworth-maude')]; })()`);
  check('siblings share a row', sameRow[0] && sameRow[0] === sameRow[1], JSON.stringify(sameRow));
  check('ended partnership draws a dashed spouse line', (await ev(`document.querySelectorAll('.edge.spouse.ended').length`)) >= 1);
  check('ended partnership has a hollow dot', (await ev(`document.querySelectorAll('.union.ended').length`)) >= 1);

  // ---- family colours (nothing selected)
  check('each couple draws its lines in a family colour', (await ev(`document.querySelectorAll('.edge[class*="fam-"]').length`)) >= 1);
  check('no legend and no highlight mode when nothing is selected', (await ev(`document.getElementById('legend').hidden && !document.getElementById('tree').classList.contains('has-hl')`)) === true);

  // ---- hover preview
  await ev(`document.querySelector('.node[data-id="smith-bob"]').dispatchEvent(new PointerEvent('pointerenter'))`);
  await sleep(200);
  check('hovering a person previews their relatives with the legend', (await ev(`!document.getElementById('legend').hidden && document.querySelectorAll('.node.role-parent').length >= 2`)) === true);
  check('hovering does not open the panel', (await ev(`document.getElementById('panel').hidden`)) === true);
  await ev(`document.querySelector('.node[data-id="smith-bob"]').dispatchEvent(new PointerEvent('pointerleave'))`);
  await sleep(200);
  check('leaving a person clears the preview', (await ev(`document.getElementById('legend').hidden && document.querySelectorAll('.node.related').length === 0`)) === true);

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
  check('relatives are marked related', (await ev(`document.querySelectorAll('.node.related').length`)) >= 2);
  check('unrelated people and lines are faded', (await ev(`document.querySelectorAll('.node.dim').length`)) >= 1);
  check('parents, siblings and children are told apart by role', (await ev(`document.querySelectorAll('.node.role-parent').length >= 2 && document.querySelectorAll('.node.role-sibling').length >= 1`)) === true);
  check('the connectors carry the same roles', (await ev(`document.querySelectorAll('.edge.role-parent').length >= 1 && document.querySelectorAll('.edge.role-sibling').length >= 1`)) === true);
  check('roles are different colours', (await ev(`(() => { const c = (sel) => getComputedStyle(document.querySelector(sel)).stroke; return c('.edge.role-parent') !== c('.edge.role-sibling'); })()`)) === true);
  check('family colours step aside while a person is highlighted', (await ev(`document.getElementById('tree').classList.contains('has-hl') && document.querySelectorAll('.edge[class*="fam-"]').length === 0`)) === true);
  check('the legend names the roles on screen', (await ev(`(() => { const l = document.getElementById('legend'); return !l.hidden && /Parents/.test(l.textContent) && /Siblings/.test(l.textContent); })()`)) === true);
  // ---- lineage colours
  check('the legend offers the two colour modes', (await ev(`!!document.querySelector('#legend [data-mode="family"]') && !!document.querySelector('#legend [data-mode="lineage"]')`)) === true);
  await click('#legend [data-mode="lineage"]');
  await sleep(300);
  check('lineage mode shades ancestors and descendants', (await ev(`document.querySelectorAll('.node.lin-old').length >= 1 && document.querySelectorAll('.node.lin-new').length >= 1 && document.querySelectorAll('.edge.lin').length >= 1`)) === true);
  check('oldest and youngest are different colours', (await ev(`(() => { const c = (sel) => getComputedStyle(document.querySelector(sel + ' rect')).stroke; return c('.node.lin-old') !== c('.node.lin-new'); })()`)) === true);
  check('relatives off the line fade in lineage mode', (await ev(`document.querySelector('.node[data-id="ellsworth-maude"]').classList.contains('dim')`)) === true);
  check('the selected person keeps their own outline in lineage mode', (await ev(`document.querySelectorAll('.node.selected').length`)) === 1);
  check('the legend shows the ramp and its ends', (await ev(`(() => { const l = document.getElementById('legend'); return !!l.querySelector('.legend-ramp') && /Oldest/.test(l.textContent) && /Youngest/.test(l.textContent); })()`)) === true);
  check('node tooltips say how many generations away someone is', (await ev(`[...document.querySelectorAll('.node.lin-old title')].some((t) => /generations? above/.test(t.textContent))`)) === true);
  check('the colour mode is remembered', (await ev(`localStorage.getItem('famsite.colourMode')`)) === 'lineage');
  await click('#legend [data-mode="family"]');
  await sleep(300);
  check('switching back restores the relationship colours', (await ev(`document.querySelectorAll('.node.role-parent').length >= 2 && document.querySelectorAll('.node.lin').length === 0`)) === true);
  await shot('tree-panel-open');
  await click('#panel .close');
  await sleep(300);
  check('close button hides the panel', (await ev(`document.getElementById('panel').hidden`)) === true);
  check('close deselects the node', (await ev(`document.querySelectorAll('.node.selected').length`)) === 0);
  check('close clears the url selection', (await ev(`location.hash`)) === '#/tree');
  check('close removes all highlighting', (await ev(`document.querySelectorAll('.edge.hi, .edge.dim, .node.dim, .node.related').length`)) === 0);
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
  ws.close();
}

try { await main(); } catch (e) { console.log('FAIL  harness error -> ' + e.stack); failures++; }
proc.kill();
process.exit(failures ? 1 : 0);
