(function (root) {
  'use strict';

  // Lower-case and strip accents so "Köhler" and "KOHLER" are the same word.
  function fold(text) {
    return String(text == null ? '' : text).normalize('NFD').replace(/[̀-ͯ]/g, '').toLowerCase();
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

  var api = { fold: fold, matches: matches, todayKey: todayKey };
  if (typeof module !== 'undefined' && module.exports) {
    module.exports = api;
  } else if (typeof document !== 'undefined') {
    root.famsiteSite = api;
    if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init);
    else init();
  }
})(typeof window !== 'undefined' ? window : this);
