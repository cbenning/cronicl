const test = require('node:test');
const assert = require('node:assert');
const v = require('../../src/famsite/viewer/viewer.js');

const measure = (s) => s.length * 7; // 7px per character
const MAX = 140; // 20 characters

test('wrapName keeps a short name on one line', () => {
  assert.deepStrictEqual(v.wrapName('Bob Smith', MAX, measure), { lines: ['Bob Smith'], truncated: false });
});

test('wrapName wraps a long name onto two lines without an ellipsis', () => {
  const r = v.wrapName('Maude Sylvie Marnie Ellsworth', MAX, measure);
  assert.deepStrictEqual(r.lines, ['Maude Sylvie Marnie', 'Ellsworth']);
  assert.strictEqual(r.truncated, false);
});

test('wrapName ends with an ellipsis when it cannot fit in two lines', () => {
  const r = v.wrapName('Jeremiah Humphrey Alexander Ashby Herbert', MAX, measure);
  assert.strictEqual(r.lines.length, 2);
  assert.ok(r.lines[1].endsWith('…'));
  assert.ok(r.lines.every((l) => measure(l) <= MAX));
  assert.strictEqual(r.truncated, true);
});

test('wrapName hard-cuts a single word wider than the box', () => {
  const r = v.wrapName('Pneumonoultramicroscopicsilico', MAX, measure);
  assert.strictEqual(r.lines.length, 1);
  assert.ok(r.lines[0].endsWith('…') && measure(r.lines[0]) <= MAX);
});

test('wrapName tolerates empty input', () => {
  assert.deepStrictEqual(v.wrapName('', MAX, measure), { lines: [''], truncated: false });
});

test('parseRoute understands views, ids and the legacy bare id', () => {
  assert.deepStrictEqual(v.parseRoute(''), { view: 'tree', id: null });
  assert.deepStrictEqual(v.parseRoute('#/tree'), { view: 'tree', id: null });
  assert.deepStrictEqual(v.parseRoute('#/tree/smith-bob'), { view: 'tree', id: 'smith-bob' });
  assert.deepStrictEqual(v.parseRoute('#/timeline'), { view: 'timeline', id: null });
  assert.deepStrictEqual(v.parseRoute('#/timeline/smith-bob'), { view: 'timeline', id: 'smith-bob' });
  assert.deepStrictEqual(v.parseRoute('#/smith-bob'), { view: 'tree', id: 'smith-bob' });
  assert.deepStrictEqual(v.parseRoute('#/focus/smith-bob'), { view: 'focus', id: 'smith-bob' });
  assert.deepStrictEqual(v.parseRoute('#/focus'), { view: 'focus', id: null });
});

test('routeHash round-trips', () => {
  assert.strictEqual(v.routeHash('timeline', 'a-b'), '#/timeline/a-b');
  assert.strictEqual(v.routeHash('tree', null), '#/tree');
});

test('yearPosition places dated events inside their year', () => {
  assert.strictEqual(v.yearPosition({ year: 1950, month: null, day: null }), 1950.5);
  assert.ok(v.yearPosition({ year: 1950, month: 6, day: 1 }) > 1950.4);
  assert.ok(v.yearPosition({ year: 1950, month: 1, day: 1 }) >= 1950);
});

const fam = {
  unions: [
    { id: 'a+b', x: 0, y: 0, members: ['a', 'b'] },
    { id: 'c+x', x: 0, y: 0, members: ['c', 'x'] },
    { id: 'solo+', x: 0, y: 0, members: ['solo'] },
  ],
  edges: [
    { from: 'a', to: 'a+b', kind: 'spouse' },
    { from: 'b', to: 'a+b', kind: 'spouse' },
    { from: 'a+b', to: 'c', kind: 'child' },
    { from: 'a+b', to: 'd', kind: 'child' },
    { from: 'c', to: 'c+x', kind: 'spouse' },
    { from: 'x', to: 'c+x', kind: 'spouse' },
    { from: 'c+x', to: 'e', kind: 'child' },
    { from: 'solo+', to: 'k', kind: 'child' },
  ],
};

