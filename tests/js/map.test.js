const test = require('node:test');
const assert = require('node:assert');
const m = require('../../src/cronicl/site/viewer/map.js');

const near = (a, b, eps) => assert.ok(Math.abs(a - b) <= (eps || 1e-6), `${a} vs ${b}`);

test('project and unproject are inverses', () => {
  [[0, 0], [51.5072, -0.1276], [-33.9, 151.2], [84, 179.9], [-84, -179.9]].forEach(([lat, lon]) => {
    [1, 5, 12, 18].forEach((z) => {
      const p = m.project(lat, lon, z), q = m.unproject(p.x, p.y, z);
      near(q.lat, lat, 1e-5); near(q.lon, lon, 1e-5);
    });
  });
});

test('the world is 256 pixels at zoom 0 and doubles each zoom; the equator and prime meridian are the middle', () => {
  const p = m.project(0, 0, 3);
  near(p.x, 1024); near(p.y, 1024);
  const corner = m.project(85.0511287798, -180, 3);
  near(corner.x, 0); near(corner.y, 0, 1e-3);
});

test('latitude is clamped at the Mercator limit and longitude wraps', () => {
  const top = m.project(90, 0, 4), limit = m.project(85.0511287798, 0, 4);
  near(top.y, limit.y);
  near(m.wrapLon(190), -170); near(m.wrapLon(-190), 170); near(m.wrapLon(540), -180 + 0); near(m.wrapLon(0), 0);
  assert.ok(Number.isFinite(m.project(-90, 0, 2).y));
});

test('tile addresses wrap east-west and have none above or below the world', () => {
  const t = 'https://t.example/{z}/{x}/{y}.png';
  assert.strictEqual(m.tileUrl(t, 2, 5, 1), 'https://t.example/2/1/1.png');
  assert.strictEqual(m.tileUrl(t, 2, -1, 1), 'https://t.example/2/3/1.png');
  assert.strictEqual(m.tileUrl(t, 2, 0, -1), null);
  assert.strictEqual(m.tileUrl(t, 2, 0, 4), null);
});

test('only well-formed tile templates are accepted', () => {
  assert.ok(m.validTemplate('https://t.example/{z}/{x}/{y}.png'));
  assert.ok(m.validTemplate('http://127.0.0.1:1/{z}/{x}/{y}.png'));
  ['javascript:{z}{x}{y}', 'https://t.example/{z}/{x}.png', 'https://t/{z}/{x}/{y}/{s}', 'https://t/{z}/{x}/{y}" onload=1', '', null, 'ftp://t/{z}/{x}/{y}']
    .forEach((bad) => assert.ok(!m.validTemplate(bad), String(bad)));
});

test('tilesFor covers the viewport and positions tiles relative to it', () => {
  const tiles = m.tilesFor({ lat: 0, lon: 0 }, 2, 400, 300);
  const minLeft = Math.min(...tiles.map((t) => t.left)), maxRight = Math.max(...tiles.map((t) => t.left + 256));
  assert.ok(minLeft <= 0 && maxRight >= 400);
  assert.ok(Math.min(...tiles.map((t) => t.top)) <= 0 && Math.max(...tiles.map((t) => t.top + 256)) >= 300);
  assert.strictEqual(new Set(tiles.map((t) => t.key)).size, tiles.length);
});

test('a marker at the centre is in the middle of the viewport; the nearest copy of the world is used', () => {
  const c = { lat: 10, lon: 179 };
  const mid = m.markerPosition(10, 179, c, 5, 800, 600);
  near(mid.left, 400, 1e-6); near(mid.top, 300, 1e-6);
  const across = m.markerPosition(10, -179, c, 5, 800, 600); // two degrees east across the date line
  assert.ok(across.left > 400 && across.left < 400 + 200, String(across.left));
});

test('fit shows every point, centres them, and a single point is a city-level zoom', () => {
  const pts = [{ lat: 51.5, lon: -0.1 }, { lat: 53.55, lon: 9.99 }, { lat: 48.85, lon: 2.35 }];
  const f = m.fit(pts, 800, 500, 40);
  pts.forEach((p) => {
    const pos = m.markerPosition(p.lat, p.lon, f.center, f.z, 800, 500);
    assert.ok(pos.left >= 40 - 1 && pos.left <= 760 + 1 && pos.top >= 40 - 1 && pos.top <= 460 + 1, JSON.stringify(pos));
  });
  assert.strictEqual(m.fit([{ lat: 1, lon: 2 }], 800, 500, 40).z, 10);
  assert.deepStrictEqual(m.fit([], 800, 500, 40).z, m.MIN_Z);
});

test('the scheme of a tile template is not case sensitive, as in the build check', () => {
  assert.ok(m.validTemplate('HTTPS://t.example/{z}/{x}/{y}.png'));
});
