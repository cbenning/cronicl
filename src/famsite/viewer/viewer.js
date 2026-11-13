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
  function packLanes(items, gap) {
    var order = items.map(function (_, i) { return i; }).sort(function (a, b) {
      return items[a].start - items[b].start || a - b;
    });
    var laneEnds = [];
    var lanes = new Array(items.length);
    order.forEach(function (i) {
      for (var lane = 0; lane < laneEnds.length; lane++) {
        if (items[i].start >= laneEnds[lane] + gap) {
          lanes[i] = lane;
          laneEnds[lane] = items[i].end;
          return;
        }
      }
      lanes[i] = laneEnds.length;
      laneEnds.push(items[i].end);
    });
    return lanes;
  }

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

  var GLYPH = { birth: '●', marriage: '⚭', partnership: '⚭', divorce: '⚮', death: '✝' };

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
      view: 'tree', selected: null, layout: null, index: null, timeline: null, personEvents: {},
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
      tabs.forEach(function (a) {
        var active = a.getAttribute('data-view') === (treeLike ? 'tree' : view);
        if (active) a.setAttribute('aria-current', 'page');
        else a.removeAttribute('aria-current');
      });
    }

    function route() {
      var r = parseRoute(location.hash);
      showView(r.view);
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
          avatar.textContent = p.initials || '';
          function para(cls, text) {
            if (!text) return;
            var el = document.createElement('p');
            el.className = cls;
            el.textContent = text;
            titleBox.appendChild(el);
          }
          para('years', p.years);
          var places = [];
          if (p.birth && p.birth.place) places.push('Born ' + p.birth.place);
          if (p.death && p.death.place) places.push('Died ' + p.death.place);
          para('places', places.join(' · '));
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
        var wrapped = wrapName(info.name, n.w - 2 * NODE_PAD, measureName, 2);
        var tip = svgEl('title');
        tip.textContent = info.name + (info.years ? ' (' + info.years + ')' : '') +
          (linEntry ? ' · ' + generationLabel(linEntry.d) + (linEntry.partner ? ' (partner)' : '') : '');
        g.appendChild(tip);
        var top = wrapped.lines.length > 1 ? n.y + 20 : n.y + 26;
        wrapped.lines.forEach(function (line, i) {
          var t = svgEl('text', { x: n.x + n.w / 2, y: top + i * 16, 'text-anchor': 'middle', 'class': 'name' });
          t.textContent = line;
          g.appendChild(t);
        });
        var years = svgEl('text', {
          x: n.x + n.w / 2,
          y: n.y + n.h - 10,
          'text-anchor': 'middle',
          'class': 'years'
        });
        years.textContent = info.years;
        g.appendChild(years);
        g.addEventListener('click', function (e) {
          e.stopPropagation();
          if (!moved) select(id, false, false);
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
          var text = svgEl('text', { x: label.x, y: label.y, 'class': 'group-label', 'font-size': labelSize() });
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
        var radius = dotRadius();
        var size = labelSize();
        live.forEach(function (el, key) {
          if (key.slice(0, 2) === 'u:') el.setAttribute('r', radius);
          else if (key.slice(0, 2) === 'l:') el.setAttribute('font-size', size);
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
          [
            lin.up ? 'Oldest · −' + lin.up : '',
            'Selected',
            lin.down ? 'Youngest · +' + lin.down : ''
          ].forEach(function (text) {
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
        scale = Math.min(r.width / b.w, r.height / b.h, 1);
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
        if (center) centerOn(id);
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
          boxes.push({ id: 'l:' + i, x: l.x, y: l.y - 16, w: 320, h: 24 });
        });
        grid = buildGrid(boxes, CELL);
        fit();
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

      treeSvg.addEventListener('pointerdown', function (e) {
        drag = { x: e.clientX, y: e.clientY, tx: tx, ty: ty };
        moved = false;
      });
      window.addEventListener('pointermove', function (e) {
        if (!drag) return;
        var dx = e.clientX - drag.x, dy = e.clientY - drag.y;
        if (Math.abs(dx) + Math.abs(dy) > 4) moved = true;
        tx = drag.tx + dx;
        ty = drag.ty + dy;
        render();
      });
      window.addEventListener('pointerup', function () {
        drag = null;
        setTimeout(function () { moved = false; }, 0);
      });
      treeSvg.addEventListener('click', function () {
        if (!moved && !panel.hidden) closePanel();
      });
      treeSvg.addEventListener('wheel', function (e) {
        e.preventDefault();
        var r = treeSvg.getBoundingClientRect();
        var px = e.clientX - r.left, py = e.clientY - r.top;
        var next = Math.min(3, Math.max(0.1, scale * Math.exp(-e.deltaY * 0.0015)));
        tx = px - (px - tx) * (next / scale);
        ty = py - (py - ty) * (next / scale);
        scale = next;
        render();
      }, { passive: false });
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
      var LANE_H = 24;
      var focus = null;
      var items = [];
      var lanes = [];
      var pxPerYear = 14;
      var originYear = 0;
      var tx = 40, ty = 0;
      var drag = null;
      var moved = false;
      var loading = null;
      var axisLayer = svgEl('g');
      var stemLayer = svgEl('g');
      var eventLayer = svgEl('g');
      var rootG = svgEl('g');
      rootG.appendChild(stemLayer);
      rootG.appendChild(eventLayer);
      tlSvg.appendChild(axisLayer);
      tlSvg.appendChild(rootG);

      function xOf(ev) { return (yearPosition(ev) - originYear) * pxPerYear + tx; }

      function buildItems() {
        var data = state.timeline;
        var rows;
        if (focus) {
          // a person's rows come from their own payload: timeline.json does not repeat them per person
          rows = (state.personEvents[focus] || []).map(function (r) {
            return { event: r, role: r.role, text: r.text, age: r.age, approx: r.age_approx };
          });
        } else {
          rows = data.events.map(function (ev) { return { event: ev, role: null, text: ev.text }; });
        }
        items = rows.map(function (row) {
          var ev = row.event;
          var text = row.text;
          if (row.age !== null && row.age !== undefined) text += ' (age ' + (row.approx ? '~' : '') + row.age + ')';
          var label = GLYPH[ev.type] + ' ' + text;
          if (row.role && row.role !== 'self') label = label + ' · ' + row.role;
          var measure = row.role === 'self' ? measureLabelBold : measureLabel;
          return { ev: ev, role: row.role, label: label, width: measure(label) + 16 };
        });
      }

      function layoutLanes() {
        lanes = packLanes(
          items.map(function (it) {
            var x = (yearPosition(it.ev) - originYear) * pxPerYear;
            return { start: x, end: x + it.width };
          }),
          6
        );
      }

      function ticks(minX, maxX) {
        var steps = [1, 2, 5, 10, 20, 50, 100, 200, 500];
        var step = steps[steps.length - 1];
        for (var i = 0; i < steps.length; i++) {
          if (steps[i] * pxPerYear >= 70) { step = steps[i]; break; }
        }
        var first = Math.floor(((minX - tx) / pxPerYear + originYear) / step) * step;
        var last = Math.ceil(((maxX - tx) / pxPerYear + originYear) / step) * step;
        var out = [];
        for (var y = first; y <= last; y += step) out.push(y);
        return out;
      }

      function render() {
        if (!state.timeline) return;
        var r = tlSvg.getBoundingClientRect();
        axisLayer.textContent = '';
        stemLayer.textContent = '';
        eventLayer.textContent = '';
        axisLayer.appendChild(svgEl('rect', { x: 0, y: 0, width: r.width, height: AXIS_H, 'class': 'axis-bg' }));
        ticks(-80, r.width + 80).forEach(function (year) {
          var x = (year - originYear) * pxPerYear + tx;
          axisLayer.appendChild(svgEl('line', { x1: x, x2: x, y1: AXIS_H - 8, y2: r.height, 'class': 'tick' }));
          var label = svgEl('text', { x: x + 4, y: AXIS_H - 12, 'class': 'tick-label' });
          label.textContent = String(year);
          axisLayer.appendChild(label);
        });
        rootG.setAttribute('transform', 'translate(0 ' + ty + ')');
        items.forEach(function (it, i) {
          var x = xOf(it.ev);
          if (x + it.width < -40 || x > r.width + 40) return;
          var y = AXIS_H + 14 + lanes[i] * LANE_H;
          var cls = 'ev ' + it.ev.type + (it.role === 'self' ? ' self' : '') +
            (state.selected && it.ev.people.indexOf(state.selected) !== -1 ? ' selected' : '');
          stemLayer.appendChild(svgEl('line', { x1: x, x2: x, y1: AXIS_H - ty, y2: y, 'class': 'stem' }));
          var g = svgEl('g', { 'class': cls, transform: 'translate(' + x + ' ' + y + ')' });
          g.appendChild(svgEl('rect', { x: -4, y: -11, width: it.width, height: 20, rx: 4 }));
          var t = svgEl('text', { x: 2, y: 4 });
          t.textContent = it.label;
          g.appendChild(t);
          var tip = svgEl('title');
          tip.textContent = it.ev.date + (it.ev.place ? ' — ' + it.ev.place : '');
          g.appendChild(tip);
          g.addEventListener('click', function (e) {
            e.stopPropagation();
            if (!moved) showPanel(it.ev.people[0]);
            refresh();
          });
          eventLayer.appendChild(g);
        });
        updateControls();
      }

      // ---- movement: every way of panning/zooming goes through these two
      function totalRange() {
        if (!items.length) return { min: originYear, max: originYear + 1 };
        var years = items.map(function (it) { return it.ev.year; });
        return { min: Math.min.apply(null, years) - 1, max: Math.max.apply(null, years) + 2 };
      }

      function viewWidth() { return tlSvg.getBoundingClientRect().width; }

      function panBy(dx) {
        tx += dx;
        render();
      }

      function zoomBy(factor, anchorX) {
        var anchor = anchorX === undefined ? viewWidth() / 2 : anchorX;
        var yearAt = (anchor - tx) / pxPerYear + originYear;
        pxPerYear = Math.min(200, Math.max(1, pxPerYear * factor));
        tx = anchor - (yearAt - originYear) * pxPerYear;
        layoutLanes();
        render();
      }

      function centerOnYear(year) {
        tx = viewWidth() / 2 - (year - originYear) * pxPerYear;
        render();
      }

      function updateControls() {
        var readout = $('tl-range');
        var scroll = $('timeline-scroll');
        if (!readout || !scroll || !items.length) return;
        var vis = visibleRange(tx, pxPerYear, originYear, viewWidth());
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

      function fit() {
        var r = tlSvg.getBoundingClientRect();
        var years = items.map(function (it) { return it.ev.year; });
        var min = Math.min.apply(null, years), max = Math.max.apply(null, years);
        originYear = min - 1;
        var span = Math.max(max - min + 2, 2);
        // leave room for the widest label among the latest events, not a fixed guess
        var tail = items.reduce(function (w, it) { return it.ev.year >= max - 1 ? Math.max(w, it.width) : w; }, 0);
        pxPerYear = Math.min(60, Math.max(3, (r.width - 40 - tail - 24) / span));
        tx = 40;
        ty = 0;
      }

      function header() {
        tlHead.textContent = '';
        var h = document.createElement('h2');
        if (focus) {
          var person = state.timeline.people[focus];
          h.textContent = (person ? person.name : focus) + ' — timeline';
          tlHead.appendChild(h);
          var back = link(routeHash('timeline', null), '← All family events');
          back.className = 'back';
          tlHead.appendChild(back);
        } else {
          h.textContent = 'Family timeline';
          tlHead.appendChild(h);
        }
        var controls = document.createElement('span');
        controls.className = 'tl-controls';
        controls.appendChild(button('tl-left', '◀', 'Earlier (←)', function () { panBy(viewWidth() * 0.25); }));
        controls.appendChild(button('tl-right', '▶', 'Later (→)', function () { panBy(-viewWidth() * 0.25); }));
        controls.appendChild(button('tl-zoom-out', '−', 'Zoom out (-)', function () { zoomBy(1 / 1.4); }));
        controls.appendChild(button('tl-zoom-in', '+', 'Zoom in (+)', function () { zoomBy(1.4); }));
        controls.appendChild(button('tl-fit', 'Fit', 'Fit everything (Home)', function () {
          fit();
          layoutLanes();
          render();
        }));
        var readout = document.createElement('span');
        readout.id = 'tl-range';
        readout.className = 'hint';
        controls.appendChild(readout);
        tlHead.appendChild(controls);
        undated.hidden = !!focus || !state.timeline.undated.length;
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
          items = [];
          render();
          return;
        }
        if (focus && !state.personEvents[focus]) {
          var wanted = focus;
          tlHead.textContent = 'Loading…';
          fetch('data/people/' + wanted + '.json')
            .then(function (r) { return r.json(); })
            .then(function (p) {
              state.personEvents[wanted] = p.events || [];
              if (focus === wanted) show(wanted);
            })
            .catch(function () { tlHead.textContent = 'Could not load this person.'; });
          return;
        }
        header();
        $('timeline-scroll').hidden = false;
        buildItems();
        if (!items.length) {
          tlHead.appendChild(document.createTextNode(' No dated events to show.'));
        }
        fit();
        layoutLanes();
        render();
      }

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
        ty = Math.min(0, drag.ty + dy);
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
          zoomBy(Math.exp(-e.deltaY * 0.0015), px);
        }
      }, { passive: false });

      document.addEventListener('keydown', function (e) {
        if (state.view !== 'timeline' || e.altKey || e.ctrlKey || e.metaKey) return;
        var tag = e.target && e.target.tagName;
        if (tag === 'INPUT' || tag === 'TEXTAREA') return;
        var handled = true;
        if (e.key === 'ArrowLeft') panBy(viewWidth() * 0.2);
        else if (e.key === 'ArrowRight') panBy(-viewWidth() * 0.2);
        else if (e.key === '+' || e.key === '=') zoomBy(1.4);
        else if (e.key === '-' || e.key === '_') zoomBy(1 / 1.4);
        else if (e.key === 'Home') {
          var t = totalRange();
          centerOnYear(t.min + (viewWidth() / 2) / pxPerYear);
        } else if (e.key === 'End') {
          var t2 = totalRange();
          centerOnYear(t2.max - (viewWidth() / 2) / pxPerYear);
        } else handled = false;
        if (handled) e.preventDefault();
      });

      // scrollbar: click or drag the track to move along the timeline
      var scrollEl = $('timeline-scroll');
      var scrollDrag = false;
      function scrollTo(e) {
        var rect = scrollEl.getBoundingClientRect();
        var frac = Math.min(1, Math.max(0, (e.clientX - rect.left) / rect.width));
        var t = totalRange();
        centerOnYear(t.min + frac * (t.max - t.min));
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
    packLanes: packLanes,
    parseRoute: parseRoute,
    visibleRange: visibleRange,
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
