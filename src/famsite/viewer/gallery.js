(function (root) {
  'use strict';

  // Photos of a person from an external gallery, fetched in the visitor's browser. Everything the gallery host
  // sends is untrusted: it is only ever used through DOM properties, and every address must stay under the
  // gallery's own address.

  var TIMEOUT_MS = 5000;
  var MAX_PHOTOS = 6;
  var SPECIAL = { 'ß': 'ss', 'æ': 'ae', 'œ': 'oe', 'ø': 'o', 'đ': 'd', 'ł': 'l', 'þ': 'th' };

  // An http(s) address with no credentials, query, fragment or whitespace, ending in exactly one slash; else null.
  // It is the canonical form (lower-case host, default port dropped, escaped path), because confine compares
  // against addresses the browser has canonicalised.
  function normalizeBase(url) {
    if (typeof url !== 'string' || /[\s\\?#]/.test(url)) return null;
    var parsed;
    try { parsed = new URL(url); } catch (e) { return null; }
    if ((parsed.protocol !== 'http:' && parsed.protocol !== 'https:') || parsed.username || parsed.password) return null;
    return parsed.origin + parsed.pathname.replace(/\/+$/, '') + '/';
  }

  // The absolute address of ref under base, or null when ref could point anywhere else.
  function confine(base, ref) {
    if (typeof ref !== 'string' || ref === '') return null;
    if (/^[a-z][a-z0-9+.-]*:/i.test(ref) || ref.indexOf('//') === 0 || ref.indexOf('\\') !== -1) return null;
    if (ref.split(/[?#]/)[0].split('/').indexOf('..') !== -1) return null;
    var href;
    try { href = new URL(ref, base).href; } catch (e) { return null; }
    return href.indexOf(base) === 0 ? href : null;
  }

  var NON_ASCII_LETTER;
  try { NON_ASCII_LETTER = new RegExp('(?![\\x00-\\x7f])\\p{L}', 'u'); } catch (e) { NON_ASCII_LETTER = /[^\x00-\x7f]/; }

  // Lower-case words without accents, so "Zoë  Müller" and "zoe muller" compare equal. A name with a letter
  // that cannot be folded ("Иван Smith") folds to '' so it never matches by name: the rest of it
  // could match someone else.
  function fold(text) {
    var lowered = String(text == null ? '' : text).toLowerCase().replace(/[ßæœøđłþ]/g, function (c) { return SPECIAL[c]; });
    var plain = lowered.normalize('NFD').replace(/[̀-ͯ]/g, '');
    if (NON_ASCII_LETTER.test(plain)) return '';
    return plain.replace(/[^a-z0-9]+/g, ' ').trim();
  }

  function isObject(value) { return value !== null && typeof value === 'object'; }

  // The gallery's entry for a person: by slug; else, unless the id was set by hand, by the one entry with the same name.
  function pickEntry(people, key, explicit, name) {
    var entries = (people || []).filter(isObject);
    for (var i = 0; i < entries.length; i++) if (entries[i].slug === key) return entries[i];
    if (explicit) return null;
    var wanted = fold(name);
    if (!wanted) return null;
    var same = entries.filter(function (entry) { return fold(entry.name) === wanted; });
    return same.length === 1 ? same[0] : null;
  }

  // What the page shows, or null when there is nothing safe and worth showing.
  function shape(base, entry, cap) {
    if (!isObject(entry)) return null;
    var count = entry.count;
    if (typeof count !== 'number' || !isFinite(count) || Math.floor(count) !== count || count < 1) return null;
    var seeAllHref = confine(base, entry.url);
    if (!seeAllHref || !Array.isArray(entry.photos)) return null;
    var limit = cap || MAX_PHOTOS, photos = [];
    for (var i = 0; i < entry.photos.length && photos.length < limit; i++) {
      var p = entry.photos[i];
      if (!isObject(p) || typeof p.name !== 'string') continue;
      var thumbSrc = confine(base, p.thumb), href = confine(base, p.url);
      if (thumbSrc && href) photos.push({ name: p.name, thumbSrc: thumbSrc, href: href });
    }
    if (!photos.length) return null;
    return { count: Math.max(count, photos.length), photos: photos, seeAllHref: seeAllHref };
  }

  function withTimeout(start, deps) {
    return new Promise(function (resolve, reject) {
      var controller = typeof AbortController !== 'undefined' ? new AbortController() : null;
      var timer = deps.setTimeout(function () {
        if (controller) controller.abort();
        reject(new Error('timeout'));
      }, TIMEOUT_MS);
      var done = function (settle) { return function (value) { deps.clearTimeout(timer); settle(value); }; };
      try {
        start(controller ? controller.signal : undefined).then(done(resolve), done(reject));
      } catch (e) {
        done(reject)(e);
      }
    });
  }

  var ADAPTERS = {
    fussel: function (config, person, deps) {
      var base = normalizeBase(config.url);
      if (!base) return Promise.resolve(null);
      return withTimeout(function (signal) {
        var options = { credentials: 'omit' };
        if (signal) options.signal = signal;
        return Promise.resolve(deps.fetch(base + 'people.json', options)).then(function (response) {
          if (!response || !response.ok) throw new Error('bad status');
          return response.json();
        });
      }, deps).then(function (data) {
        if (!isObject(data) || data.version !== 1 || !Array.isArray(data.people)) return null;
        return shape(base, pickEntry(data.people, person.key, person.explicit, person.name));
      });
    }
  };

  // Resolves to the shape for a person, or null for anything that goes wrong. Never rejects.
  function load(config, person, deps) {
    deps = deps || {};
    var d = {
      fetch: deps.fetch || (root.fetch ? root.fetch.bind(root) : null),
      setTimeout: deps.setTimeout || root.setTimeout.bind(root),
      clearTimeout: deps.clearTimeout || root.clearTimeout.bind(root)
    };
    var adapter = isObject(config) ? ADAPTERS[config.type] : null;
    if (!adapter || !d.fetch) return Promise.resolve(null);
    try {
      return Promise.resolve(adapter(config, person, d)).then(function (result) { return result || null; }, function () { return null; });
    } catch (e) {
      return Promise.resolve(null);
    }
  }

  function render(section, shaped, doc) {
    var list = section.querySelector('.gallery-thumbs');
    shaped.photos.forEach(function (photo) {
      var item = doc.createElement('li');
      var link = doc.createElement('a');
      link.setAttribute('href', photo.href);
      link.setAttribute('target', '_blank');
      link.setAttribute('rel', 'noopener');
      var img = doc.createElement('img');
      img.setAttribute('src', photo.thumbSrc);
      img.setAttribute('alt', photo.name);
      img.setAttribute('loading', 'lazy');
      link.appendChild(img);
      item.appendChild(link);
      list.appendChild(item);
    });
    var more = section.querySelector('.gallery-more a');
    more.setAttribute('href', shaped.seeAllHref);
    more.setAttribute('target', '_blank');
    more.setAttribute('rel', 'noopener');
    more.textContent = shaped.count === 1 ? 'See the photo in the gallery' : 'See all ' + shaped.count + ' photos in the gallery';
    section.hidden = false;
  }

  function init(doc, deps) {
    try {
      var section = doc.getElementById('gallery');
      if (!section || !section.dataset || !section.dataset.galleryType) return Promise.resolve();
      var data = section.dataset;
      return load({ type: data.galleryType, url: data.galleryUrl },
        { key: data.galleryKey, explicit: data.galleryExplicit === '1', name: data.galleryName }, deps)
        .then(function (shaped) { if (shaped) render(section, shaped, doc); })
        .then(null, function () { /* a broken block must never break the page */ });
    } catch (e) {
      return Promise.resolve();
    }
  }

  var api = {
    normalizeBase: normalizeBase, confine: confine, fold: fold, pickEntry: pickEntry, shape: shape,
    load: load, render: render, init: init, ADAPTERS: ADAPTERS
  };
  if (typeof module !== 'undefined' && module.exports) {
    module.exports = api;
  } else {
    root.famsiteGallery = api;
    if (root.document) {
      if (root.document.readyState === 'loading') root.document.addEventListener('DOMContentLoaded', function () { init(root.document); });
      else init(root.document);
    }
  }
})(typeof window !== 'undefined' ? window : this);
