const test = require('node:test');
const assert = require('node:assert');
const s = require('../../src/famsite/viewer/site.js');

test('fold lowercases and strips accents', () => { assert.strictEqual(s.fold('Köhler  Ÿ'), 'kohler  y'); });
test('matches needs every word, in any order, as plain text', () => {
  assert.ok(s.matches('dunn hilda', 'Hilda Rosalind Dunn 1928–2019 dunn-hilda-rosalind'));
  assert.ok(s.matches('KOHLER', 'Esperanza Louisa Köhler'));
  assert.ok(!s.matches('dunn zzz', 'Hilda Rosalind Dunn'));
  assert.ok(s.matches('', 'anything'));
  assert.ok(!s.matches('.*', 'Hilda') && s.matches('(a', 'x (a) y'));
});
test('todayKey is month-day with leading zeros', () => { assert.strictEqual(s.todayKey(new Date(2026, 0, 5)), '01-05'); });