test('relatedFor colours the parents line, partners, children and siblings by role', () => {
  const r = v.relatedFor(fam, 'c');
  assert.deepStrictEqual(Object.fromEntries(r.people), { a: 'parent', b: 'parent', d: 'sibling', x: 'partner', e: 'child' });
  assert.deepStrictEqual(Object.fromEntries(r.edges), { 0: 'parent', 1: 'parent', 2: 'parent', 3: 'sibling', 4: 'partner', 5: 'partner', 6: 'child' });
  assert.deepStrictEqual(Object.fromEntries(r.unions), { 'a+b': 'parent', 'c+x': 'partner' });
});

test('relatedFor works for a child with one known parent', () => {
  const r = v.relatedFor(fam, 'k');
  assert.deepStrictEqual(Object.fromEntries(r.people), { solo: 'parent' });
  assert.deepStrictEqual(Object.fromEntries(r.edges), { 7: 'parent' });
});

test('relatedFor of an unconnected person highlights nothing', () => {
  const r = v.relatedFor(fam, 'nobody');
  assert.strictEqual(r.edges.size, 0);
  assert.strictEqual(r.people.size, 0);
});

const halves = {
  unions: [
    { id: 'p+q', members: ['p', 'q'] },
    { id: 'p+r', members: ['p', 'r'] },
  ],
  edges: [
    { from: 'p', to: 'p+q', kind: 'spouse' },
    { from: 'q', to: 'p+q', kind: 'spouse' },
    { from: 'p+q', to: 'me', kind: 'child' },
    { from: 'p+q', to: 's1', kind: 'child' },
    { from: 'p', to: 'p+r', kind: 'spouse' },
    { from: 'r', to: 'p+r', kind: 'spouse' },
    { from: 'p+r', to: 'h', kind: 'child' },
  ],
};

test('relatedFor counts half-siblings through a shared parent as siblings and leaves the other partner out', () => {
  const r = v.relatedFor(halves, 'me');
  assert.deepStrictEqual(Object.fromEntries(r.people), { p: 'parent', q: 'parent', s1: 'sibling', h: 'sibling' });
  assert.strictEqual(r.edges.get(6), 'sibling');
  assert.ok(!r.edges.has(4) && !r.edges.has(5), "the parent's other partnership link is not highlighted");
});

test('legendFor lists only the roles present, in a fixed order, with counts', () => {
  const r = v.relatedFor(fam, 'c');
  assert.deepStrictEqual(v.legendFor(r), [
    { role: 'parent', label: 'Parents', count: 2 },
    { role: 'partner', label: 'Partners', count: 1 },
    { role: 'child', label: 'Children', count: 1 },
    { role: 'sibling', label: 'Siblings', count: 1 },
  ]);
  assert.deepStrictEqual(v.legendFor(v.relatedFor(fam, 'k')), [{ role: 'parent', label: 'Parents', count: 1 }]);
  assert.deepStrictEqual(v.legendFor(null), []);
});

// three generations above "me", two below; a sibling and an aunt who are not on the line
const lin = {
  unions: [
    { id: 'U1', members: ['g1', 'g2'] },
    { id: 'U2', members: ['p', 'q'] },
    { id: 'U3', members: ['me', 'w'] },
    { id: 'U4', members: ['k1', 'z'] },
  ],
  edges: [
    { from: 'g1', to: 'U1', kind: 'spouse' }, // 0
    { from: 'g2', to: 'U1', kind: 'spouse' }, // 1
    { from: 'U1', to: 'p', kind: 'child' }, // 2
    { from: 'U1', to: 'aunt', kind: 'child' }, // 3
    { from: 'p', to: 'U2', kind: 'spouse' }, // 4
    { from: 'q', to: 'U2', kind: 'spouse' }, // 5
    { from: 'U2', to: 'me', kind: 'child' }, // 6
    { from: 'U2', to: 'sib', kind: 'child' }, // 7
    { from: 'me', to: 'U3', kind: 'spouse' }, // 8
    { from: 'w', to: 'U3', kind: 'spouse' }, // 9
    { from: 'U3', to: 'k1', kind: 'child' }, // 10
    { from: 'U3', to: 'k2', kind: 'child' }, // 11
    { from: 'k1', to: 'U4', kind: 'spouse' }, // 12
    { from: 'z', to: 'U4', kind: 'spouse' }, // 13
    { from: 'U4', to: 'gk', kind: 'child' }, // 14
  ],
};

