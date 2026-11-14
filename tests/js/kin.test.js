const test = require('node:test');
const assert = require('node:assert');
const k = require('../../src/cronicl/site/viewer/kin.js');

const person = (sex, parents, partners) => ({ name: '', sex: sex || 'U', parents: parents || [], partners: partners || [] });
const P = {
  gg: person('F'), g1: person('M', ['gg'], ['g2']), g2: person('F', [], ['g1']),
  dad: person('M', ['g1', 'g2'], ['mum']), mum: person('F', [], ['dad']), other: person('F'),
  aunt: person('F', ['g1', 'g2'], ['unc']), unc: person('M', [], ['aunt']),
  me: person('U', ['dad', 'mum'], ['sp']), sis: person('F', ['dad', 'mum']),
  half: person('M', ['dad', 'other']), solo: person('U', ['dad']),
  cuz: person('U', ['aunt', 'unc']), cuzkid: person('U', ['cuz']),
  sp: person('U', ['spdad'], ['me']), spdad: person('M'), kid: person('F', ['me', 'sp']),
  stranger: person('U'),
};
const label = (a, b) => k.kinship(P, a, b).label;

test('direct line', () => {
  assert.deepStrictEqual(k.kinship(P, 'me', 'me'), { label: 'self', up: 0, down: 0, by: 'self' });
  assert.deepStrictEqual(k.kinship(P, 'me', 'g1'), { label: 'grandfather', up: 2, down: 0, by: 'blood' });
  assert.deepStrictEqual(['dad', 'mum', 'gg', 'kid'].map((b) => label('me', b)), ['father', 'mother', 'great-grandmother', 'daughter']);
  assert.strictEqual(label('gg', 'kid'), 'great-great-granddaughter');
  assert.strictEqual(label('dad', 'me'), 'child');
});
test('beyond great-great the greats are counted', () => {
  const chain = {};
  for (let i = 0; i < 7; i++) chain['a' + i] = person('U', i < 6 ? ['a' + (i + 1)] : []);
  assert.strictEqual(k.kinship(chain, 'a0', 'a5').label, '3× great-grandparent');
  assert.strictEqual(k.kinship(chain, 'a6', 'a0').label, '4× great-grandchild');
});
test('siblings', () => {
  assert.deepStrictEqual(['sis', 'half', 'solo'].map((b) => label('me', b)), ['sister', 'half-brother', 'sibling']);
});
test('aunts, nieces and cousins', () => {
  assert.strictEqual(label('me', 'aunt'), 'aunt');
  assert.strictEqual(label('aunt', 'me'), 'niece or nephew');
  assert.strictEqual(label('kid', 'aunt'), 'great-aunt');
  assert.strictEqual(label('aunt', 'kid'), 'great-niece');
  assert.strictEqual(label('me', 'cuz'), 'first cousin');
  assert.strictEqual(label('me', 'cuzkid'), 'first cousin once removed');
  assert.strictEqual(label('kid', 'cuzkid'), 'second cousin');
  assert.deepStrictEqual(k.kinship(P, 'kid', 'cuz'), { label: 'first cousin once removed', up: 3, down: 2, by: 'blood' });
});
test('by partnership', () => {
  assert.deepStrictEqual(k.kinship(P, 'me', 'sp'), { label: 'partner', up: null, down: null, by: 'partner' });
  assert.strictEqual(label('me', 'spdad'), "partner's father");
  assert.strictEqual(label('me', 'unc'), "aunt's partner");
  assert.strictEqual(k.kinship(P, 'me', 'unc').by, 'in-law');
});
test('no relationship, unknown ids and cycles', () => {
  assert.deepStrictEqual(k.kinship(P, 'me', 'stranger'), { label: null, up: null, down: null, by: null });
  assert.strictEqual(k.kinship(P, 'me', 'nobody').label, null);
  const loop = { x: person('U', ['y']), y: person('U', ['x']), z: person('U') };
  assert.strictEqual(k.kinship(loop, 'x', 'z').label, null);
});
test('the closest blood relation wins over a partnership route', () => {
  const Q = Object.assign({}, P, { cuz: person('U', ['aunt', 'unc'], ['me']), me: person('U', ['dad', 'mum'], ['cuz']) });
  assert.strictEqual(k.kinship(Q, 'me', 'cuz').label, 'first cousin');
});

test('phrase', () => {
  const gm = { label: 'grandmother', by: 'blood' };
  assert.strictEqual(k.phrase(gm, 'Nora Hollings', true), 'Your grandmother');
  assert.strictEqual(k.phrase(gm, 'Nora Hollings', false), "Nora Hollings's grandmother");
  assert.strictEqual(k.phrase({ label: "partner's father", by: 'in-law' }, 'Nora', true), "Your partner's father");
  assert.strictEqual(k.phrase({ label: 'self', by: 'self' }, 'Nora', true), 'This is you');
  assert.strictEqual(k.phrase({ label: 'self', by: 'self' }, 'Nora', false), '');
  assert.strictEqual(k.phrase({ label: null, by: null }, 'Nora', true), '');
});
test('sentence', () => {
  const N = { a: { name: 'Amy Smith', sex: 'F', parents: ['b'], partners: [] }, b: { name: 'Bob Smith', sex: 'M', parents: [], partners: [] }, c: { name: 'Cy', sex: 'U', parents: [], partners: [] } };
  assert.strictEqual(k.sentence(N, 'a', 'b'), "Bob Smith is Amy Smith's father.");
  assert.strictEqual(k.sentence(N, 'a', 'a'), 'That is the same person.');
  assert.strictEqual(k.sentence(N, 'a', 'c'), 'No recorded relationship between Amy Smith and Cy.');
});
