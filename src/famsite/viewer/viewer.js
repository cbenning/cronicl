(function (root) {
  'use strict';

  var CELL = 256;

  // ------------------------------------------------------------------ pure helpers

  function boundsOf(points) {
    var minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity;
    points.forEach(function (p) {
      if (p[0] < minX) minX = p[0];
      if (p[0] > maxX) maxX = p[0];
      if (p[1] < minY) minY = p[1];
      if (p[1] > maxY) maxY = p[1];
    });
    return { x: minX, y: minY, w: maxX - minX, h: maxY - minY };
  }

  function buildGrid(items, cell) {
    var cells = new Map();
    items.forEach(function (item) {
      var x0 = Math.floor(item.x / cell), x1 = Math.floor((item.x + item.w) / cell);
      var y0 = Math.floor(item.y / cell), y1 = Math.floor((item.y + item.h) / cell);
      for (var cx = x0; cx <= x1; cx++) {
        for (var cy = y0; cy <= y1; cy++) {
          var key = cx + ',' + cy;
          if (!cells.has(key)) cells.set(key, []);
          cells.get(key).push(item.id);
        }
      }
    });
    return { cell: cell, cells: cells };
  }

  function queryGrid(grid, view) {
    var ids = new Set();
    var x0 = Math.floor(view.x / grid.cell), x1 = Math.floor((view.x + view.w) / grid.cell);
    var y0 = Math.floor(view.y / grid.cell), y1 = Math.floor((view.y + view.h) / grid.cell);
    for (var cx = x0; cx <= x1; cx++) {
      for (var cy = y0; cy <= y1; cy++) {
        var list = grid.cells.get(cx + ',' + cy);
        if (list) list.forEach(function (id) { ids.add(id); });
      }
    }
    return ids;
  }

  function ellipsize(text, maxWidth, measure) {
    var s = text;
    while (s.length > 1 && measure(s + '…') > maxWidth) s = s.slice(0, -1);
    return s.replace(/\s+$/, '') + '…';
  }

  // Break a name into at most maxLines lines that fit maxWidth; end with an ellipsis if it cannot.
  function wrapName(text, maxWidth, measure, maxLines) {
    maxLines = maxLines || 2;
    var words = String(text).split(/\s+/).filter(Boolean);
    if (!words.length) return { lines: [''], truncated: false };
    var lines = [];
    var current = '';
    words.forEach(function (word) {
      var candidate = current ? current + ' ' + word : word;
      if (current && measure(candidate) > maxWidth) {
        lines.push(current);
        current = word;
      } else {
        current = candidate;
      }
    });
    lines.push(current);
    var truncated = false;
    if (lines.length > maxLines) {
      truncated = true;
      var kept = lines.slice(0, maxLines);
      kept[maxLines - 1] = kept[maxLines - 1] + ' ' + lines.slice(maxLines).join(' ');
      lines = kept;
    }
    lines = lines.map(function (line, i) {
      if (truncated && i === lines.length - 1) return ellipsize(line, maxWidth, measure);
      if (measure(line) > maxWidth) {
        truncated = true;
        return ellipsize(line, maxWidth, measure);
      }
      return line;
    });
    return { lines: lines, truncated: truncated };
  }

  // Greedy interval packing: returns a lane index for each item so items in one lane never overlap.
  function parseRoute(hash) {
    var parts = String(hash || '').replace(/^#\/?/, '').split('/').filter(Boolean).map(decodeURIComponent);
    if (!parts.length) return { view: 'tree', id: null };
    if (parts[0] === 'tree' || parts[0] === 'timeline' || parts[0] === 'focus') {
      return { view: parts[0], id: parts[1] || null };
    }
    return { view: 'tree', id: parts[0] };
  }

  function routeHash(view, id) {
    return '#/' + view + (id ? '/' + encodeURIComponent(id) : '');
  }

  function yearPosition(ev) {
    if (ev.month) return ev.year + (ev.month - 1) / 12 + ((ev.day || 1) - 1) / 372;
    return ev.year + 0.5;
  }

  // What to light up for `id`, each part tagged with its relationship to them: parent, partner, child or sibling.
  // Returns Maps: people (id -> role, never `id` itself), edges (layout edge index -> role) and unions (id -> role).
  function relatedFor(layout, id) {
    var people = new Map(), edges = new Map(), unions = new Map();
    var members = {};
    (layout.unions || []).forEach(function (u) { members[u.id] = u.members || []; });
    var own = new Set();
    var birth = null;
    layout.edges.forEach(function (e) {
      if (e.kind === 'spouse' && e.from === id) own.add(e.to);
      if (e.kind === 'child' && e.to === id) birth = e.from;
    });
    (layout.unions || []).forEach(function (u) {
      if ((u.members || []).length === 1 && u.members[0] === id) own.add(u.id); // a lone parent has no spouse edge
    });
    function put(map, key, role) { if (!map.has(key)) map.set(key, role); }
    var parents = new Set();
    if (birth) {
      unions.set(birth, 'parent');
      (members[birth] || []).forEach(function (p) {
        if (p !== id) { put(people, p, 'parent'); parents.add(p); }
      });
    }
    // the unions that give this person half-siblings: other unions of their parents
    var halfUnions = new Set();
    Object.keys(members).forEach(function (uid) {
      if (uid !== birth && !own.has(uid) && members[uid].some(function (m) { return parents.has(m); })) halfUnions.add(uid);
    });
    own.forEach(function (uid) {
      put(unions, uid, 'partner');
      (members[uid] || []).forEach(function (m) { if (m !== id) put(people, m, 'partner'); });
    });
    layout.edges.forEach(function (e, i) {
      if (e.kind === 'spouse') {
        if (e.to === birth) put(edges, i, 'parent');
        else if (own.has(e.to)) put(edges, i, 'partner');
      } else if (e.kind === 'child') {
        if (e.from === birth) {
          if (e.to === id) put(edges, i, 'parent');
          else { put(edges, i, 'sibling'); put(people, e.to, 'sibling'); }
        } else if (own.has(e.from)) {
          put(edges, i, 'child');
          put(people, e.to, 'child');
        } else if (halfUnions.has(e.from) && e.to !== id) {
          put(edges, i, 'sibling');
          put(people, e.to, 'sibling');
        }
      }
    });
    people.delete(id);
    return { people: people, edges: edges, unions: unions };
  }

  var LEGEND = [
    { role: 'parent', label: 'Parents' },
    { role: 'partner', label: 'Partners' },
    { role: 'child', label: 'Children' },
    { role: 'sibling', label: 'Siblings' }
  ];

  // The legend rows for a highlight: only roles that actually occur, with how many people have them.
  function legendFor(related) {
    if (!related) return [];
    var counts = {};
    related.people.forEach(function (role) { counts[role] = (counts[role] || 0) + 1; });
    return LEGEND.filter(function (row) { return counts[row.role]; }).map(function (row) {
      return { role: row.role, label: row.label, count: counts[row.role] };
    });
  }

  // Everyone on the selected person's own line, numbered by generation: ancestors negative, descendants positive.
  // Partners of the person and of their descendants are listed with the generation of the person they married.
  // Returns people (id -> {d, partner}, never `id` itself), edges (layout edge index -> d), unions (id -> d)
  // and the deepest generation up and down, which the colour ramp is spread over.
  function lineageFor(layout, id) {
    var members = {}, birthOf = {}, kidsOf = {}, ownOf = {};
    (layout.unions || []).forEach(function (u) { members[u.id] = u.members || []; });
    layout.edges.forEach(function (e) {
      if (e.kind === 'child') {
        birthOf[e.to] = e.from;
        (kidsOf[e.from] = kidsOf[e.from] || []).push(e.to);
      } else if (e.kind === 'spouse') {
        (ownOf[e.from] = ownOf[e.from] || []).push(e.to);
      }
    });
    (layout.unions || []).forEach(function (u) {
      if ((u.members || []).length === 1) (ownOf[u.members[0]] = ownOf[u.members[0]] || []).push(u.id);
    });
    var gen = new Map([[id, 0]]);
    var partners = new Map();
    var queue = [id];
    while (queue.length) {
      var child = queue.shift();
      var birth = birthOf[child];
      if (!birth) continue;
      (members[birth] || []).forEach(function (m) {
        if (!gen.has(m)) { gen.set(m, gen.get(child) - 1); queue.push(m); }
      });
    }
    var descendants = new Set([id]);
    var ownLineal = new Set();
    queue = [id];
    while (queue.length) {
      var x = queue.shift();
      (ownOf[x] || []).forEach(function (u) {
        ownLineal.add(u);
        (members[u] || []).forEach(function (m) {
          if (m !== x && !gen.has(m) && !partners.has(m)) partners.set(m, gen.get(x));
        });
        (kidsOf[u] || []).forEach(function (c) {
          if (!gen.has(c)) { gen.set(c, gen.get(x) + 1); descendants.add(c); queue.push(c); }
        });
      });
    }
    var unions = new Map();
    ownLineal.forEach(function (u) {
      var owner = (members[u] || []).filter(function (m) { return descendants.has(m); })[0];
      if (owner !== undefined) unions.set(u, gen.get(owner));
    });
    gen.forEach(function (d, person) {
      var u = birthOf[person];
      if (u && !unions.has(u)) unions.set(u, d - 1);
    });
    var edges = new Map();
    layout.edges.forEach(function (e, i) {
      if (e.kind === 'spouse' && unions.has(e.to)) {
        if (gen.has(e.from)) edges.set(i, gen.get(e.from));
        else if (partners.has(e.from)) edges.set(i, partners.get(e.from));
      } else if (e.kind === 'child' && unions.has(e.from) && gen.has(e.to)) {
        edges.set(i, gen.get(e.to));
      }
    });
    var people = new Map();
    var up = 0, down = 0;
    gen.forEach(function (d, person) {
      if (person === id) return;
      people.set(person, { d: d, partner: false });
      if (d < 0) up = Math.max(up, -d);
      else down = Math.max(down, d);
    });
    partners.forEach(function (d, person) { people.set(person, { d: d, partner: true }); });
    return { people: people, edges: edges, unions: unions, up: up, down: down };
  }

  // Where a generation sits on the ramp. Each side is stretched over its own depth, so the oldest ancestor is
  // always the full "old" colour and the youngest descendant the full "new" one, however many generations exist.
  function lineageShade(d, up, down) {
    if (d < 0) return { side: 'old', pct: Math.round(100 * Math.min(1, -d / Math.max(up, 1))) };
    if (d > 0) return { side: 'new', pct: Math.round(100 * Math.min(1, d / Math.max(down, 1))) };
    return { side: 'mid', pct: 0 };
  }

  function generationLabel(d) {
    if (d === 0) return 'same generation';
    var n = Math.abs(d);
    return n + (n === 1 ? ' generation ' : ' generations ') + (d < 0 ? 'above' : 'below');
  }

  var READABLE_SCALE = 0.6;
  var FAR_SCALE = 0.35;
  var MIN_SCALE = 0.05;
  var MAX_SCALE = 3;
  var ZOOM_STEP = 1.4;

  // Where the tree opens: the whole layout when that stays readable, otherwise scale 1 centred on the target.
  function initialView(bounds, size, target) {
    var fit = Math.min(size.w / bounds.w, size.h / bounds.h, 1);
    if (!isFinite(fit) || fit <= 0) fit = 1;
    if (fit >= READABLE_SCALE) {
      return { scale: fit, tx: (size.w - bounds.w * fit) / 2, ty: Math.max(0, (size.h - bounds.h * fit) / 2) };
    }
    if (target) {
      return { scale: 1, tx: size.w / 2 - (target.x + target.w / 2), ty: size.h / 2 - (target.y + target.h / 2) };
    }
    return { scale: 1, tx: size.w / 2 - bounds.w / 2, ty: 0 };
  }

  function lodFor(scale) {
    if (scale >= READABLE_SCALE) return 'near';
    if (scale >= FAR_SCALE) return 'mid';
    return 'far';
  }

  // Zoom by `factor` keeping the point (px, py) under the pointer still.
  function zoomAt(view, factor, px, py) {
    var next = Math.min(MAX_SCALE, Math.max(MIN_SCALE, view.scale * factor));
    var k = next / view.scale;
    return { scale: next, tx: px - (px - view.tx) * k, ty: py - (py - view.ty) * k };
  }

  function legendEnds(up, down) {
    function words(n, dir) { return n > 0 ? n + (n === 1 ? ' generation ' : ' generations ') + dir : ''; }
    return { old: words(up, 'up'), young: words(down, 'down') };
  }

  var ROW_H = 30;
  var BAR_H = 8;
  var UNKNOWN_FADE_YEARS = 8;
  var ROW_OVERSCAN = 5;

  // The bar for one person: from birth to death, to today when living, or a short fading stub when the end is
  // unknown. Null when there is no birth date.
  function spanBar(span, nowYear) {
    if (span.start === null || span.start === undefined) return null;
    if (span.end !== null && span.end !== undefined) return { from: span.start, to: span.end, fade: false };
    if (span.open === 'living') return { from: span.start, to: nowYear, fade: false };
    return { from: span.start, to: Math.min(span.start + UNKNOWN_FADE_YEARS, nowYear), fade: true };
  }

  // Pixel position and width of a bar; never negative and never thinner than 2px.
  function barRect(bar, originYear, pxPerYear) {
    return { x: (bar.from - originYear) * pxPerYear, w: Math.max(2, (bar.to - bar.from) * pxPerYear) };
  }

  // The time axis starts on a decade before the earliest year and ends next year, never in the far future.
  function axisBounds(minYear, nowYear) {
    var min = minYear === null || minYear === undefined ? Math.floor(nowYear) - 100 : Math.floor((minYear - 5) / 10) * 10;
    return { min: min, max: Math.floor(nowYear) + 1 };
  }

  // Which rows exist in the DOM: those in view plus a few above and below. `last` is exclusive.
  function rowWindow(scrollTop, viewHeight, rowHeight, count) {
    var first = Math.max(0, Math.floor(scrollTop / rowHeight) - ROW_OVERSCAN);
    var last = Math.min(count, Math.ceil((scrollTop + viewHeight) / rowHeight) + ROW_OVERSCAN);
    return { first: first, last: last };
  }

  // Where a tree node's text goes: centred across the box, or to the right of a 40px portrait when there is one.
  function nodeTextBox(n, hasImage) {
    if (hasImage) return { x: n.x + 54, anchor: 'start', width: n.w - 54 - 8 };
    return { x: n.x + n.w / 2, anchor: 'middle', width: n.w - 20 };
  }

  function visibleRange(tx, pxPerYear, originYear, width) {
    return { from: originYear + (0 - tx) / pxPerYear, to: originYear + (width - tx) / pxPerYear };
  }

  // Scrollbar thumb as fractions of the track: where the visible years sit within all years.
  function thumbGeometry(total, visible) {
    var span = Math.max(total.max - total.min, 1e-6);
    var width = Math.min(1, Math.max(0.03, (visible.to - visible.from) / span));
    var left = Math.min(1 - width, Math.max(0, (visible.from - total.min) / span));
    return { left: left, width: width };
  }

  function relationNote(rel) {
    if (rel.type !== 'half') return '';
    var via = (rel.via || []).map(function (p) { return p.name; }).join(' & ');
    return via ? 'half-sibling via ' + via : 'half-sibling';
  }

  // ------------------------------------------------------------------ browser app

  function init() {
    var NS = 'http://www.w3.org/2000/svg';
    var $ = function (id) { return document.getElementById(id); };
    var treeSvg = $('tree');
    var tlSection = $('timeline');
    var tlSvg = $('timeline-svg');
    var tlHead = $('timeline-head');
    var undated = $('undated');
    var panel = $('panel');
    var search = $('search');
    var results = $('results');
    var tabs = Array.prototype.slice.call(document.querySelectorAll('#tabs a'));
    var focusBar = $('focus-bar');
    var legendEl = $('legend');
    var controls = $('tree-controls');
    var metaHome = (document.querySelector('meta[name="famsite-home"]') || {}).content || null;
    var ME_KEY = 'famsite.me';
    function savedMe() {
      try { return root.localStorage.getItem(ME_KEY) || null; } catch (e) { return null; }
    }
    // The person the viewer said is them, else the site's home person.
    var home = savedMe() || metaHome;
    var treeTab = document.querySelector('#tabs a[data-view="focus"]');

    var canvas = document.createElement('canvas').getContext('2d');
    function measureWith(font) {
      return function (text) {
        canvas.font = font;
        return canvas.measureText(text).width;
      };
    }
    var measureName = measureWith('13px system-ui, sans-serif');
    var measureLabel = measureWith('12px system-ui, sans-serif');
    var measureLabelBold = measureWith('600 12px system-ui, sans-serif');

    function svgEl(name, attrs) {
      var el = document.createElementNS(NS, name);
      Object.keys(attrs || {}).forEach(function (k) { el.setAttribute(k, attrs[k]); });
      return el;
    }

    function savedColourMode() {
      // the generation ramp is the default; the relationship roles are one click away
      try { return localStorage.getItem('famsite.colourMode') === 'family' ? 'family' : 'lineage'; } catch (e) { return 'lineage'; }
    }
    var state = {
      view: 'tree', selected: null, layout: null, index: null, timeline: null,
      colourMode: savedColourMode()
    };
    var people = new Map();

    // ---------------------------------------------------------------- navigation

    function go(view, id) {
      var next = routeHash(view, id);
      if (location.hash === next) route();
      else location.hash = next;
    }

    // `hidden` is only a real attribute on HTML elements; SVG needs it set explicitly.
    function setHidden(el, hidden) {
      if (hidden) el.setAttribute('hidden', '');
      else el.removeAttribute('hidden');
    }

    function showView(view) {
      state.view = view;
      var treeLike = view === 'tree' || view === 'focus';
      setHidden(treeSvg, !treeLike);
      setHidden(tlSection, view !== 'timeline');
      if (!treeLike || view !== 'focus') setHidden(focusBar, true);
      if (!treeLike) legendEl.hidden = true;
      controls.hidden = !treeLike;
      tabs.forEach(function (a) {
        var active = a.getAttribute('data-view') === view;
        if (active) a.setAttribute('aria-current', 'page');
        else a.removeAttribute('aria-current');
      });
    }

    // The Tree tab always leads to a focused tree: the selected person's, else the home person's.
    function updateTreeTab(id) {
      if (treeTab) treeTab.setAttribute('href', id ? routeHash('focus', id) : '#/tree');
    }

    function route() {
      if (!location.hash && home) history.replaceState(null, '', routeHash('focus', home));
      var r = parseRoute(location.hash);
      showView(r.view);
      updateTreeTab(r.id || state.selected || home);
      if (r.view === 'focus' && r.id) {
        tree.ensure();
        tree.showFocus(r.id);
      } else if (r.view === 'tree' || r.view === 'focus') {
        tree.ensure();
        tree.showFull();
        if (r.id) tree.select(r.id, true, true);
        else tree.clearSelection();
      } else {
        timeline.show(r.id);
      }
    }

    // ---------------------------------------------------------------- side panel

    function link(href, text) {
      var a = document.createElement('a');
      a.href = href;
      a.textContent = text;
      return a;
    }

    function relativeGroup(title, list, view) {
      if (!list || !list.length) return null;
      var wrap = document.createElement('section');
      wrap.className = 'rel-group';
      var h = document.createElement('h3');
      h.textContent = title;
      var ul = document.createElement('ul');
      ul.className = 'chips';
      list.forEach(function (rel) {
        var li = document.createElement('li');
        var a = link(routeHash(view, rel.id), '');
        a.className = 'chip';
        var name = document.createElement('span');
        name.className = 'chip-name';
        name.textContent = rel.name;
        a.appendChild(name);
        function line(cls, text) {
          if (!text) return;
          var s = document.createElement('span');
          s.className = cls;
          s.textContent = text;
          a.appendChild(s);
        }
        line('chip-years', rel.years);
        line('chip-note', relationNote(rel));
        (rel.partnerships || []).forEach(function (part) { line('partnership', part.text); });
        li.appendChild(a);
        ul.appendChild(li);
      });
      wrap.appendChild(h);
      wrap.appendChild(ul);
      return wrap;
    }

    function closePanel() {
      state.selected = null;
      panel.hidden = true;
      panel.textContent = '';
      tree.refresh();
      timeline.refresh();
      if (state.view === 'tree' && parseRoute(location.hash).id) go('tree', null);
    }

    // The kinship line in the panel: how this person relates to the viewer ("Your grandmother").
    var kinData = null;
    function fillKin(line, id) {
      var kin = root.famsiteKin, site = root.famsiteSite;
      if (!kin || !site) return;
      if (!kinData) {
        kinData = fetch('kin.json').then(function (r) { return r.json(); }).then(function (d) { return d.people; })
          .catch(function () { return null; });
      }
      kinData.then(function (kinPeople) {
        if (!kinPeople) return;
        var store = null;
        try { store = root.localStorage; } catch (e) { store = null; }
        var who = site.viewerId(store, kinPeople, metaHome);
        if (!who.id) return;
        var text = kin.phrase(kin.kinship(kinPeople, who.id, id), kinPeople[who.id].name, who.mine);
        line.textContent = text;
        line.hidden = !text;
      });
    }

    function showPanel(id) {
      state.selected = id;
      panel.hidden = false;
      panel.textContent = '';
      var head = document.createElement('div');
      head.className = 'panel-head';
      var avatar = document.createElement('div');
      avatar.className = 'avatar avatar-sm';
      avatar.setAttribute('aria-hidden', 'true');
      var titleBox = document.createElement('div');
      titleBox.className = 'panel-title';
      var title = document.createElement('h2');
      title.textContent = (people.get(id) || { name: id }).name;
      titleBox.appendChild(title);
      var close = document.createElement('button');
      close.type = 'button';
      close.className = 'close';
      close.setAttribute('aria-label', 'Close');
      close.textContent = '×';
      close.addEventListener('click', closePanel);
      head.appendChild(avatar);
      head.appendChild(titleBox);
      head.appendChild(close);
      panel.appendChild(head);
      var body = document.createElement('div');
      body.textContent = 'Loading…';
      panel.appendChild(body);
      fetch('data/people/' + id + '.json')
        .then(function (r) { return r.json(); })
        .then(function (p) {
          if (state.selected !== id) return;
          body.textContent = '';
          title.textContent = p.name;
          if (p.image) {
            var photo = document.createElement('img');
            photo.className = 'avatar avatar-sm';
            photo.src = p.image.src;
            photo.alt = p.image.alt;
            avatar.replaceWith(photo);
          } else {
            avatar.textContent = p.initials || '';
          }
          function para(cls, text) {
            if (!text) return;
            var el = document.createElement('p');
            el.className = cls;
            el.textContent = text;
            titleBox.appendChild(el);
          }
          para('years', p.years);
          var kinLine = document.createElement('p');
          kinLine.className = 'kin';
          kinLine.hidden = true;
          titleBox.appendChild(kinLine);
          fillKin(kinLine, id);
          para('summary', p.summary);
          var pills = document.createElement('div');
          pills.className = 'pills';
          function pill(href, text) {
            var a = link(href, text);
            a.className = 'pill';
            pills.appendChild(a);
          }
          if (state.view === 'timeline') pill(routeHash('tree', id), 'Show in tree');
          pill(routeHash('focus', id), 'Focus tree');
          pill(routeHash('timeline', id), 'Timeline');
          pill('p/' + id + '/', 'Page');
          body.appendChild(pills);
          if (p.bodyHtml) {
            var bio = document.createElement('div');
            bio.className = 'bio';
            bio.innerHTML = p.bodyHtml;
            body.appendChild(bio);
            var more = link('p/' + id + '/', 'Read more');
            more.className = 'read-more';
            body.appendChild(more);
          }
          [
            ['Parents', p.parents], ['Partners', p.spouses], ['Siblings', p.siblings], ['Children', p.children]
          ].forEach(function (pair) {
            var section = relativeGroup(pair[0], pair[1], state.view);
            if (section) body.appendChild(section);
          });
        })
        .catch(function () {
          body.textContent = 'Could not load this person.';
        });
    }

    document.addEventListener('keydown', function (e) {
      if (e.key === 'Escape' && !panel.hidden) closePanel();
    });

    // ---------------------------------------------------------------- tree view

    var tree = (function () {
      var NODE_PAD = 10;
      var viewport = svgEl('g');
      var edgeLayer = svgEl('g');
      var nodeLayer = svgEl('g');
      viewport.appendChild(edgeLayer);
      viewport.appendChild(nodeLayer);
      treeSvg.appendChild(viewport);
      var grid = null;
      var nodes = new Map();
      var live = new Map();
      var unionIndex = new Map();
      var endedUnions = new Set();
      var tx = 0, ty = 0, scale = 1;
      var drag = null;
      var moved = false;
      var loading = null;
      var hl = null;
      var lin = null;
      var fullLayout = null;
      var focusId = null;
      var focusCache = {};
      // highlighted connectors are drawn after the plain ones, parents last so their line is never hidden
      var roleLayers = {};
      ['sibling', 'partner', 'child', 'parent'].forEach(function (role) {
        roleLayers[role] = svgEl('g');
        viewport.insertBefore(roleLayers[role], nodeLayer);
      });
      var linLayer = svgEl('g'); // lineage-coloured connectors
      viewport.insertBefore(linLayer, nodeLayer);

      // put an element on the generation ramp: a side class plus how far along that side it sits
      function shade(el, d) {
        var sh = lineageShade(d, lin.up, lin.down);
        el.classList.add('lin-' + sh.side);
        el.style.setProperty('--p', sh.pct);
      }

      function makeNode(id) {
        var n = nodes.get(id);
        var info = people.get(id) || { name: id, years: '' };
        var mark = '';
        var linEntry = null;
        if (id === state.selected) mark = ' selected';
        else if (lin) {
          linEntry = lin.people.get(id);
          if (linEntry) mark = ' lin' + (linEntry.partner ? ' lin-partner' : '');
          else mark = ' dim';
        } else if (hl) {
          var role = hl.people.get(id);
          if (role) mark = ' related role-' + role;
          else mark = ' dim';
        }
        if (id === focusId) mark += ' focus';
        var g = svgEl('g', { 'class': 'node' + mark, 'data-id': id });
        if (linEntry) shade(g, linEntry.d);
        g.appendChild(svgEl('rect', { x: n.x, y: n.y, width: n.w, height: n.h, rx: 6 }));
        var box = nodeTextBox(n, !!info.image);
        if (info.image) {
          var clip = svgEl('clipPath', { id: 'clip-' + id });
          clip.appendChild(svgEl('circle', { cx: n.x + 28, cy: n.y + 32, r: 20 }));
          g.appendChild(clip);
          g.appendChild(svgEl('image', {
            href: info.image, x: n.x + 8, y: n.y + 12, width: 40, height: 40,
            'clip-path': 'url(#clip-' + id + ')', preserveAspectRatio: 'xMidYMid slice'
          }));
        }
        var wrapped = wrapName(info.name, box.width, measureName, 2);
        var tip = svgEl('title');
        tip.textContent = info.name + (info.years ? ' (' + info.years + ')' : '') +
          (linEntry ? ' · ' + generationLabel(linEntry.d) + (linEntry.partner ? ' (partner)' : '') : '');
        g.appendChild(tip);
        var top = wrapped.lines.length > 1 ? n.y + 20 : n.y + 26;
        wrapped.lines.forEach(function (line, i) {
          var t = svgEl('text', { x: box.x, y: top + i * 16, 'text-anchor': box.anchor, 'class': 'name' });
          t.textContent = line;
          g.appendChild(t);
        });
        var years = svgEl('text', {
          x: box.x,
          y: n.y + n.h - 10,
          'text-anchor': box.anchor,
          'class': 'years'
        });
        years.textContent = info.years;
        g.appendChild(years);
        var more = state.layout.hidden && state.layout.hidden[id];
        if (more) {
          var badge = svgEl('text', { x: n.x + n.w - 6, y: n.y + 14, 'text-anchor': 'end', 'class': 'more' });
          badge.textContent = '+' + more;
          g.appendChild(badge);
        }
        g.addEventListener('click', function (e) {
          e.stopPropagation();
          if (!moved) select(id, false, false);
        });
        g.addEventListener('dblclick', function (e) {
          e.stopPropagation();
          go('focus', id);
        });
        return g;
      }

      function make(key) {
        var kind = key.slice(0, 2), ref = key.slice(2);
        if (kind === 'n:') {
          var g = makeNode(ref);
          nodeLayer.appendChild(g);
          return g;
        }
        if (kind === 'u:') {
          var u = unionIndex.get(ref);
          var linUnion = lin ? lin.unions.get(ref) : undefined;
          var dot = svgEl('circle', {
            cx: u.x, cy: u.y, r: dotRadius(),
            'class': 'union' + (endedUnions.has(ref) ? ' ended' : '') +
              (lin ? (linUnion !== undefined ? ' lin' : ' dim')
                : hl ? (hl.unions.has(ref) ? ' hi role-' + hl.unions.get(ref) : ' dim')
                : '')
          });
          if (linUnion !== undefined) shade(dot, linUnion);
          nodeLayer.appendChild(dot);
          return dot;
        }
        if (kind === 'l:') {
          var label = state.layout.labels[Number(ref)];
          var kind = label.kind || 'loners';
          var text = svgEl('text', { x: label.x, y: label.y, 'class': 'group-label ' + kind, 'font-size': labelSize() * (kind === 'island' ? 1.4 : 1) });
          if (kind === 'island') text.setAttribute('text-anchor', 'middle');
          text.textContent = label.text;
          nodeLayer.appendChild(text);
          return text;
        }
        var edge = state.layout.edges[Number(ref)];
        var role = hl ? hl.edges.get(Number(ref)) : null;
        var linEdge = lin ? lin.edges.get(Number(ref)) : undefined;
        var line = svgEl('polyline', {
          points: edge.points.map(function (p) { return p.join(','); }).join(' '),
          'class': 'edge ' + edge.kind + (edge.kind === 'spouse' && endedUnions.has(edge.to) ? ' ended' : '') +
            (lin ? (linEdge !== undefined ? ' hi lin' : ' dim')
              : hl ? (role ? ' hi role-' + role : ' dim')
              : ''),
          fill: 'none'
        });
        if (linEdge !== undefined) shade(line, linEdge);
        (linEdge !== undefined ? linLayer : role ? roleLayers[role] : edgeLayer).appendChild(line);
        return line;
      }

      // Junction dots are geometry, so they would shrink with the zoom: size them from the current scale instead.
      function dotRadius() { return Math.min(9, Math.max(3, 4 / scale)); }
      // group labels are text in layout units too: keep them readable when the tree is fitted
      function labelSize() { return Math.min(64, Math.max(14, 13 / scale)); }

      function render() {
        if (!grid) return;
        var r = treeSvg.getBoundingClientRect();
        var margin = 200;
        var view = {
          x: -tx / scale - margin,
          y: -ty / scale - margin,
          w: r.width / scale + 2 * margin,
          h: r.height / scale + 2 * margin
        };
        var want = queryGrid(grid, view);
        live.forEach(function (el, key) {
          if (!want.has(key)) {
            el.remove();
            live.delete(key);
          }
        });
        want.forEach(function (key) {
          if (!live.has(key)) live.set(key, make(key));
        });
        viewport.setAttribute('transform', 'translate(' + tx + ' ' + ty + ') scale(' + scale + ')');
        ['near', 'mid', 'far'].forEach(function (lod) { treeSvg.classList.toggle('lod-' + lod, lod === lodFor(scale)); });
        var radius = dotRadius();
        var size = labelSize();
        live.forEach(function (el, key) {
          if (key.slice(0, 2) === 'u:') el.setAttribute('r', radius);
          else if (key.slice(0, 2) === 'l:') el.setAttribute('font-size', size * (el.classList.contains('island') ? 1.4 : 1));
        });
      }

      function setColourMode(mode) {
        state.colourMode = mode;
        try { localStorage.setItem('famsite.colourMode', mode); } catch (e) { /* private mode: remember for this visit only */ }
        rebuild();
      }

      function renderLegend() {
        legendEl.textContent = '';
        legendEl.hidden = !(lin || hl) || !(state.view === 'tree' || state.view === 'focus');
        if (legendEl.hidden) return;
        // the mode can be switched only while a person stays selected: hovering moves off the legend and ends
        if (state.selected) {
          var modes = document.createElement('div');
          modes.className = 'legend-modes';
          [['family', 'Family'], ['lineage', 'Lineage']].forEach(function (pair) {
            var b = document.createElement('button');
            b.type = 'button';
            b.setAttribute('data-mode', pair[0]);
            b.setAttribute('aria-pressed', String(state.colourMode === pair[0]));
            b.textContent = pair[1];
            b.addEventListener('click', function () { setColourMode(pair[0]); });
            modes.appendChild(b);
          });
          legendEl.appendChild(modes);
        }
        if (lin) {
          if (!lin.people.size) {
            var none = document.createElement('div');
            none.textContent = 'No ancestors or descendants recorded';
            legendEl.appendChild(none);
            return;
          }
          var ramp = document.createElement('div');
          ramp.className = 'legend-ramp';
          legendEl.appendChild(ramp);
          var ends = document.createElement('div');
          ends.className = 'legend-ends';
          var legendWords = legendEnds(lin.up, lin.down);
          [legendWords.old, 'Selected', legendWords.young].forEach(function (text) {
            var span = document.createElement('span');
            span.textContent = text;
            ends.appendChild(span);
          });
          legendEl.appendChild(ends);
          return;
        }
        legendFor(hl).forEach(function (row) {
          var item = document.createElement('div');
          item.className = 'legend-item';
          var swatch = document.createElement('span');
          swatch.className = 'legend-swatch role-' + row.role;
          item.appendChild(swatch);
          item.appendChild(document.createTextNode(row.label + ' · ' + row.count));
          legendEl.appendChild(item);
        });
      }

      function rebuild() {
        var target = state.selected;
        var known = target && state.layout && nodes.has(target);
        lin = known && state.colourMode === 'lineage' ? lineageFor(state.layout, target) : null;
        hl = known && !lin ? relatedFor(state.layout, target) : null;
        treeSvg.classList.toggle('has-hl', !!(hl || lin));
        renderLegend();
        live.forEach(function (el) { el.remove(); });
        live.clear();
        render();
      }

      function fit() {
        var r = treeSvg.getBoundingClientRect();
        var b = state.layout.bounds;
        scale = Math.max(MIN_SCALE, Math.min(r.width / b.w, r.height / b.h, 1));
        if (!isFinite(scale) || scale <= 0) scale = 1;
        tx = (r.width - b.w * scale) / 2;
        ty = Math.max(0, (r.height - b.h * scale) / 2);
      }

      function centerOn(id) {
        var n = nodes.get(id);
        if (!n) return;
        var r = treeSvg.getBoundingClientRect();
        tx = r.width / 2 - (n.x + n.w / 2) * scale;
        ty = r.height / 2 - (n.y + n.h / 2) * scale;
      }

      function select(id, center, fromRoute) {
        if (!nodes.has(id)) return;
        state.selected = id;
        if (!fromRoute && !focusId) {
          var target = routeHash('tree', id);
          if (location.hash !== target) history.replaceState(null, '', target);
        }
        if (scale < READABLE_SCALE) {
          scale = 1;
          center = true;
        }
        if (center) centerOn(id);
        updateTreeTab(id);
        rebuild();
        showPanel(id);
      }

      function clearSelection() {
        if (state.selected === null && panel.hidden) return;
        state.selected = null;
        panel.hidden = true;
        rebuild();
      }

      // Swap the drawn layout (the full tree or one person's focused tree) and rebuild the spatial index.
      function useLayout(layout) {
        state.layout = layout;
        nodes = new Map();
        unionIndex = new Map();
        endedUnions = new Set();
        var boxes = [];
        layout.nodes.forEach(function (n) {
          nodes.set(n.id, n);
          boxes.push({ id: 'n:' + n.id, x: n.x, y: n.y, w: n.w, h: n.h });
        });
        layout.unions.forEach(function (u) {
          unionIndex.set(u.id, u);
          if (u.ended) endedUnions.add(u.id);
          boxes.push({ id: 'u:' + u.id, x: u.x - 4, y: u.y - 4, w: 8, h: 8 });
        });
        layout.edges.forEach(function (e, i) {
          var b = boundsOf(e.points);
          boxes.push({ id: 'e:' + i, x: b.x, y: b.y, w: b.w, h: b.h });
        });
        (layout.labels || []).forEach(function (l, i) {
          if (l.kind === 'island') boxes.push({ id: 'l:' + i, x: l.x - 160, y: l.y - 40, w: 320, h: 80 });
          else boxes.push({ id: 'l:' + i, x: l.x, y: l.y - 16, w: 320, h: 24 });
        });
        grid = buildGrid(boxes, CELL);
        var box = treeSvg.getBoundingClientRect();
        var view = initialView(layout.bounds, { w: box.width, h: box.height },
          nodes.get(focusId || state.selected || home) || null);
        scale = view.scale;
        tx = view.tx;
        ty = view.ty;
        rebuild();
      }

      function showFull() {
        focusId = null;
        setHidden(focusBar, true);
        if (fullLayout && state.layout !== fullLayout) {
          state.selected = null;
          useLayout(fullLayout);
        }
      }

      function showFocusBar(id) {
        focusBar.textContent = '';
        var text = document.createElement('span');
        var who = people.get(id);
        text.textContent = 'Focused on ' + (who ? who.name : id) + ' — ancestors and descendants only';
        var back = link(routeHash('tree', id), 'Show full tree');
        back.className = 'back';
        focusBar.appendChild(text);
        focusBar.appendChild(back);
        setHidden(focusBar, false);
      }

      function showFocus(id) {
        if (!fullLayout) return; // ensure() will call route() again once the data is loaded
        focusId = id;
        function apply(layout) {
          if (focusId !== id) return;
          state.selected = null;
          panel.hidden = true;
          useLayout(layout);
          showFocusBar(id);
        }
        if (focusCache[id]) {
          apply(focusCache[id]);
          return;
        }
        fetch('focus/' + encodeURIComponent(id) + '.json')
          .then(function (r) {
            if (!r.ok) throw new Error('missing');
            return r.json();
          })
          .then(function (layout) {
            focusCache[id] = layout;
            apply(layout);
          })
          .catch(function () {
            focusId = null;
            if (id === savedMe()) {
              // "me" names someone who is no longer in the site: forget it and use the site's home person
              try { root.localStorage.removeItem(ME_KEY); } catch (e) { /* nothing to forget */ }
              home = metaHome;
              if (home && home !== id) {
                go('focus', home);
                return;
              }
            }
            go('tree', null);
          });
      }

      function has(id) { return nodes.has(id); }

      function ensure() {
        if (state.layout) {
          rebuild();
          return;
        }
        if (loading) return;
        loading = Promise.all([
          fetch('layout.json').then(function (r) { return r.json(); }),
          fetch('index.json').then(function (r) { return r.json(); })
        ]).then(function (loaded) {
          fullLayout = loaded[0];
          state.index = loaded[1];
          state.index.forEach(function (p) { people.set(p.id, p); });
          useLayout(fullLayout);
          route();
        }).catch(function () {
          treeSvg.insertAdjacentHTML('afterend', '<p class="error">Could not load the tree data.</p>');
        });
      }

      // Active pointers on the tree: one pans, two pinch.
      var pointers = new Map();
      var pinchDist = 0;

      function spread() {
        var pts = Array.from(pointers.values());
        return { dist: Math.hypot(pts[0].x - pts[1].x, pts[0].y - pts[1].y), x: (pts[0].x + pts[1].x) / 2, y: (pts[0].y + pts[1].y) / 2 };
      }

      function applyView(v) {
        scale = v.scale;
        tx = v.tx;
        ty = v.ty;
        render();
      }

      function zoomBy(factor) {
        var r = treeSvg.getBoundingClientRect();
        applyView(zoomAt({ scale: scale, tx: tx, ty: ty }, factor, r.width / 2, r.height / 2));
      }

      treeSvg.addEventListener('pointerdown', function (e) {
        pointers.set(e.pointerId, { x: e.clientX, y: e.clientY });
        moved = false;
        if (pointers.size === 1) {
          drag = { x: e.clientX, y: e.clientY, tx: tx, ty: ty };
        } else if (pointers.size === 2) {
          drag = null;
          pinchDist = spread().dist;
        }
      });
      window.addEventListener('pointermove', function (e) {
        if (pointers.has(e.pointerId)) pointers.set(e.pointerId, { x: e.clientX, y: e.clientY });
        if (pointers.size >= 2) {
          var s = spread();
          var r = treeSvg.getBoundingClientRect();
          if (pinchDist > 0 && s.dist > 0) {
            applyView(zoomAt({ scale: scale, tx: tx, ty: ty }, s.dist / pinchDist, s.x - r.left, s.y - r.top));
          }
          pinchDist = s.dist;
          moved = true;
          return;
        }
        if (!drag) return;
        var dx = e.clientX - drag.x, dy = e.clientY - drag.y;
        if (Math.abs(dx) + Math.abs(dy) > 4) moved = true;
        tx = drag.tx + dx;
        ty = drag.ty + dy;
        render();
      });
      function releasePointer(e) {
        pointers.delete(e.pointerId);
        pinchDist = 0;
        if (pointers.size === 1) {
          var rest = Array.from(pointers.values())[0];
          drag = { x: rest.x, y: rest.y, tx: tx, ty: ty };
        } else {
          drag = null;
        }
        setTimeout(function () { moved = false; }, 0);
      }
      window.addEventListener('pointerup', releasePointer);
      window.addEventListener('pointercancel', releasePointer);
      treeSvg.addEventListener('click', function () {
        if (!moved && !panel.hidden) closePanel();
      });
      treeSvg.addEventListener('wheel', function (e) {
        e.preventDefault();
        var r = treeSvg.getBoundingClientRect();
        applyView(zoomAt({ scale: scale, tx: tx, ty: ty }, Math.exp(-e.deltaY * 0.0015), e.clientX - r.left, e.clientY - r.top));
      }, { passive: false });
      controls.addEventListener('click', function (e) {
        var act = e.target && e.target.getAttribute && e.target.getAttribute('data-act');
        if (act === 'zoom-in') zoomBy(ZOOM_STEP);
        else if (act === 'zoom-out') zoomBy(1 / ZOOM_STEP);
        else if (act === 'fit') {
          fit();
          render();
        } else if (act === 'home' && home) go('focus', home);
      });
      if (!home) controls.querySelector('[data-act="home"]').hidden = true;
      document.addEventListener('keydown', function (e) {
        if (state.view !== 'tree' && state.view !== 'focus') return;
        if (e.ctrlKey || e.metaKey || e.altKey) return;
        if (e.target && /^(INPUT|TEXTAREA|SELECT)$/.test(e.target.tagName || '')) return;
        if (e.key === '+' || e.key === '=') zoomBy(ZOOM_STEP);
        else if (e.key === '-') zoomBy(1 / ZOOM_STEP);
        else if (e.key === '0') {
          fit();
          render();
        }
      });
      window.addEventListener('resize', function () { if (state.view === 'tree' || state.view === 'focus') render(); });

      return {
        ensure: ensure,
        select: select,
        clearSelection: clearSelection,
        showFocus: showFocus,
        showFull: showFull,
        has: has,
        refresh: function () { rebuild(); }
      };
    })();

    // ---------------------------------------------------------------- timeline view

    var timeline = (function () {
      var AXIS_H = 34;
      var PAD = 40;
      var focus = null;
      var pxPerYear = 14;
      var tx = PAD, ty = 0; // ty is the vertical scroll: 0 or negative
      var bounds = { min: 0, max: 1 };
      var nowYear = 0;
      var rowIndex = new Map();
      var marks = new Map(); // person id -> partnership events that belong on their bar
      var ready = false;
      var drag = null;
      var moved = false;
      var loading = null;
      var defs = svgEl('defs');
      [['tl-fade', 'var(--muted)'], ['tl-fade-accent', 'var(--accent)']].forEach(function (pair) {
        var grad = svgEl('linearGradient', { id: pair[0], x1: 0, x2: 1, y1: 0, y2: 0 });
        grad.appendChild(svgEl('stop', { offset: 0, style: 'stop-color:' + pair[1] + ';stop-opacity:1' }));
        grad.appendChild(svgEl('stop', { offset: 1, style: 'stop-color:' + pair[1] + ';stop-opacity:0' }));
        defs.appendChild(grad);
      });
      var gridLayer = svgEl('g');
      var rowLayer = svgEl('g');
      var axisLayer = svgEl('g');
      tlSvg.appendChild(defs);
      tlSvg.appendChild(gridLayer);
      tlSvg.appendChild(rowLayer);
      tlSvg.appendChild(axisLayer);
      var emptyEl = document.createElement('p');
      emptyEl.id = 'timeline-empty';
      emptyEl.textContent = 'No dated events yet.';
      emptyEl.hidden = true;
      tlSection.insertBefore(emptyEl, tlSvg);

      function viewWidth() { return tlSvg.getBoundingClientRect().width; }
      function viewHeight() { return tlSvg.getBoundingClientRect().height; }
      function rows() { return state.timeline ? state.timeline.rows : []; }
      function xOfYear(year) { return (year - bounds.min) * pxPerYear + tx; }
      function maxScroll() { return Math.max(0, rows().length * ROW_H - (viewHeight() - AXIS_H)); }

      function clampView() {
        var minTx = Math.min(PAD, viewWidth() - (bounds.max - bounds.min) * pxPerYear - PAD);
        tx = Math.min(PAD, Math.max(minTx, tx));
        ty = Math.min(0, Math.max(-maxScroll(), ty));
      }

      function totalRange() { return { min: bounds.min, max: bounds.max }; }

      function ticks() {
        var steps = [1, 2, 5, 10, 20, 50, 100, 200, 500];
        var step = steps[steps.length - 1];
        for (var i = 0; i < steps.length; i++) {
          if (steps[i] * pxPerYear >= 70) { step = steps[i]; break; }
        }
        var out = [];
        for (var y = Math.ceil(bounds.min / step) * step; y <= bounds.max; y += step) out.push(y);
        return out;
      }

      function relatedSet(id) {
        var info = state.timeline.people[id];
        var set = new Set();
        if (!info) return set;
        [info.parents, info.spouses, info.children, info.siblings].forEach(function (list) {
          (list || []).forEach(function (pid) { set.add(pid); });
        });
        return set;
      }

      function drawRow(index, id, related) {
        var info = state.timeline.people[id];
        var span = info.span;
        var cls = 'span-row';
        if (id === state.selected) cls += ' selected';
        else if (state.selected) cls += related.has(id) ? ' related' : ' dim';
        var g = svgEl('g', { 'class': cls, 'data-id': id, transform: 'translate(0 ' + (AXIS_H + index * ROW_H + ty) + ')' });
        var bar = spanBar(span, nowYear);
        var startX = null;
        if (bar) {
          var rect = barRect(bar, bounds.min, pxPerYear);
          startX = rect.x + tx;
          var kind = span.open === 'living' ? ' open-living' : span.open === 'unknown' ? ' open-unknown' : '';
          g.appendChild(svgEl('rect', { x: startX, y: 15, width: rect.w, height: BAR_H, rx: 4, 'class': 'bar' + kind }));
          g.appendChild(svgEl('circle', { cx: startX + 2, cy: 15 + BAR_H / 2, r: 4, 'class': 'cap birth' }));
          if (span.end !== null) {
            g.appendChild(svgEl('circle', { cx: startX + rect.w - 2, cy: 15 + BAR_H / 2, r: 4, 'class': 'cap death' }));
          }
        } else if (span.end !== null) {
          startX = xOfYear(span.end);
          g.appendChild(svgEl('circle', { cx: startX, cy: 15 + BAR_H / 2, r: 4, 'class': 'cap death' }));
        }
        (marks.get(id) || []).forEach(function (ev) {
          var x = xOfYear(yearPosition(ev)), y = 15 + BAR_H / 2;
          var d = 'M' + x + ' ' + (y - 4) + 'l4 4l-4 4l-4 -4z';
          var mark = svgEl('path', { d: d, 'class': 'mark ' + (ev.type === 'divorce' ? 'end' : 'partner') });
          var tip = svgEl('title');
          tip.textContent = ev.text + ' · ' + ev.year;
          mark.appendChild(tip);
          g.appendChild(mark);
        });
        var label = svgEl('text', { x: Math.max(startX === null ? 8 : startX, 8), y: 11, 'class': 'label' });
        label.textContent = info.name;
        var meta = people.get(id);
        if (meta && meta.years) {
          var years = svgEl('tspan', { dx: 6, 'class': 'years' });
          years.textContent = meta.years;
          label.appendChild(years);
        }
        g.appendChild(label);
        g.addEventListener('click', function (e) {
          e.stopPropagation();
          if (!moved) selectRow(id);
        });
        rowLayer.appendChild(g);
      }

      function render() {
        if (!ready) return;
        var r = tlSvg.getBoundingClientRect();
        clampView();
        gridLayer.textContent = '';
        rowLayer.textContent = '';
        axisLayer.textContent = '';
        axisLayer.appendChild(svgEl('rect', { x: 0, y: 0, width: r.width, height: AXIS_H, 'class': 'axis-bg' }));
        ticks().forEach(function (year) {
          var x = xOfYear(year);
          if (x < -40 || x > r.width + 40) return;
          gridLayer.appendChild(svgEl('line', { x1: x, x2: x, y1: AXIS_H, y2: r.height, 'class': 'tick' }));
          var label = svgEl('text', { x: x + 4, y: AXIS_H - 12, 'class': 'tick-label' });
          label.textContent = String(year);
          axisLayer.appendChild(label);
        });
        var list = rows();
        var win = rowWindow(-ty, r.height - AXIS_H, ROW_H, list.length);
        var related = state.selected ? relatedSet(state.selected) : new Set();
        for (var i = win.first; i < win.last; i++) drawRow(i, list[i], related);
        updateControls();
      }

      function panBy(dx) {
        tx += dx;
        render();
      }

      function zoomBy(factor, anchorX) {
        var anchor = anchorX === undefined ? viewWidth() / 2 : anchorX;
        var yearAt = (anchor - tx) / pxPerYear + bounds.min;
        pxPerYear = Math.min(200, Math.max(1, pxPerYear * factor));
        tx = anchor - (yearAt - bounds.min) * pxPerYear;
        render();
      }

      function centerOnYear(year) {
        tx = viewWidth() / 2 - (year - bounds.min) * pxPerYear;
        render();
      }

      function fit() {
        pxPerYear = Math.min(60, Math.max(1, (viewWidth() - 2 * PAD) / Math.max(1, bounds.max - bounds.min)));
        tx = PAD;
        ty = 0;
      }

      function updateControls() {
        var readout = $('tl-range');
        var scroll = $('timeline-scroll');
        if (!readout || !scroll || !rows().length) return;
        var vis = visibleRange(tx, pxPerYear, bounds.min, viewWidth());
        readout.textContent = Math.round(vis.from) + ' – ' + Math.round(vis.to) +
          '  ·  ' + Math.round(vis.to - vis.from) + ' years in view';
        var geo = thumbGeometry(totalRange(), vis);
        var thumb = scroll.firstChild;
        thumb.style.left = (geo.left * 100) + '%';
        thumb.style.width = (geo.width * 100) + '%';
      }

      function button(id, label, title, handler) {
        var b = document.createElement('button');
        b.type = 'button';
        b.id = id;
        b.textContent = label;
        b.title = title;
        b.setAttribute('aria-label', title);
        b.addEventListener('click', handler);
        return b;
      }

      function header() {
        tlHead.textContent = '';
        var h = document.createElement('h2');
        h.textContent = 'Family timeline';
        tlHead.appendChild(h);
        var controls = document.createElement('span');
        controls.className = 'tl-controls';
        controls.appendChild(button('tl-left', '◀', 'Earlier (←)', function () { panBy(viewWidth() * 0.25); }));
        controls.appendChild(button('tl-right', '▶', 'Later (→)', function () { panBy(-viewWidth() * 0.25); }));
        controls.appendChild(button('tl-zoom-out', '−', 'Zoom out (-)', function () { zoomBy(1 / 1.4); }));
        controls.appendChild(button('tl-zoom-in', '+', 'Zoom in (+)', function () { zoomBy(1.4); }));
        controls.appendChild(button('tl-fit', 'Fit', 'Fit everything (Home)', function () {
          fit();
          render();
        }));
        var readout = document.createElement('span');
        readout.id = 'tl-range';
        readout.className = 'hint';
        controls.appendChild(readout);
        tlHead.appendChild(controls);
        undated.hidden = !state.timeline.undated.length;
        if (!undated.hidden) {
          undated.textContent = '';
          var summary = document.createElement('summary');
          summary.textContent = state.timeline.undated.length + ' people have no dated events';
          undated.appendChild(summary);
          var ul = document.createElement('ul');
          state.timeline.undated.forEach(function (pid) {
            var li = document.createElement('li');
            li.appendChild(link(routeHash('timeline', pid), state.timeline.people[pid].name));
            ul.appendChild(li);
          });
          undated.appendChild(ul);
        }
      }

      function scrollToRow(index) {
        var top = index * ROW_H, view = viewHeight() - AXIS_H;
        if (top + ty >= 0 && top + ROW_H + ty <= view) return;
        ty = -(top - (view - ROW_H) / 2);
        clampView();
      }

      function selectRow(id) {
        history.replaceState(null, '', routeHash('timeline', id));
        showPanel(id);
        render();
      }

      function prepare() {
        var d = new Date();
        nowYear = yearPosition({ year: d.getFullYear(), month: d.getMonth() + 1, day: d.getDate() });
        bounds = axisBounds(state.timeline.range.min, nowYear);
        rowIndex = new Map();
        rows().forEach(function (id, i) { rowIndex.set(id, i); });
        marks = new Map();
        state.timeline.events.forEach(function (ev) {
          if (ev.type !== 'marriage' && ev.type !== 'partnership' && ev.type !== 'divorce') return;
          ev.people.forEach(function (pid) {
            if (!marks.has(pid)) marks.set(pid, []);
            marks.get(pid).push(ev);
          });
        });
      }

      function show(id) {
        focus = id;
        if (!state.timeline) {
          if (loading) return;
          loading = Promise.all([
            fetch('timeline.json').then(function (r) { return r.json(); }),
            state.index ? Promise.resolve(state.index) : fetch('index.json').then(function (r) { return r.json(); })
          ]).then(function (loaded) {
            state.timeline = loaded[0];
            if (!state.index) {
              state.index = loaded[1];
              state.index.forEach(function (p) { people.set(p.id, p); });
            }
            loading = null;
            show(focus);
          }).catch(function () {
            loading = null;
            tlHead.textContent = 'Could not load the timeline data.';
          });
          return;
        }
        if (focus && !state.timeline.people[focus]) {
          tlHead.textContent = 'No such person: ' + focus;
          ready = false;
          return;
        }
        prepare();
        header();
        var empty = !rows().length;
        emptyEl.hidden = !empty;
        setHidden(tlSvg, empty);
        $('timeline-scroll').hidden = empty;
        tlHead.querySelector('.tl-controls').hidden = empty;
        ready = !empty;
        if (empty) {
          if (focus) showPanel(focus);
          return;
        }
        if (!shown) {
          fit();
          shown = true;
        }
        if (focus) {
          state.selected = focus;
          var at = rowIndex.get(focus);
          if (at !== undefined) scrollToRow(at);
          else undated.open = true;
          showPanel(focus);
        }
        render();
      }
      var shown = false;

      function refresh() {
        if (state.view === 'timeline' && state.timeline) render();
      }

      tlSvg.addEventListener('pointerdown', function (e) {
        drag = { x: e.clientX, y: e.clientY, tx: tx, ty: ty };
        moved = false;
      });
      window.addEventListener('pointermove', function (e) {
        if (!drag || state.view !== 'timeline') return;
        var dx = e.clientX - drag.x, dy = e.clientY - drag.y;
        if (Math.abs(dx) + Math.abs(dy) > 4) moved = true;
        tx = drag.tx + dx;
        ty = drag.ty + dy;
        render();
      });
      function endDrag() {
        drag = null;
        setTimeout(function () { moved = false; }, 0);
      }
      window.addEventListener('pointerup', endDrag);
      window.addEventListener('pointercancel', endDrag);
      tlSvg.addEventListener('click', function () {
        if (!moved && !panel.hidden) closePanel();
      });
      tlSvg.addEventListener('wheel', function (e) {
        e.preventDefault();
        var px = e.clientX - tlSvg.getBoundingClientRect().left;
        if (e.ctrlKey || e.metaKey) {
          zoomBy(Math.exp(-e.deltaY * 0.01), px); // pinch / Ctrl+wheel
        } else if (e.shiftKey || Math.abs(e.deltaX) > Math.abs(e.deltaY)) {
          panBy(-(e.deltaX || e.deltaY)); // sideways swipe / Shift+wheel
        } else {
          ty -= e.deltaY; // a plain wheel scrolls the rows
          render();
        }
      }, { passive: false });

      document.addEventListener('keydown', function (e) {
        if (state.view !== 'timeline' || e.altKey || e.ctrlKey || e.metaKey) return;
        var tag = e.target && e.target.tagName;
        if (tag === 'INPUT' || tag === 'TEXTAREA') return;
        var handled = true;
        if (e.key === 'ArrowLeft') panBy(viewWidth() * 0.2);
        else if (e.key === 'ArrowRight') panBy(-viewWidth() * 0.2);
        else if (e.key === 'ArrowUp') { ty += ROW_H * 3; render(); }
        else if (e.key === 'ArrowDown') { ty -= ROW_H * 3; render(); }
        else if (e.key === '+' || e.key === '=') zoomBy(1.4);
        else if (e.key === '-' || e.key === '_') zoomBy(1 / 1.4);
        else if (e.key === 'Home') centerOnYear(bounds.min + (viewWidth() / 2) / pxPerYear);
        else if (e.key === 'End') centerOnYear(bounds.max - (viewWidth() / 2) / pxPerYear);
        else handled = false;
        if (handled) e.preventDefault();
      });

      // scrollbar: click or drag the track to move along the timeline
      var scrollEl = $('timeline-scroll');
      var scrollDrag = false;
      function scrollTo(e) {
        var rect = scrollEl.getBoundingClientRect();
        var frac = Math.min(1, Math.max(0, (e.clientX - rect.left) / rect.width));
        centerOnYear(bounds.min + frac * (bounds.max - bounds.min));
      }
      scrollEl.addEventListener('pointerdown', function (e) {
        scrollDrag = true;
        scrollTo(e);
      });
      window.addEventListener('pointermove', function (e) { if (scrollDrag) scrollTo(e); });
      window.addEventListener('pointerup', function () { scrollDrag = false; });
      window.addEventListener('resize', function () { refresh(); });

      return { show: show, refresh: refresh };
    })();

    // ---------------------------------------------------------------- search

    function showResults(query) {
      results.textContent = '';
      var q = query.trim().toLowerCase();
      if (!q || !state.index) {
        results.hidden = true;
        return;
      }
      state.index.filter(function (p) { return p.name.toLowerCase().indexOf(q) !== -1; }).slice(0, 10).forEach(function (p) {
        var li = document.createElement('li');
        var b = document.createElement('button');
        b.type = 'button';
        b.textContent = p.name + (p.years ? ' (' + p.years + ')' : '');
        b.addEventListener('click', function () {
          results.hidden = true;
          search.value = '';
          if (state.view === 'focus' && tree.has(p.id)) tree.select(p.id, true, false);
          else go(state.view, p.id);
        });
        li.appendChild(b);
        results.appendChild(li);
      });
      results.hidden = results.childElementCount === 0;
    }
    search.addEventListener('input', function () { showResults(search.value); });
    search.addEventListener('focus', function () {
      if (!state.index) tree.ensure();
    });

    window.addEventListener('hashchange', route);
    tree.ensure();
    if (parseRoute(location.hash).view === 'timeline') route();
  }

  var api = {
    buildGrid: buildGrid,
    queryGrid: queryGrid,
    boundsOf: boundsOf,
    wrapName: wrapName,
    parseRoute: parseRoute,
    visibleRange: visibleRange,
    spanBar: spanBar,
    barRect: barRect,
    axisBounds: axisBounds,
    rowWindow: rowWindow,
    nodeTextBox: nodeTextBox,
    initialView: initialView,
    lodFor: lodFor,
    zoomAt: zoomAt,
    legendEnds: legendEnds,
    thumbGeometry: thumbGeometry,
    routeHash: routeHash,
    yearPosition: yearPosition,
    relatedFor: relatedFor,
    relationNote: relationNote,
    legendFor: legendFor,
    lineageFor: lineageFor,
    lineageShade: lineageShade,
    generationLabel: generationLabel
  };
  if (typeof module !== 'undefined' && module.exports) {
    module.exports = api;
  } else if (typeof document !== 'undefined') {
    root.famsiteViewer = api;
    if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init);
    else init();
  }
})(typeof window !== 'undefined' ? window : this);
