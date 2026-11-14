const test = require('node:test');
const assert = require('node:assert');
const s = require('../../src/cronicl/site/viewer/site.js');

test('fold lowercases and strips accents', () => { assert.strictEqual(s.fold('Köhler  Ÿ'), 'kohler  y'); });
test('matches needs every word, in any order, as plain text', () => {
  assert.ok(s.matches('dunn hilda', 'Hilda Rosalind Dunn 1928–2019 dunn-hilda-rosalind'));
  assert.ok(s.matches('KOHLER', 'Esperanza Louisa Köhler'));
  assert.ok(!s.matches('dunn zzz', 'Hilda Rosalind Dunn'));
  assert.ok(s.matches('', 'anything'));
  assert.ok(!s.matches('.*', 'Hilda') && s.matches('(a', 'x (a) y'));
});
test('todayKey is month-day with leading zeros', () => { assert.strictEqual(s.todayKey(new Date(2026, 0, 5)), '01-05'); });

test('viewerId prefers a known "me", forgets an unknown one, survives a broken store', () => {
  const people = { a: {}, h: {} };
  const store = (v) => ({ v, getItem() { return this.v; }, removeItem() { this.v = null; } });
  assert.deepStrictEqual(s.viewerId(store('a'), people, 'h'), { id: 'a', mine: true });
  const stale = store('gone');
  assert.deepStrictEqual(s.viewerId(stale, people, 'h'), { id: 'h', mine: false });
  assert.strictEqual(stale.v, null);
  assert.deepStrictEqual(s.viewerId({ getItem() { throw new Error('denied'); } }, people, 'h'), { id: 'h', mine: false });
  assert.deepStrictEqual(s.viewerId(store(null), people, ''), { id: null, mine: false });
});
