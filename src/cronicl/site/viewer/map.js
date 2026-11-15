/* The map page: a small slippy map (Web Mercator tiles, pan, zoom, markers) in plain ES5. No library. */
(function (root) {
  'use strict';
  var TILE = 256, MAX_LAT = 85.0511287798, MIN_Z = 1, MAX_Z = 18;

  function clamp(v, lo, hi) { return Math.max(lo, Math.min(hi, v)); }
  function worldSize(z) { return TILE * Math.pow(2, z); }
  function wrapLon(lon) { return ((((lon + 180) % 360) + 360) % 360) - 180; }

  // Pixel position in the whole world at zoom z.
  function project(lat, lon, z) {
    var s = worldSize(z), rad = clamp(lat, -MAX_LAT, MAX_LAT) * Math.PI / 180;
    return { x: (lon + 180) / 360 * s, y: (1 - Math.log(Math.tan(rad) + 1 / Math.cos(rad)) / Math.PI) / 2 * s };
  }
  function unproject(x, y, z) {
    var s = worldSize(z), n = Math.PI * (1 - 2 * y / s);
    return { lat: 180 / Math.PI * Math.atan(0.5 * (Math.exp(n) - Math.exp(-n))), lon: wrapLon(x / s * 360 - 180) };
  }

  // The tile address for a template; x wraps around the world, y outside the world has no tile.
  function tileUrl(template, z, x, y) {
    var n = Math.pow(2, z);
    if (y < 0 || y >= n) return null;
    var wrapped = ((x % n) + n) % n;
    return template.replace('{z}', z).replace('{x}', wrapped).replace('{y}', y);
  }

  function validTemplate(t) {
    return typeof t === 'string' && /^https?:\/\//i.test(t) && !/[\s"'<>`\\]/.test(t) &&
      t.indexOf('{z}') > -1 && t.indexOf('{x}') > -1 && t.indexOf('{y}') > -1 && (t.match(/\{[^{}]*\}/g) || []).length === 3;
  }

  // The tiles that cover a w x h viewport centred on `center` at zoom z, with their pixel offsets in the viewport.
  function tilesFor(center, z, w, h) {
    var c = project(center.lat, center.lon, z), left = c.x - w / 2, top = c.y - h / 2, out = [];
    for (var ty = Math.floor(top / TILE); ty <= Math.floor((top + h) / TILE); ty++) {
      for (var tx = Math.floor(left / TILE); tx <= Math.floor((left + w) / TILE); tx++) {
        out.push({ key: z + '/' + tx + '/' + ty, z: z, x: tx, y: ty, left: tx * TILE - left, top: ty * TILE - top });
      }
    }
    return out;
  }

  // Where a point falls in the viewport, taking the nearest copy of the world so the date line does not matter.
  function markerPosition(lat, lon, center, z, w, h) {
    var c = project(center.lat, center.lon, z), p = project(lat, lon, z), s = worldSize(z), dx = p.x - c.x;
    if (dx > s / 2) dx -= s; else if (dx < -s / 2) dx += s;
    return { left: w / 2 + dx, top: h / 2 + (p.y - c.y) };
  }

  // The centre and zoom that show every point in a w x h viewport.
  function fit(points, w, h, pad) {
    if (!points.length) return { center: { lat: 20, lon: 0 }, z: MIN_Z };
    var minLat = 90, maxLat = -90, minLon = 180, maxLon = -180, i;
    for (i = 0; i < points.length; i++) {
      minLat = Math.min(minLat, points[i].lat); maxLat = Math.max(maxLat, points[i].lat);
      minLon = Math.min(minLon, points[i].lon); maxLon = Math.max(maxLon, points[i].lon);
    }
    var z, a, b;
    for (z = MAX_Z; z > MIN_Z; z--) {
      a = project(maxLat, minLon, z); b = project(minLat, maxLon, z);
      if (b.x - a.x <= w - 2 * pad && b.y - a.y <= h - 2 * pad) break;
    }
    if (minLat === maxLat && minLon === maxLon) z = Math.min(z, 10);
    a = project(maxLat, minLon, z); b = project(minLat, maxLon, z);
    return { center: unproject((a.x + b.x) / 2, (a.y + b.y) / 2, z), z: z };
  }

  var api = { project: project, unproject: unproject, tileUrl: tileUrl, validTemplate: validTemplate, tilesFor: tilesFor,
    markerPosition: markerPosition, fit: fit, wrapLon: wrapLon, MIN_Z: MIN_Z, MAX_Z: MAX_Z, TILE: TILE };

  function start(doc) {
    var box = doc.getElementById('map');
    if (!box) return;
    var template = box.getAttribute('data-tiles'), prefix = box.getAttribute('data-root') || '';
    var status = doc.getElementById('map-status'), list = doc.getElementById('map-list');
    function say(text) { if (status) { status.textContent = text; status.hidden = !text; } }
    if (!validTemplate(template)) { say('The map is not set up correctly.'); return; }
    var view = doc.createElement('div'); view.className = 'map-view'; view.tabIndex = 0;
    view.setAttribute('role', 'application'); view.setAttribute('aria-label', 'Map of places');
    var tileLayer = doc.createElement('div'), markerLayer = doc.createElement('div');
    tileLayer.className = 'map-tiles'; markerLayer.className = 'map-markers';
    var controls = doc.createElement('div'); controls.className = 'map-controls';
    var credit = doc.createElement('div'); credit.className = 'map-attribution';
    credit.textContent = box.getAttribute('data-attribution') || '';
    view.appendChild(tileLayer); view.appendChild(markerLayer); view.appendChild(controls); view.appendChild(credit);
    box.appendChild(view);
    var state = { center: { lat: 20, lon: 0 }, z: MIN_Z }, markers = [], tiles = {}, els = {}, open = null;

    function size() { return { w: view.clientWidth || 800, h: view.clientHeight || 500 }; }
    function render() {
      var s = size(), wanted = {}, needed = tilesFor(state.center, state.z, s.w, s.h), i, t, img;
      for (i = 0; i < needed.length; i++) {
        t = needed[i]; wanted[t.key] = true;
        img = tiles[t.key];
        if (!img) {
          var url = tileUrl(template, t.z, t.x, t.y);
          if (!url) continue;
          img = doc.createElement('img'); img.alt = ''; img.draggable = false; img.width = TILE; img.height = TILE;
          img.className = 'map-tile'; img.onerror = function () { this.style.visibility = 'hidden'; };
          img.src = url; tileLayer.appendChild(img); tiles[t.key] = img;
        }
        img.style.left = Math.round(t.left) + 'px'; img.style.top = Math.round(t.top) + 'px';
      }
      for (var key in tiles) if (!wanted[key]) { tileLayer.removeChild(tiles[key]); delete tiles[key]; }
      for (i = 0; i < markers.length; i++) {
        var p = markerPosition(markers[i].lat, markers[i].lon, state.center, state.z, s.w, s.h), el = els[markers[i].slug];
        el.style.left = Math.round(p.left) + 'px'; el.style.top = Math.round(p.top) + 'px';
      }
    }
    function setView(center, z) {
      state.z = clamp(Math.round(z), MIN_Z, MAX_Z);
      state.center = { lat: clamp(center.lat, -MAX_LAT, MAX_LAT), lon: wrapLon(center.lon) };
      for (var key in tiles) { tileLayer.removeChild(tiles[key]); delete tiles[key]; }
      render();
    }
    function panBy(dx, dy) {
      var c = project(state.center.lat, state.center.lon, state.z);
      state.center = unproject(c.x - dx, clamp(c.y - dy, 0, worldSize(state.z)), state.z);
      render();
    }
    function zoomAt(delta, px, py) {
      var s = size(), z = clamp(state.z + delta, MIN_Z, MAX_Z);
      if (z === state.z) return;
      var c = project(state.center.lat, state.center.lon, state.z);
      var cx = px === undefined ? s.w / 2 : px, cy = py === undefined ? s.h / 2 : py;
      var under = unproject(c.x + cx - s.w / 2, c.y + cy - s.h / 2, state.z);
      var u = project(under.lat, under.lon, z);
      setView(unproject(u.x - (cx - s.w / 2), u.y - (cy - s.h / 2), z), z);
    }
    function showFit() { var s = size(); var f = fit(markers, s.w, s.h, 40); setView(f.center, f.z); }

    function button(label, text, handler) {
      var b = doc.createElement('button'); b.type = 'button'; b.textContent = text; b.setAttribute('aria-label', label);
      b.addEventListener('click', handler); controls.appendChild(b);
    }
    button('Zoom in', '+', function () { zoomAt(1); });
    button('Zoom out', '−', function () { zoomAt(-1); });
    button('Show all places', 'Fit', showFit);

    function show(marker) {
      open = marker;
      if (!list) return;
      list.hidden = false; list.textContent = '';
      var h = doc.createElement('h2'); h.textContent = marker.name; list.appendChild(h);
      var ul = doc.createElement('ul');
      marker.entries.forEach(function (e) {
        var li = doc.createElement('li'), a = doc.createElement('a');
        a.href = prefix + 'p/' + encodeURIComponent(e.id) + '/'; a.textContent = e.name;
        li.appendChild(a); li.appendChild(doc.createTextNode(' — ' + e.what + (e.when ? ' ' + e.when : '')));
        ul.appendChild(li);
      });
      list.appendChild(ul);
      if (root.history && root.history.replaceState) root.history.replaceState(null, '', '#' + marker.slug);
    }

    var drag = null;
    view.addEventListener('pointerdown', function (e) {
      if (e.target.closest && e.target.closest('button')) return;
      drag = { x: e.clientX, y: e.clientY, moved: false }; view.setPointerCapture && view.setPointerCapture(e.pointerId);
      view.classList.add('dragging');
    });
    view.addEventListener('pointermove', function (e) {
      if (!drag) return;
      var dx = e.clientX - drag.x, dy = e.clientY - drag.y;
      if (dx || dy) { drag.moved = true; panBy(dx, dy); drag.x = e.clientX; drag.y = e.clientY; }
    });
    function stop() { drag = null; view.classList.remove('dragging'); }
    view.addEventListener('pointerup', stop); view.addEventListener('pointercancel', stop);
    var lastWheel = 0;
    view.addEventListener('wheel', function (e) {
      e.preventDefault();
      var now = Date.now(); if (now - lastWheel < 120) return; lastWheel = now;
      var r = view.getBoundingClientRect();
      zoomAt(e.deltaY < 0 ? 1 : -1, e.clientX - r.left, e.clientY - r.top);
    }, { passive: false });
    view.addEventListener('keydown', function (e) {
      var k = e.key;
      if (k === 'ArrowLeft') panBy(80, 0); else if (k === 'ArrowRight') panBy(-80, 0);
      else if (k === 'ArrowUp') panBy(0, 80); else if (k === 'ArrowDown') panBy(0, -80);
      else if (k === '+' || k === '=') zoomAt(1); else if (k === '-') zoomAt(-1); else if (k === '0') showFit();
      else return;
      e.preventDefault();
    });
    root.addEventListener('resize', render);

    var xhr = new XMLHttpRequest();
    xhr.open('GET', prefix + 'map.json');
    xhr.onload = function () {
      var data;
      try { data = JSON.parse(xhr.responseText); } catch (err) { data = null; }
      if (!data || !data.length) { say(data ? 'No places with coordinates yet.' : 'The map data could not be read.'); return; }
      markers = data;
      markers.forEach(function (m) {
        var el = doc.createElement('button'); el.type = 'button'; el.className = 'map-marker';
        el.textContent = String(m.entries.length);
        el.setAttribute('aria-label', m.name + ', ' + m.entries.length + (m.entries.length === 1 ? ' entry' : ' entries'));
        el.addEventListener('click', function () { show(m); });
        markerLayer.appendChild(el); els[m.slug] = el;
      });
      var wanted = (root.location.hash || '').slice(1), hit = null;
      markers.forEach(function (m) { if (m.slug === wanted) hit = m; });
      if (hit) { setView({ lat: hit.lat, lon: hit.lon }, 10); show(hit); } else showFit();
      say('');
    };
    xhr.onerror = function () { say('The map data could not be loaded.'); };
    xhr.send();
    render();
  }

  if (typeof module !== 'undefined' && module.exports) module.exports = api;
  else if (typeof document !== 'undefined') {
    root.croniclMap = api;
    if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', function () { start(document); });
    else start(document);
  }
})(typeof window !== 'undefined' ? window : this);
