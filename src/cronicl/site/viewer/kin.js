(function (root) {
  'use strict';

  var ORDINALS = ['first', 'second', 'third', 'fourth', 'fifth', 'sixth', 'seventh', 'eighth', 'ninth', 'tenth'];

  function sexed(sex, male, female, neutral) {
    return sex === 'M' ? male : sex === 'F' ? female : neutral;
  }

  // "", "great-", "great-great-", then "3× great-".
  function greats(n) {
    if (n <= 0) return '';
    if (n === 1) return 'great-';
    if (n === 2) return 'great-great-';
    return n + '× great-';
  }

  // Ancestors of `id` (and `id` itself at 0) with the shortest number of generations up. Cycle-safe.
  function ancestors(people, id) {
    var depth = {};
    depth[id] = 0;
    var level = [id];
    var n = 0;
    while (level.length) {
      n += 1;
      var next = [];
      level.forEach(function (pid) {
        ((people[pid] && people[pid].parents) || []).forEach(function (parent) {
          if (people[parent] && depth[parent] === undefined) {
            depth[parent] = n;
            next.push(parent);
          }
        });
      });
      level = next;
    }
    return depth;
  }

  // The closest common ancestor route from a to b: fewest generations in total, then fewest up from a.
  function blood(people, a, b) {
    var fromA = ancestors(people, a), fromB = ancestors(people, b);
    var best = null;
    Object.keys(fromA).sort().forEach(function (id) {
      if (fromB[id] === undefined) return;
      var u = fromA[id], d = fromB[id];
      if (!best || u + d < best.up + best.down || (u + d === best.up + best.down && u < best.up)) best = { up: u, down: d };
    });
    return best;
  }

  function sharedParents(people, a, b) {
    var pa = people[a].parents || [], pb = people[b].parents || [];
    return pa.filter(function (p) { return pb.indexOf(p) !== -1; }).length;
  }

  function bloodLabel(people, a, b, up, down) {
    var sex = people[b].sex;
    if (up === 0 && down === 0) return 'self';
    if (down === 0) return greats(up - 2) + (up === 1 ? '' : 'grand') + sexed(sex, 'father', 'mother', 'parent');
    if (up === 0) return greats(down - 2) + (down === 1 ? '' : 'grand') + sexed(sex, 'son', 'daughter', 'child');
    if (up === 1 && down === 1) {
      var half = sharedParents(people, a, b) === 1 && people[a].parents.length === 2 && people[b].parents.length === 2;
      return (half ? 'half-' : '') + sexed(sex, 'brother', 'sister', 'sibling');
    }
    if (down === 1) return greats(up - 2) + sexed(sex, 'uncle', 'aunt', 'aunt or uncle');
    if (up === 1) return greats(down - 2) + sexed(sex, 'nephew', 'niece', 'niece or nephew');
    var degree = Math.min(up, down) - 1;
    var removed = Math.abs(up - down);
    var text = (degree <= ORDINALS.length ? ORDINALS[degree - 1] : degree + 'th') + ' cousin';
    if (removed === 1) text += ' once removed';
    else if (removed === 2) text += ' twice removed';
    else if (removed > 2) text += ' ' + removed + ' times removed';
    return text;
  }

  function none() { return { label: null, up: null, down: null, by: null }; }

  // How b is related to a, told from a's side. `people` is the `people` object of kin.json.
  function kinship(people, a, b) {
    if (!people[a] || !people[b]) return none();
    if (a === b) return { label: 'self', up: 0, down: 0, by: 'self' };
    var direct = blood(people, a, b);
    if (direct) {
      return { label: bloodLabel(people, a, b, direct.up, direct.down), up: direct.up, down: direct.down, by: 'blood' };
    }
    var partnersOfA = people[a].partners || [];
    if (partnersOfA.indexOf(b) !== -1) return { label: 'partner', up: null, down: null, by: 'partner' };
    var found = null;
    partnersOfA.forEach(function (p) {
      var via = people[p] ? blood(people, p, b) : null;
      if (via && (!found || via.up + via.down < found.size)) {
        found = { label: "partner's " + bloodLabel(people, p, b, via.up, via.down), size: via.up + via.down };
      }
    });
    if (found) return { label: found.label, up: null, down: null, by: 'in-law' };
    (people[b].partners || []).forEach(function (q) {
      var via = people[q] ? blood(people, a, q) : null;
      if (via && (!found || via.up + via.down < found.size)) {
        found = { label: bloodLabel(people, a, q, via.up, via.down) + "'s partner", size: via.up + via.down };
      }
    });
    if (found) return { label: found.label, up: null, down: null, by: 'in-law' };
    return none();
  }

  // The line shown on a person's page: "Your grandmother". The site shows it only once the viewer has said who they
  // are; `mine` false (naming the viewer) is for a caller that knows someone else's reference person.
  function phrase(result, viewerName, mine) {
    if (!result || !result.label) return '';
    if (result.by === 'self') return mine ? 'This is you' : '';
    return (mine ? 'Your' : viewerName + "'s") + ' ' + result.label;
  }

  // The relate page's answer about two chosen people.
  function sentence(people, a, b) {
    if (!people[a] || !people[b]) return '';
    if (a === b) return 'That is the same person.';
    var nameA = people[a].name || a, nameB = people[b].name || b;
    var result = kinship(people, a, b);
    if (!result.label) return 'No recorded relationship between ' + nameA + ' and ' + nameB + '.';
    return nameB + ' is ' + nameA + "'s " + result.label + '.';
  }

  var api = { kinship: kinship, phrase: phrase, sentence: sentence };
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
  else root.croniclKin = api;
})(typeof window !== 'undefined' ? window : this);
