const test = require('node:test');
const assert = require('node:assert');
const { buildGrid, queryGrid, boundsOf } = require('../../src/cronicl/viewer/viewer.js');

test('queryGrid returns only items intersecting the view', () => {
  const grid = buildGrid(
    [
      { id: 'a', x: 0, y: 0, w: 10, h: 10 },
      { id: 'b', x: 5000, y: 5000, w: 10, h: 10 },
      { id: 'wide', x: 0, y: 0, w: 4000, h: 10 },
    ],
    256
  );
  const hit = queryGrid(grid, { x: -5, y: -5, w: 100, h: 100 });
  assert.ok(hit.has('a'));
  assert.ok(hit.has('wide'));
  assert.ok(!hit.has('b'));
});

test('items spanning several cells are found from any of them', () => {
  const grid = buildGrid([{ id: 'wide', x: 0, y: 0, w: 4000, h: 10 }], 256);
  assert.ok(queryGrid(grid, { x: 3500, y: 0, w: 10, h: 10 }).has('wide'));
});

test('empty view far away returns nothing', () => {
  const grid = buildGrid([{ id: 'a', x: 0, y: 0, w: 10, h: 10 }], 256);
  assert.strictEqual(queryGrid(grid, { x: 9000, y: 9000, w: 10, h: 10 }).size, 0);
});

test('boundsOf computes the box around points', () => {
  assert.deepStrictEqual(boundsOf([[10, 20], [30, 5], [15, 40]]), { x: 10, y: 5, w: 20, h: 35 });
});
