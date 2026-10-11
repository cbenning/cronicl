(function (root) {
  'use strict';

  var CELL = 256;

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

  function init() {
    var NS = 'http://www.w3.org/2000/svg';
    var svg = document.getElementById('tree');
    var panel = document.getElementById('panel');
    var search = document.getElementById('search');
    var results = document.getElementById('results');
    var viewport = document.createElementNS(NS, 'g');
    var edgeLayer = document.createElementNS(NS, 'g');
    var nodeLayer = document.createElementNS(NS, 'g');
    viewport.appendChild(edgeLayer);
    viewport.appendChild(nodeLayer);
    svg.appendChild(viewport);

    var layout, index, grid;
    var nodes = new Map();
    var people = new Map();
    var live = new Map();
    var tx = 0, ty = 0, scale = 1;
    var selected = null;
    var drag = null;
    var moved = false;

    function svgEl(name, attrs) {
      var el = document.createElementNS(NS, name);
      Object.keys(attrs || {}).forEach(function (k) { el.setAttribute(k, attrs[k]); });
      return el;
    }

    function makeNode(id) {
      var n = nodes.get(id);
      var info = people.get(id) || { name: id, years: '' };
      var g = svgEl('g', { 'class': 'node' + (id === selected ? ' selected' : ''), 'data-id': id });
      g.appendChild(svgEl('rect', { x: n.x, y: n.y, width: n.w, height: n.h, rx: 6 }));
      var name = svgEl('text', { x: n.x + n.w / 2, y: n.y + 24, 'text-anchor': 'middle', 'class': 'name' });
      name.textContent = info.name;
      var years = svgEl('text', { x: n.x + n.w / 2, y: n.y + 42, 'text-anchor': 'middle', 'class': 'years' });
      years.textContent = info.years;
      g.appendChild(name);
      g.appendChild(years);
      g.addEventListener('click', function () {
        if (!moved) select(id, false);
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
        var u = layout.unions.filter(function (x) { return x.id === ref; })[0];
        var dot = svgEl('circle', { cx: u.x, cy: u.y, r: 3, 'class': 'union' });
        nodeLayer.appendChild(dot);
        return dot;
      }
      var edge = layout.edges[Number(ref)];
      var line = svgEl('polyline', {
        points: edge.points.map(function (p) { return p.join(','); }).join(' '),
        'class': 'edge ' + edge.kind,
        fill: 'none'
      });
      edgeLayer.appendChild(line);
      return line;
    }

    function render() {
      if (!grid) return;
      var r = svg.getBoundingClientRect();
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
    }

    function fit() {
      var r = svg.getBoundingClientRect();
      var b = layout.bounds;
      scale = Math.min(r.width / b.w, r.height / b.h, 1);
      if (!isFinite(scale) || scale <= 0) scale = 1;
      tx = (r.width - b.w * scale) / 2;
      ty = Math.max(0, (r.height - b.h * scale) / 2);
    }

    function centerOn(id) {
      var n = nodes.get(id);
      if (!n) return;
      var r = svg.getBoundingClientRect();
      tx = r.width / 2 - (n.x + n.w / 2) * scale;
      ty = r.height / 2 - (n.y + n.h / 2) * scale;
    }

    function link(id, name) {
      var a = document.createElement('a');
      a.href = '#/' + id;
      a.textContent = name;
      return a;
    }

    function relatives(title, list) {
      if (!list || !list.length) return null;
      var wrap = document.createElement('div');
      var h = document.createElement('h3');
      h.textContent = title;
      var ul = document.createElement('ul');
      list.forEach(function (rel) {
        var li = document.createElement('li');
        li.appendChild(link(rel.id, rel.name));
        ul.appendChild(li);
      });
      wrap.appendChild(h);
      wrap.appendChild(ul);
      return wrap;
    }

    function showPanel(id) {
      panel.hidden = false;
      panel.textContent = 'Loading…';
      fetch('data/people/' + id + '.json')
        .then(function (r) { return r.json(); })
        .then(function (p) {
          if (selected !== id) return;
          panel.textContent = '';
          var h = document.createElement('h2');
          h.textContent = p.name;
          panel.appendChild(h);
          if (p.years) {
            var y = document.createElement('p');
            y.className = 'years';
            y.textContent = p.years;
            panel.appendChild(y);
          }
          if (p.bodyHtml) {
            var body = document.createElement('div');
            body.innerHTML = p.bodyHtml;
            panel.appendChild(body);
          }
          [['Parents', p.parents], ['Spouses', p.spouses], ['Children', p.children]].forEach(function (pair) {
            var section = relatives(pair[0], pair[1]);
            if (section) panel.appendChild(section);
          });
          var page = document.createElement('a');
          page.href = 'p/' + id + '/';
          page.textContent = 'Open page';
          panel.appendChild(page);
        })
        .catch(function () {
          panel.textContent = 'Could not load this person.';
        });
    }

    function select(id, center) {
      if (!nodes.has(id)) return;
      selected = id;
      if (location.hash !== '#/' + id) history.replaceState(null, '', '#/' + id);
      if (center) centerOn(id);
      live.forEach(function (el) { el.remove(); });
      live.clear();
      render();
      showPanel(id);
    }

    svg.addEventListener('pointerdown', function (e) {
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
    svg.addEventListener('wheel', function (e) {
      e.preventDefault();
      var r = svg.getBoundingClientRect();
      var px = e.clientX - r.left, py = e.clientY - r.top;
      var next = Math.min(3, Math.max(0.1, scale * Math.exp(-e.deltaY * 0.0015)));
      tx = px - (px - tx) * (next / scale);
      ty = py - (py - ty) * (next / scale);
      scale = next;
      render();
    }, { passive: false });
    window.addEventListener('resize', render);
    window.addEventListener('hashchange', function () {
      var id = decodeURIComponent(location.hash.replace(/^#\//, ''));
      if (id && id !== selected) select(id, true);
    });

    function showResults(query) {
      results.textContent = '';
      var q = query.trim().toLowerCase();
      if (!q || !index) {
        results.hidden = true;
        return;
      }
      index.filter(function (p) { return p.name.toLowerCase().indexOf(q) !== -1; }).slice(0, 10).forEach(function (p) {
        var li = document.createElement('li');
        var b = document.createElement('button');
        b.type = 'button';
        b.textContent = p.name + (p.years ? ' (' + p.years + ')' : '');
        b.addEventListener('click', function () {
          results.hidden = true;
          search.value = '';
          select(p.id, true);
        });
        li.appendChild(b);
        results.appendChild(li);
      });
      results.hidden = results.childElementCount === 0;
    }
    search.addEventListener('input', function () { showResults(search.value); });

    Promise.all([
      fetch('layout.json').then(function (r) { return r.json(); }),
      fetch('index.json').then(function (r) { return r.json(); })
    ]).then(function (loaded) {
      layout = loaded[0];
      index = loaded[1];
      index.forEach(function (p) { people.set(p.id, p); });
      var boxes = [];
      layout.nodes.forEach(function (n) {
        nodes.set(n.id, n);
        boxes.push({ id: 'n:' + n.id, x: n.x, y: n.y, w: n.w, h: n.h });
      });
      layout.unions.forEach(function (u) {
        boxes.push({ id: 'u:' + u.id, x: u.x - 4, y: u.y - 4, w: 8, h: 8 });
      });
      layout.edges.forEach(function (e, i) {
        var b = boundsOf(e.points);
        boxes.push({ id: 'e:' + i, x: b.x, y: b.y, w: b.w, h: b.h });
      });
      grid = buildGrid(boxes, CELL);
      fit();
      var start = decodeURIComponent(location.hash.replace(/^#\//, ''));
      if (start && nodes.has(start)) select(start, true);
      else render();
    }).catch(function () {
      svg.insertAdjacentHTML('afterend', '<p class="error">Could not load the tree data.</p>');
    });
  }

  var api = { buildGrid: buildGrid, queryGrid: queryGrid, boundsOf: boundsOf };
  if (typeof module !== 'undefined' && module.exports) {
    module.exports = api;
  } else if (typeof document !== 'undefined') {
    root.famsiteViewer = api;
    if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init);
    else init();
  }
})(typeof window !== 'undefined' ? window : this);
