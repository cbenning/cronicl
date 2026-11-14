(function (root) {
  'use strict';

  // Lower-case and strip accents so "Köhler" and "KOHLER" are the same word.
  function fold(text) {
    return String(text == null ? '' : text).normalize('NFD').replace(/[\u0300-\u036f]/g, '').toLowerCase();
  }

  // Every word of the query must appear in the text, in any order. Plain substrings only: no pattern syntax.
  function matches(query, text) {
    var words = fold(query).split(/\s+/).filter(Boolean);
    var haystack = fold(text);
    return words.every(function (word) { return haystack.indexOf(word) !== -1; });
  }

  function todayKey(date) {
    var m = date.getMonth() + 1, d = date.getDate();
    return (m < 10 ? '0' : '') + m + '-' + (d < 10 ? '0' : '') + d;
  }

  var ME_KEY = 'cronicl.me';

  // Who is looking: the person the visitor said is them, else the home person. A saved id that is no longer in
  // the site is forgotten; a store that throws (private mode) is treated as empty.
  function viewerId(storage, people, home) {
    var saved = null;
    try { saved = storage ? storage.getItem(ME_KEY) : null; } catch (e) { saved = null; }
    if (saved) {
      if (people[saved]) return { id: saved, mine: true };
      try { storage.removeItem(ME_KEY); } catch (e) { /* nothing to forget */ }
    }
    if (home && people[home]) return { id: home, mine: false };
    return { id: null, mine: false };
  }

  function localStore() {
    try {
      var store = root.localStorage;
      store.getItem(ME_KEY);
      return store;
    } catch (e) { return null; }
  }

  function metaContent(name) {
    var el = document.querySelector('meta[name="' + name + '"]');
    return el ? el.getAttribute('content') || '' : '';
  }

  // The kinship line and the "This is me" button on a person page.
  function initKin(line) {
    var id = line.getAttribute('data-kin-for');
    var base = metaContent('cronicl-root');
    var home = metaContent('cronicl-home');
    var button = document.getElementById('set-me');
    var kin = root.croniclKin;
    if (!kin) return;
    fetch(base + 'kin.json').then(function (r) { return r.json(); }).then(function (data) {
      var people = data.people;
      var store = localStore();
      function render() {
        var who = viewerId(store, people, home);
        var text = who.id ? kin.phrase(kin.kinship(people, who.id, id), people[who.id].name, who.mine) : '';
        line.textContent = text;
        line.hidden = !text;
        if (button) {
          var saved = who.mine && who.id === id;
          button.textContent = saved ? 'This is you · undo' : 'This is me';
        }
      }
      if (button && store) {
        button.hidden = false;
        button.addEventListener('click', function () {
          try {
            if (store.getItem(ME_KEY) === id) store.removeItem(ME_KEY);
            else store.setItem(ME_KEY, id);
          } catch (e) { return; }
          render();
        });
      }
      render();
    }).catch(function () { /* the page is complete without the line */ });
  }

  function queryValue(search, name) {
    var found = new RegExp('[?&]' + name + '=([^&]*)').exec(search || '');
    if (!found) return '';
    try { return decodeURIComponent(found[1].replace(/\+/g, ' ')); } catch (e) { return found[1]; }
  }

  // The relate page: two pickers and one sentence.
  function initRelate(selectA, selectB) {
    var answer = document.getElementById('relate-answer');
    var base = metaContent('cronicl-root');
    var home = metaContent('cronicl-home');
    var kin = root.croniclKin;
    if (!kin) return;
    fetch(base + 'kin.json').then(function (r) { return r.json(); }).then(function (data) {
      var people = data.people;
      var who = viewerId(localStore(), people, home);
      var a = queryValue(location.search, 'a') || who.id;
      var b = queryValue(location.search, 'b');
      if (a && people[a]) selectA.value = a;
      if (b && people[b]) selectB.value = b;
      function render() {
        answer.textContent = kin.sentence(people, selectA.value, selectB.value);
        try {
          history.replaceState(null, '', '?a=' + encodeURIComponent(selectA.value) + '&b=' + encodeURIComponent(selectB.value));
        } catch (e) { /* the answer still shows */ }
      }
      selectA.addEventListener('change', render);
      selectB.addEventListener('change', render);
      render();
    }).catch(function () { /* the page says it needs scripts */ });
  }

  function queryParam(search) {
    var found = /[?&]q=([^&]*)/.exec(search || '');
    if (!found) return '';
    try { return decodeURIComponent(found[1].replace(/\+/g, ' ')); } catch (e) { return found[1]; }
  }

  function init() {
    var section = document.getElementById('on-this-day');
    if (section) {
      var key = todayKey(new Date());
      var any = false;
      Array.prototype.forEach.call(section.querySelectorAll('li[data-md]'), function (li) {
        if (li.getAttribute('data-md') === key) {
          li.hidden = false;
          any = true;
        }
      });
      section.hidden = !any;
    }
    var relateA = document.getElementById('relate-a');
    if (relateA) initRelate(relateA, document.getElementById('relate-b'));
    var kinLine = document.querySelector('[data-kin-for]');
    if (kinLine) initKin(kinLine);
    var people = Array.prototype.slice.call(document.querySelectorAll('[data-person]'));
    if (!people.length) return;
    var input = document.querySelector('.site-search input');
    var groups = Array.prototype.slice.call(document.querySelectorAll('[data-group]'));
    var none = document.getElementById('no-match');
    function filter() {
      var query = input ? input.value : '';
      var shown = 0;
      people.forEach(function (li) {
        var ok = matches(query, li.getAttribute('data-text'));
        li.hidden = !ok;
        if (ok) shown += 1;
      });
      groups.forEach(function (g) { g.hidden = !g.querySelector('[data-person]:not([hidden])'); });
      if (none) none.hidden = shown > 0;
    }
    if (input) {
      input.value = queryParam(location.search);
      input.addEventListener('input', filter);
    }
    filter();
  }

  var api = { fold: fold, matches: matches, todayKey: todayKey, viewerId: viewerId };
  if (typeof module !== 'undefined' && module.exports) {
    module.exports = api;
  } else if (typeof document !== 'undefined') {
    root.croniclSite = api;
    if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init);
    else init();
  }
})(typeof window !== 'undefined' ? window : this);
