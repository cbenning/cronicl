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

test('packLanes puts overlapping items in different lanes and reuses free lanes', () => {
  const lanes = v.packLanes(
    [
      { start: 0, end: 100 },
      { start: 50, end: 150 },
      { start: 120, end: 200 },
      { start: 300, end: 400 },
    ],
    10
  );
  assert.deepStrictEqual(lanes, [0, 1, 0, 0]);
});

test('packLanes respects the gap between neighbours', () => {
  const lanes = v.packLanes([{ start: 0, end: 100 }, { start: 105, end: 200 }], 10);
  assert.deepStrictEqual(lanes, [0, 1]);
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

test('familyIndex is stable, in range, and spreads different couples over several colours', () => {
  assert.strictEqual(v.familyIndex('a+b', 8), v.familyIndex('a+b', 8));
  const seen = new Set();
  for (let i = 0; i < 40; i++) {
    const k = v.familyIndex('person-' + i + '+other-' + i, 8);
    assert.ok(k >= 0 && k < 8);
    seen.add(k);
  }
  assert.ok(seen.size >= 5, 'got ' + seen.size + ' distinct colours');
});

test('visibleRange converts the pan/zoom state to a year span', () => {
  // 10 px per year, year 1900 at x=40, 1000px wide
  const r = v.visibleRange(40, 10, 1900, 1000);
  assert.strictEqual(r.from, 1896);
  assert.strictEqual(r.to, 1996);
});

test('thumbGeometry sizes and places the scrollbar thumb', () => {
  const g = v.thumbGeometry({ min: 1900, max: 2000 }, { from: 1950, to: 1975 });
  assert.strictEqual(g.left, 0.5);
  assert.strictEqual(g.width, 0.25);
});

test('thumbGeometry clamps to the track and keeps a grabbable minimum', () => {
  const wide = v.thumbGeometry({ min: 1900, max: 2000 }, { from: 1800, to: 2100 });
  assert.deepStrictEqual(wide, { left: 0, width: 1 });
  const tiny = v.thumbGeometry({ min: 1900, max: 2000 }, { from: 1990, to: 1990.1 });
  assert.ok(tiny.width >= 0.03);
  assert.ok(tiny.left + tiny.width <= 1);
});

test('relationNote names the shared parent of a half-sibling and nothing for others', () => {
  assert.strictEqual(
    v.relationNote({ type: 'half', via: [{ id: 'a', name: 'Alfred' }] }),
    'half-sibling via Alfred'
  );
  assert.strictEqual(v.relationNote({ type: 'half', via: [] }), 'half-sibling');
  assert.strictEqual(v.relationNote({ type: 'full', via: [{ id: 'a', name: 'A' }, { id: 'b', name: 'B' }] }), '');
  assert.strictEqual(v.relationNote({ type: 'sibling', via: [{ id: 'a', name: 'A' }] }), '');
  assert.strictEqual(v.relationNote({ id: 'x', name: 'X' }), '');
});