test('lineageFor numbers ancestors and descendants by generation and leaves collaterals out', () => {
  const r = v.lineageFor(lin, 'me');
  const gens = Object.fromEntries([...r.people].filter(([, e]) => !e.partner).map(([k, e]) => [k, e.d]));
  assert.deepStrictEqual(gens, { p: -1, q: -1, g1: -2, g2: -2, k1: 1, k2: 1, gk: 2 });
  const partners = Object.fromEntries([...r.people].filter(([, e]) => e.partner).map(([k, e]) => [k, e.d]));
  assert.deepStrictEqual(partners, { w: 0, z: 1 });
  assert.ok(!r.people.has('sib') && !r.people.has('aunt') && !r.people.has('me'));
  assert.strictEqual(r.up, 2);
  assert.strictEqual(r.down, 2);
});

test('lineageFor colours the lines and junctions of the line only', () => {
  const r = v.lineageFor(lin, 'me');
  assert.deepStrictEqual(Object.fromEntries(r.edges), {
    0: -2, 1: -2, 2: -1, 4: -1, 5: -1, 6: 0, 8: 0, 9: 0, 10: 1, 11: 1, 12: 1, 13: 1, 14: 2,
  });
  assert.ok(!r.edges.has(3) && !r.edges.has(7), "an aunt's and a sibling's descent are not on the line");
  assert.deepStrictEqual(Object.fromEntries(r.unions), { U1: -2, U2: -1, U3: 0, U4: 1 });
});

test('lineageFor copes with a person who has no ancestors or descendants', () => {
  const r = v.lineageFor({ unions: [], edges: [] }, 'x');
  assert.strictEqual(r.people.size, 0);
  assert.strictEqual(r.up, 0);
  assert.strictEqual(r.down, 0);
});

test('lineageShade spreads each side over the full ramp, whatever its depth', () => {
  assert.deepStrictEqual(v.lineageShade(-2, 2, 2), { side: 'old', pct: 100 });
  assert.deepStrictEqual(v.lineageShade(-1, 2, 2), { side: 'old', pct: 50 });
  assert.deepStrictEqual(v.lineageShade(1, 2, 4), { side: 'new', pct: 25 });
  assert.deepStrictEqual(v.lineageShade(1, 0, 1), { side: 'new', pct: 100 });
  assert.deepStrictEqual(v.lineageShade(0, 3, 3), { side: 'mid', pct: 0 });
});

test('generationLabel says how far above or below the selected person someone is', () => {
  assert.strictEqual(v.generationLabel(0), 'same generation');
  assert.strictEqual(v.generationLabel(-1), '1 generation above');
  assert.strictEqual(v.generationLabel(-3), '3 generations above');
  assert.strictEqual(v.generationLabel(2), '2 generations below');
});

