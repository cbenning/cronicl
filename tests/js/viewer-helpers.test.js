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
});

test('routeHash round-trips', () => {
  assert.strictEqual(v.routeHash('timeline', 'a-b'), '#/timeline/a-b');
  assert.strictEqual(v.routeHash('tree', null), '#/tree');
});

const timeline = {
  events: [
    { id: 'birth:p1', type: 'birth', year: 1920, month: null, day: null, people: ['p1'] },
    { id: 'marriage:p1+p2', type: 'marriage', year: 1948, month: 6, day: 20, people: ['p1', 'p2'] },
    { id: 'birth:c1', type: 'birth', year: 1950, month: null, day: null, people: ['c1'] },
    { id: 'death:p1', type: 'death', year: 1990, month: null, day: null, people: ['p1'] },
    { id: 'death:s1', type: 'death', year: 1995, month: null, day: null, people: ['s1'] },
    { id: 'birth:x', type: 'birth', year: 1960, month: null, day: null, people: ['x'] },
    { id: 'death:par', type: 'death', year: 1970, month: null, day: null, people: ['par'] },
  ],
  people: {
    p1: { name: 'John', parents: ['par'], spouses: ['p2'], children: ['c1'], siblings: ['s1'] },
    p2: { name: 'Mary', parents: [], spouses: ['p1'], children: ['c1'], siblings: [] },
    c1: { name: 'Bob', parents: ['p1', 'p2'], spouses: [], children: [], siblings: [] },
    s1: { name: 'Sib', parents: ['par'], spouses: [], children: [], siblings: ['p1'] },
    par: { name: 'Parent', parents: [], spouses: [], children: ['p1', 's1'], siblings: [] },
    x: { name: 'Stranger', parents: [], spouses: [], children: [], siblings: [] },
  },
};

test('personTimelineEvents includes own events and relatives in the right roles', () => {
  const got = v.personTimelineEvents(timeline, 'p1').map((r) => r.event.id + ':' + r.role);
  assert.deepStrictEqual(got, [
    'birth:p1:self',
    'marriage:p1+p2:self',
    'birth:c1:child',
    'death:p1:self',
    'death:s1:sibling',
    'death:par:parent',
  ].sort((a, b) => timeline.events.findIndex((e) => a.startsWith(e.id)) - timeline.events.findIndex((e) => b.startsWith(e.id))));
});

test('personTimelineEvents excludes strangers and returns null for an unknown person', () => {
  const ids = v.personTimelineEvents(timeline, 'p1').map((r) => r.event.id);
  assert.ok(!ids.includes('birth:x'));
  assert.strictEqual(v.personTimelineEvents(timeline, 'nobody'), null);
});

test('eventText reads naturally from a person focus and from the family view', () => {
  const ev = timeline.events;
  assert.strictEqual(v.eventText(ev[0], timeline.people, 'p1'), 'born');
  assert.strictEqual(v.eventText(ev[0], timeline.people, null), 'John born');
  assert.strictEqual(v.eventText(ev[1], timeline.people, 'p1'), 'married Mary');
  assert.strictEqual(v.eventText(ev[1], timeline.people, null), 'John & Mary married');
  assert.strictEqual(v.eventText(ev[4], timeline.people, 'p1'), 'Sib died');
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

test('relatedFor lights up the parents line, own couples and children, not siblings', () => {
  const r = v.relatedFor(fam, 'c');
  assert.deepStrictEqual([...r.people].sort(), ['a', 'b', 'e', 'x']);
  assert.deepStrictEqual([...r.edges].sort((m, n) => m - n), [0, 1, 2, 4, 5, 6]);
  assert.ok(!r.edges.has(3), "sibling d's connector is not highlighted");
  assert.deepStrictEqual([...r.unions].sort(), ['a+b', 'c+x']);
});

test('relatedFor works for a child with one known parent', () => {
  const r = v.relatedFor(fam, 'k');
  assert.deepStrictEqual([...r.people], ['solo']);
  assert.deepStrictEqual([...r.edges], [7]);
});

test('relatedFor of an unconnected person highlights nothing', () => {
  const r = v.relatedFor(fam, 'nobody');
  assert.strictEqual(r.edges.size, 0);
  assert.strictEqual(r.people.size, 0);
});