test('initialView fits a layout that stays readable', () => {
  assert.deepStrictEqual(v.initialView({ w: 1000, h: 500 }, { w: 1400, h: 800 }, null), { scale: 1, tx: 200, ty: 150 });
  assert.deepStrictEqual(v.initialView({ w: 2000, h: 500 }, { w: 1400, h: 800 }, null), { scale: 0.7, tx: 0, ty: 225 });
});
test('initialView centres on the target at scale 1 when fitting would be unreadable', () => {
  const t = { x: 5000, y: 100, w: 160, h: 64 };
  assert.deepStrictEqual(v.initialView({ w: 10000, h: 500 }, { w: 1400, h: 800 }, t), { scale: 1, tx: -4380, ty: 268 });
  assert.deepStrictEqual(v.initialView({ w: 10000, h: 500 }, { w: 1400, h: 800 }, null), { scale: 1, tx: -4300, ty: 0 });
});
test('initialView never magnifies a tiny layout', () => {
  assert.strictEqual(v.initialView({ w: 224, h: 128 }, { w: 1400, h: 800 }, null).scale, 1);
});
test('lodFor picks the level of detail from the scale', () => {
  assert.deepStrictEqual([0.6, 0.59, 0.35, 0.34].map(v.lodFor), ['near', 'mid', 'mid', 'far']);
});
test('zoomAt keeps the point under the pointer still and clamps', () => {
  assert.deepStrictEqual(v.zoomAt({ scale: 1, tx: 0, ty: 0 }, 2, 100, 50), { scale: 2, tx: -100, ty: -50 });
  assert.strictEqual(v.zoomAt({ scale: 2, tx: 0, ty: 0 }, 2, 0, 0).scale, 3);
  assert.strictEqual(v.zoomAt({ scale: 0.06, tx: 0, ty: 0 }, 0.5, 0, 0).scale, 0.05);
});
test('legendEnds says how far the line runs in words', () => {
  assert.deepStrictEqual(v.legendEnds(1, 3), { old: '1 generation up', young: '3 generations down' });
  assert.deepStrictEqual(v.legendEnds(0, 0), { old: '', young: '' });
});

test('spanBar', () => {
  assert.deepStrictEqual(v.spanBar({ start: 1900.5, end: 1980.5, open: null }, 2026.9), { from: 1900.5, to: 1980.5, fade: false });
  assert.deepStrictEqual(v.spanBar({ start: 1990.5, end: null, open: 'living' }, 2026.9), { from: 1990.5, to: 2026.9, fade: false });
  assert.deepStrictEqual(v.spanBar({ start: 1850.5, end: null, open: 'unknown' }, 2026.9), { from: 1850.5, to: 1858.5, fade: true });
  assert.deepStrictEqual(v.spanBar({ start: 2024.5, end: null, open: 'unknown' }, 2026.9), { from: 2024.5, to: 2026.9, fade: true });
  assert.strictEqual(v.spanBar({ start: null, end: 1970.5, open: null }, 2026.9), null);
});
test('barRect never has a negative or invisible width', () => {
  assert.deepStrictEqual(v.barRect({ from: 1900, to: 1950 }, 1800, 10), { x: 1000, w: 500 });
  assert.deepStrictEqual(v.barRect({ from: 1950, to: 1900 }, 1800, 10), { x: 1500, w: 2 });
  assert.deepStrictEqual(v.barRect({ from: 1950, to: 1950 }, 1800, 10), { x: 1500, w: 2 });
});
test('axisBounds starts on a decade and ends next year', () => {
  assert.deepStrictEqual(v.axisBounds(1843, 2026.9), { min: 1830, max: 2027 });
  assert.deepStrictEqual(v.axisBounds(null, 2026.9), { min: 1926, max: 2027 });
});
test('rowWindow keeps five rows of overscan', () => {
  assert.deepStrictEqual(v.rowWindow(0, 300, 30, 100), { first: 0, last: 15 });
  assert.deepStrictEqual(v.rowWindow(600, 300, 30, 100), { first: 15, last: 35 });
  assert.deepStrictEqual(v.rowWindow(0, 300, 30, 4), { first: 0, last: 4 });
});

test('nodeTextBox makes room for a portrait', () => {
  const n = { x: 100, y: 0, w: 160, h: 64 };
  assert.deepStrictEqual(v.nodeTextBox(n, false), { x: 180, anchor: 'middle', width: 140 });
  assert.deepStrictEqual(v.nodeTextBox(n, true), { x: 154, anchor: 'start', width: 98 });
});

test('wheelPixels turns lines and pages into pixels', () => {
  assert.strictEqual(v.wheelPixels(120, 0, 800), 120);
  assert.strictEqual(v.wheelPixels(3, 1, 800), 120);
  assert.strictEqual(v.wheelPixels(-1, 2, 800), -800);
});
