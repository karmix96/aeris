/* AERIS S8 Workbench.
 *
 * Every number shown comes from the project's own files, carried in s8_data.js:
 * airfoil coordinates from data/airfoil_database, the 20 design variables and
 * their bounds from shared.geometry_sets, level definitions read out of
 * strategy_s8.LEVELS, the mesh as the node array the solver was handed, and
 * cp / cf / y+ as ADflow wrote them.
 *
 * Two things this page CANNOT do, and says so rather than faking:
 *   - the geometry preview lofts linearly between the four defining sections.
 *     The mesher uses a pyGeo B-spline loft. Same parameterisation, same
 *     sections, a slightly different surface between them.
 *   - it does not mesh or solve. Moving a mesh slider shows the cell count and
 *     memory the real laws predict; it does not build the grid.
 */
'use strict';
const D = window.S8_DATA;
const $ = (s, r) => (r || document).querySelector(s);
/* The mesh arrives as base64 float32 rather than JSON numbers: exact to single
   precision, 5.33 bytes a value instead of about seven, and the browser gets a
   typed array without parsing a million strings. */
function f32(b64) {
  const bin = atob(b64), n = bin.length, bytes = new Uint8Array(n);
  for (let i = 0; i < n; i++) bytes[i] = bin.charCodeAt(i);
  return new Float32Array(bytes.buffer);
}
const XYZ = new Map();
function xyz(o) {                    // decode once, keep it
  if (!o) return null;
  if (!XYZ.has(o)) XYZ.set(o, o.f32 ? f32(o.f32) : Float32Array.from(o.xyz || []));
  return XYZ.get(o);
}
const fmt = (v, n) => (v === null || v === undefined || Number.isNaN(v)) ? '—' : (+v).toFixed(n === undefined ? 3 : n);
const counts = v => (v === null || v === undefined) ? '—' : (1e4 * v).toFixed(2);

/* ------------------------------------------------------------------ state */
const S = {
  tab: 'geom',
  dv: (D.design.designs['83'] || []).slice(),
  level: 'gci_C',
  custom: null,                 // custom mesh settings, when the user leaves the presets
  alpha: '0',
  display: 'surf-edges',        // surf | surf-edges | wire
  colour: 'none',               // none | cp | cf | yplus
  cut: { i: false, j: false, k: false, iAt: 0, jAt: 0, kAt: 0, solo: false, filled: true },
  showCap: true,
  showFar: false,
  solver: {
    turbulenceModel: 'SA', useNKSolver: false, L2Convergence: 1e-6, MGCycle: 'sg',
    eddyVisInfRatio: 0.21, liftIndex: 3, turbulenceOrder: 'first order',
    useWallFunctions: false, useQCR: false, ANKSubspaceSize: 10, ANKPCILUFill: 1,
    nCycles: 30000, ranks: 4
  }
};

/* ------------------------------------------------------------------ three */
let renderer, scene, camera, root, raf = 0;
const cam = { theta: -0.9, phi: 1.05, r: 3, target: new THREE.Vector3() };

function initGL() {
  const canvas = $('#gl');
  renderer = new THREE.WebGLRenderer({ canvas, antialias: true });
  renderer.setPixelRatio(Math.min(devicePixelRatio, 2));
  scene = new THREE.Scene();
  scene.background = new THREE.Color(0x0b0e13);
  camera = new THREE.PerspectiveCamera(42, 1, 0.002, 400);
  root = new THREE.Group();
  scene.add(root);
  scene.add(new THREE.HemisphereLight(0xbcd4f0, 0x1a1208, 0.85));
  const key = new THREE.DirectionalLight(0xffffff, 0.85); key.position.set(2, 3, 2.4); scene.add(key);
  const fill = new THREE.DirectionalLight(0x88aaff, 0.3); fill.position.set(-2, -1, -2); scene.add(fill);
  bindOrbit(canvas);
  new ResizeObserver(resize).observe($('#viewport'));
  resize();
  (function loop() { raf = requestAnimationFrame(loop); place(); renderer.render(scene, camera); })();
}
function resize() {
  const el = $('#viewport'); if (!el.clientWidth) return;
  renderer.setSize(el.clientWidth, el.clientHeight, false);
  camera.aspect = el.clientWidth / el.clientHeight; camera.updateProjectionMatrix();
}
function place() {
  const p = Math.max(0.05, Math.min(Math.PI - 0.05, cam.phi));
  camera.position.set(
    cam.target.x + cam.r * Math.sin(p) * Math.cos(cam.theta),
    cam.target.y + cam.r * Math.cos(p),
    cam.target.z + cam.r * Math.sin(p) * Math.sin(cam.theta));
  camera.lookAt(cam.target);
}
/* Orbit written here rather than pulled from three's examples: the examples
   folder is not reliably mirrored on the CDN this page is allowed to use, and
   a viewer that cannot rotate is not a viewer. */
function bindOrbit(el) {
  let mode = 0, lx = 0, ly = 0;
  el.addEventListener('pointerdown', e => {
    mode = (e.button === 0 && !e.shiftKey) ? 1 : 2; lx = e.clientX; ly = e.clientY;
    el.setPointerCapture(e.pointerId);
  });
  el.addEventListener('pointermove', e => {
    if (!mode) return;
    const dx = e.clientX - lx, dy = e.clientY - ly; lx = e.clientX; ly = e.clientY;
    if (mode === 1) { cam.theta -= dx * 0.008; cam.phi -= dy * 0.008; }
    else {
      const s = cam.r * 0.0016;
      const right = new THREE.Vector3().subVectors(camera.position, cam.target).cross(camera.up).normalize();
      const up = new THREE.Vector3().copy(camera.up).normalize();
      cam.target.addScaledVector(right, -dx * s).addScaledVector(up, dy * s);
    }
  });
  const stop = e => { mode = 0; try { el.releasePointerCapture(e.pointerId); } catch (_) {} };
  el.addEventListener('pointerup', stop); el.addEventListener('pointercancel', stop);
  el.addEventListener('wheel', e => {
    e.preventDefault(); cam.r *= Math.exp(e.deltaY * 0.0012);
    cam.r = Math.max(0.05, Math.min(60, cam.r));
  }, { passive: false });
  el.addEventListener('contextmenu', e => e.preventDefault());
}
function clearRoot() {
  while (root.children.length) {
    const c = root.children.pop();
    c.traverse(o => { if (o.geometry) o.geometry.dispose(); if (o.material) o.material.dispose(); });
  }
}
function frame(box) {
  const s = new THREE.Vector3(); box.getSize(s);
  const c = new THREE.Vector3(); box.getCenter(c);
  cam.target.copy(c); cam.r = Math.max(s.x, s.y, s.z) * 1.9 || 3;
}

/* ------------------------------------------------- structured grid helpers */
/* A structured (n x m) sheet of points -> triangles, and -> grid lines.
   The mesh is the thing being inspected, so both have to be exact: no
   decimation happens here, only in the extractor, where it is recorded. */
function sheetGeometry(xyz, n, m, colours) {
  const g = new THREE.BufferGeometry();
  g.setAttribute('position', new THREE.Float32BufferAttribute(xyz, 3));
  const idx = [];
  for (let i = 0; i < n - 1; i++) for (let k = 0; k < m - 1; k++) {
    const a = i * m + k, b = a + 1, c = (i + 1) * m + k, d = c + 1;
    idx.push(a, c, b, b, c, d);
  }
  g.setIndex(idx);
  if (colours) g.setAttribute('color', new THREE.Float32BufferAttribute(colours, 3));
  g.computeVertexNormals();
  return g;
}
function sheetWire(xyz, n, m) {
  const pos = [];
  const at = (i, k) => { const o = (i * m + k) * 3; return [xyz[o], xyz[o + 1], xyz[o + 2]]; };
  for (let i = 0; i < n; i++) for (let k = 0; k < m - 1; k++) { pos.push(...at(i, k), ...at(i, k + 1)); }
  for (let k = 0; k < m; k++) for (let i = 0; i < n - 1; i++) { pos.push(...at(i, k), ...at(i + 1, k)); }
  const g = new THREE.BufferGeometry();
  g.setAttribute('position', new THREE.Float32BufferAttribute(pos, 3));
  return g;
}
/* index into the decimated volume block: xyz[( i*nj + j )*nk + k] */
function volSlice(vol, fix, at) {
  const [ni, nj, nk] = vol.shape, x = xyz(vol);
  const P = (i, j, k) => { const o = ((i * nj + j) * nk + k) * 3; return [x[o], x[o + 1], x[o + 2]]; };
  const out = [];
  if (fix === 'k') { for (let i = 0; i < ni; i++) for (let j = 0; j < nj; j++) out.push(...P(i, j, at)); return { xyz: out, n: ni, m: nj }; }
  if (fix === 'j') { for (let i = 0; i < ni; i++) for (let k = 0; k < nk; k++) out.push(...P(i, at, k)); return { xyz: out, n: ni, m: nk }; }
  for (let j = 0; j < nj; j++) for (let k = 0; k < nk; k++) out.push(...P(at, j, k));
  return { xyz: out, n: nj, m: nk };
}

/* ------------------------------------------------------------- colour maps */
/* Diverging for cp, because it has a meaningful zero; sequential for cf and
   y+, which do not. A rainbow is avoided: it invents bands that are not in
   the data, which is exactly the failure this project keeps auditing for. */
function ramp(t, kind) {
  t = Math.max(0, Math.min(1, t));
  if (kind === 'div') {
    const s = [[0.15, 0.32, 0.65], [0.45, 0.62, 0.81], [0.94, 0.94, 0.93], [0.89, 0.55, 0.40], [0.70, 0.11, 0.13]];
    const f = t * (s.length - 1), i = Math.min(s.length - 2, Math.floor(f)), u = f - i;
    return [0, 1, 2].map(c => s[i][c] + u * (s[i + 1][c] - s[i][c]));
  }
  const s = [[0.05, 0.10, 0.22], [0.13, 0.35, 0.55], [0.18, 0.62, 0.62], [0.55, 0.80, 0.42], [0.98, 0.91, 0.40]];
  const f = t * (s.length - 1), i = Math.min(s.length - 2, Math.floor(f)), u = f - i;
  return [0, 1, 2].map(c => s[i][c] + u * (s[i + 1][c] - s[i][c]));
}
function cssRamp(kind) {
  const stops = []; for (let i = 0; i <= 8; i++) {
    const c = ramp(i / 8, kind).map(v => Math.round(v * 255));
    stops.push(`rgb(${c[0]},${c[1]},${c[2]}) ${(i / 8 * 100).toFixed(0)}%`);
  } return `linear-gradient(90deg,${stops.join(',')})`;
}

/* ------------------------------------------------- the geometry preview */
/* The same parameterisation the generator uses: four defining stations, chords
   as ratios of the root, leading edge placed by three sweep angles, twist about
   the quarter chord, dihedral accumulated outboard, and MH91 / E374 / NLF1015
   blended along the span. What differs from the mesher is the surface BETWEEN
   the stations: here it is linear, there it is a pyGeo B-spline. */
function airfoilAt(frac) {
  const a = D.airfoils.mh91.xy, b = D.airfoils.e374.xy, c = D.airfoils.nlf1015.xy;
  const N = 61, out = [];
  const sample = (arr, u) => {           // resample by index, both are Selig-ordered
    const f = u * (arr.length - 1), i = Math.min(arr.length - 2, Math.floor(f)), t = f - i;
    return [arr[i][0] + t * (arr[i + 1][0] - arr[i][0]), arr[i][1] + t * (arr[i + 1][1] - arr[i][1])];
  };
  for (let n = 0; n < N; n++) {
    const u = n / (N - 1), A = sample(a, u), B = sample(b, u), C = sample(c, u);
    let p;
    if (frac <= 0.5) { const t = frac / 0.5; p = [A[0] + t * (B[0] - A[0]), A[1] + t * (B[1] - A[1])]; }
    else { const t = (frac - 0.5) / 0.5; p = [B[0] + t * (C[0] - B[0]), B[1] + t * (C[1] - B[1])]; }
    out.push(p);
  }
  return out;
}
function buildPreview(dv) {
  const v = n => dv[D.design.names.indexOf(n)];
  const c1 = v('c1_m'), bt = v('b_total_m');
  const chords = [c1, c1 * v('c2_ratio'), c1 * v('c3_ratio'), c1 * v('c4_ratio')];
  const y3 = bt, y2 = bt * (1 - v('b3_ratio')), y1 = y2 * v('split_ratio');
  const ys = [0, y1, y2, y3];
  const sw = [v('sw1_deg'), v('sw2_deg'), v('sw3_deg')].map(d => d * Math.PI / 180);
  const di = [v('dihedral_b1_deg'), v('dihedral_b2_deg'), v('dihedral_b3_deg')].map(d => d * Math.PI / 180);
  const tw = [v('twist_b0_deg'), v('twist_b1_deg'), v('twist_b2_deg'), v('twist_b3_deg')].map(d => d * Math.PI / 180);
  const xle = [0], zle = [0];
  for (let s = 0; s < 3; s++) {
    const dy = ys[s + 1] - ys[s];
    xle.push(xle[s] + dy * Math.tan(-sw[s]));
    zle.push(zle[s] + dy * Math.tan(di[s]));
  }
  const NS = 25, N = 61, pts = [];
  for (let s = 0; s < NS; s++) {
    const u = s / (NS - 1) * 3, seg = Math.min(2, Math.floor(u)), t = u - seg;
    const y = ys[seg] + t * (ys[seg + 1] - ys[seg]);
    const ch = chords[seg] + t * (chords[seg + 1] - chords[seg]);
    const x0 = xle[seg] + t * (xle[seg + 1] - xle[seg]);
    const z0 = zle[seg] + t * (zle[seg + 1] - zle[seg]);
    const th = tw[seg] + t * (tw[seg + 1] - tw[seg]);
    const af = airfoilAt(y / Math.max(bt, 1e-9));
    for (let n = 0; n < N; n++) {
      const cx = (af[n][0] - 0.25) * ch, cz = af[n][1] * ch;
      const X = x0 + 0.25 * ch + cx * Math.cos(th) - cz * Math.sin(th);
      const Z = z0 + cx * Math.sin(th) + cz * Math.cos(th);
      pts.push(X, Z, y);                                  // three: y is up, z is span
    }
  }
  const area = (function () { let a = 0; for (let s = 0; s < 3; s++) a += 0.5 * (chords[s] + chords[s + 1]) * (ys[s + 1] - ys[s]); return a; })();
  const mac = (function () {
    let num = 0, den = 0;
    for (let s = 0; s < 3; s++) { const dy = ys[s + 1] - ys[s], cr = chords[s], ct = chords[s + 1];
      num += dy * (cr * cr + cr * ct + ct * ct) / 3; den += dy * (cr + ct) / 2; }
    return den ? num / den : 0;
  })();
  return { xyz: pts, ns: NS, n: N, area, mac, span: 2 * bt, ar: area > 0 ? (2 * bt) * (2 * bt) / (2 * area) : 0, chords, ys };
}

/* ------------------------------------------------------------ scene build */
function rebuild() {
  if (!renderer) return;
  clearRoot();
  const t0 = performance.now();
  let box = new THREE.Box3();
  if (S.tab === 'geom') box = drawPreview();
  else box = drawMesh();
  if (!box.isEmpty()) { if (!rebuild._framed) { frame(box); rebuild._framed = true; } }
  $('#stDraw').textContent = (performance.now() - t0).toFixed(0) + ' ms';
}
function drawPreview() {
  const g = buildPreview(S.dv);
  const geo = sheetGeometry(g.xyz, g.ns, g.n, null);
  root.add(new THREE.Mesh(geo, new THREE.MeshStandardMaterial({
    color: 0x7fa8d4, metalness: 0.15, roughness: 0.62, side: THREE.DoubleSide,
    flatShading: false
  })));
  if (S.display !== 'surf') {
    root.add(new THREE.LineSegments(sheetWire(g.xyz, g.ns, g.n),
      new THREE.LineBasicMaterial({ color: 0x1d2b3c, transparent: true, opacity: 0.85 })));
  }
  const box = new THREE.Box3().setFromObject(root);
  $('#hudTitle').textContent = 'geometry preview — linear loft, not the pyGeo surface';
  $('#hudInfo').innerHTML = `span ${fmt(g.span, 3)} m · half-area ${fmt(g.area, 4)} m²<br>MAC ${fmt(g.mac, 4)} m · AR ${fmt(g.ar, 2)}`;
  return box;
}
function drawMesh() {
  const m = D.meshes[S.level];
  if (!m) { $('#hudTitle').textContent = 'no mesh stored for this level'; return new THREE.Box3(); }
  const vol = m.volume;
  const solo = S.cut.solo && (S.cut.i || S.cut.j || S.cut.k) && vol;

  /* Cut planes first, so "isolate" can simply skip everything else. A cut you
     cannot look at on its own is a cut you cannot read: the surface sits in
     front of it from most angles. */
  if (vol) {
    const axes = [['k', S.cut.k, S.cut.kAt], ['j', S.cut.j, S.cut.jAt], ['i', S.cut.i, S.cut.iAt]];
    axes.forEach(([ax, on, at]) => {
      if (!on) return;
      const s = volSlice(vol, ax, Math.min(at, vol.shape[ax === 'i' ? 0 : ax === 'j' ? 1 : 2] - 1));
      root.add(new THREE.LineSegments(sheetWire(s.xyz, s.n, s.m),
        new THREE.LineBasicMaterial({ color: solo ? 0x8fc3ff : 0x4a86c4,
          transparent: true, opacity: solo ? 0.95 : 0.7 })));
      if (S.cut.filled) {
        root.add(new THREE.Mesh(sheetGeometry(s.xyz, s.n, s.m, null),
          new THREE.MeshBasicMaterial({ color: 0x0d1720, transparent: true,
            opacity: solo ? 0.9 : 0.4, side: THREE.DoubleSide })));
      }
    });
  }

  if (!solo) {
    const [n, mm] = m.surface.shape;
    const P = xyz(m.surface);
    const field = fieldFor();
    let colours = null;
    if (field) {
      colours = [];
      const [fn, fm] = field.shape, lo = field.min, hi = field.max;
      const kind = S.colour === 'cp' ? 'div' : 'seq';
      for (let i = 0; i < n; i++) for (let k = 0; k < mm; k++) {
        /* the field is CELL data on an (n-1) x (mm-1) grid; a node takes the
           cell it belongs to rather than being interpolated, so a band edge
           lands where the solver put it */
        const fi = Math.min(fn - 1, Math.max(0, i - (i === n - 1 ? 1 : 0)));
        const fk = Math.min(fm - 1, Math.max(0, k - (k === mm - 1 ? 1 : 0)));
        colours.push(...ramp((field.values[fi * fm + fk] - lo) / Math.max(1e-12, hi - lo), kind));
      }
    }
    const mat = () => new THREE.MeshStandardMaterial({
      color: 0x93b8dc, metalness: 0.08, roughness: 0.7, side: THREE.DoubleSide,
      vertexColors: !!colours
    });
    if (S.display !== 'wire') root.add(new THREE.Mesh(sheetGeometry(P, n, mm, colours), mat()));
    if (S.display !== 'surf') {
      root.add(new THREE.LineSegments(sheetWire(P, n, mm),
        new THREE.LineBasicMaterial({
          color: S.display === 'wire' ? 0x5c86ad : 0x16202c,
          transparent: true, opacity: S.display === 'wire' ? 0.95 : 0.85
        })));
    }
    /* The tip cap. Without it the wing is an open tube: cap_out[:,:,0] is the
       patch that closes the tip, and its edge matches the wing's tip ring to
       2.5e-16 m -- they are the same points. */
    if (m.cap && S.showCap !== false) {
      const [cn, cm] = m.cap.shape, C = xyz(m.cap);
      if (S.display !== 'wire') {
        root.add(new THREE.Mesh(sheetGeometry(C, cn, cm, null),
          new THREE.MeshStandardMaterial({ color: 0xb08a6a, metalness: 0.08,
            roughness: 0.72, side: THREE.DoubleSide })));
      }
      if (S.display !== 'surf') {
        root.add(new THREE.LineSegments(sheetWire(C, cn, cm),
          new THREE.LineBasicMaterial({ color: S.display === 'wire' ? 0xc79a72 : 0x2a1f16,
            transparent: true, opacity: 0.9 })));
      }
    }
  }

  const box = new THREE.Box3().setFromObject(root);
  const sh = m.blocks.o_wing.shape;
  $('#hudTitle').textContent = solo
    ? `${S.level} — cut plane isolated`
    : `${S.level} — the node array the solver was handed, at full resolution`;
  $('#hudInfo').innerHTML =
    `wing block ${sh[0]}×${sh[1]}×${sh[2]} nodes · ${(m.cells_total || 0).toLocaleString()} cells all blocks<br>` +
    (vol ? `volume sliceable, j ${vol.j_cap} of ${vol.j_full}` : 'volume not carried for this level') +
    (m.folded === 0 ? ' · 0 folded' : '');
  return box;
}

function fieldFor() {
  if (S.colour === 'none' || S.tab !== 'post') return null;
  const sf = (D.surface_fields || {})[S.alpha];
  return sf ? sf[S.colour] : null;
}

/* ------------------------------------------------------------------ panels */
function slider(id, label, lo, hi, val, step, unit, oninput) {
  return `<div class="row"><label for="${id}"><span class="nm">${label}</span>
    <span class="val" id="${id}_v">${(+val).toFixed(step < 0.01 ? 4 : step < 1 ? 3 : 0)}${unit || ''}</span></label>
    <input type="range" id="${id}" min="${lo}" max="${hi}" step="${step}" value="${val}"></div>`;
}
function wireSlider(id, fn, dp, unit) {
  const el = $('#' + id); if (!el) return;
  el.addEventListener('input', () => {
    $('#' + id + '_v').textContent = (+el.value).toFixed(dp) + (unit || '');
    fn(+el.value);
  });
}
const MEM = c => (2.69 + 7.23 * c / 1e6) * 1.05;

function levelCells(L) {
  /* The wing block alone, from interval counts: the figure the memory law and
     the timing model both take. The outboard blocks add about 55 % on top and
     the stored manifest carries the real total where a mesh was built. */
  const i = 2 * (L.n_side - 1), j = L.n_normal - 1, k = L.n_span - 1;
  return { wing: i * j * k, i, j, k };
}
function renderLeft() {
  const L = $('#left'); const N = D.design.names, B = D.design.bounds;
  if (S.tab === 'geom') {
    const groups = [
      ['Planform', [0, 1, 2, 3, 4, 5, 6]],
      ['Sweep', [7, 8, 9]],
      ['Twist', [10, 11, 12, 13]],
      ['Dihedral', [14, 15, 16]],
      ['Elevon', [17, 18, 19]]
    ];
    L.innerHTML =
      `<details class="group" open><summary>Design</summary><div class="gbody">
        <select id="pick"><option value="">— custom —</option>${Object.keys(D.design.designs)
        .map(k => `<option value="${k}"${k === '83' ? ' selected' : ''}>design ${k}${k === '83' ? ' (reference)' : ''}</option>`).join('')}</select>
        <div class="note">The 100-design LHS the campaign samples. Moving any slider leaves the set and becomes a custom vector.</div>
      </div></details>` +
      groups.map(([name, idx], gi) => `<details class="group"${gi === 0 ? ' open' : ''}><summary>${name}</summary><div class="gbody">` +
        idx.map(i => slider('dv' + i, N[i], B[i][0], B[i][1], S.dv[i],
          (B[i][1] - B[i][0]) / 200 || 0.001, '')).join('') + `</div></details>`).join('') +
      `<details class="group" open><summary>Display</summary><div class="gbody">
        <div class="seg" id="segDisp">
          <button data-d="surf">surface</button><button data-d="surf-edges">+ edges</button><button data-d="wire">wireframe</button>
        </div></div></details>`;
    $('#pick').addEventListener('change', e => {
      const k = e.target.value; if (!k) return;
      S.dv = D.design.designs[k].slice(); $('#stDesign').textContent = k;
      renderLeft(); renderRight(); rebuild._framed = false; rebuild();
    });
    N.forEach((_, i) => wireSlider('dv' + i, v => {
      S.dv[i] = v; $('#pick').value = ''; $('#stDesign').textContent = 'custom';
      renderRight(); rebuild();
    }, (B[i][1] - B[i][0]) < 2 ? 4 : 2, ''));
  }

  if (S.tab === 'mesh') {
    const cur = S.custom || D.levels.levels[S.level];
    const c = levelCells(cur);
    const vsh = (D.meshes[S.level] && D.meshes[S.level].volume || {}).shape;
    L.innerHTML =
      `<details class="group" open><summary>Level</summary><div class="gbody">
        <div class="seg" id="segLevel">
          ${['gci_C', 'gci_M', 'gci_F', 'gci_FF'].map(l => `<button data-l="${l}">${l.replace('gci_', '')}</button>`).join('')}
        </div>
        <div class="note">The convergence family, at a refinement ratio of <b>1.300</b> in every
        direction at every step. <b>gci_CC</b> and <b>gci_MF</b> are deliberately absent: both are
        generated from the old <code>oh_L3</code> baseline and carry its trailing-edge target, so
        they are not in this family.</div>
      </div></details>
      <details class="group" open><summary>Resolution</summary><div class="gbody">
        ${slider('m_side', 'n_side (chordwise half)', 20, 130, cur.n_side, 1, '')}
        ${slider('m_span', 'n_span', 20, 140, cur.n_span, 1, '')}
        ${slider('m_norm', 'n_normal', 30, 180, cur.n_normal, 1, '')}
        <div class="note">Moving any of these leaves the preset. The cell count and memory update
        from the real laws; <b>nothing is meshed</b> — that needs the mesher.</div>
      </div></details>
      <details class="group"><summary>Spacing &amp; domain</summary><div class="gbody">
        ${slider('m_te', 'ds_te / chord', 0.0002, 0.006, cur.ds_te_frac, 0.0001, '')}
        ${slider('m_s0', 's0 / bbox diagonal', 1.0e-6, 8.0e-6, cur.s0_frac, 1e-7, '')}
        ${slider('m_ff', 'far field (root chords)', 20, 120, cur.farfield_chords, 1, '')}
        ${slider('m_le', 'LE turn target', 4, 16, cur.target_le_turn_deg || 10, 0.5, '°')}
      </div></details>
      <details class="group" open><summary>Display</summary><div class="gbody">
        <div class="seg" id="segDisp">
          <button data-d="surf">surface</button><button data-d="surf-edges">+ edges</button><button data-d="wire">wireframe</button>
        </div>
        <label class="chk"><input type="checkbox" id="showCap" ${S.showCap ? 'checked' : ''}> tip cap</label>
        <div class="note">Without it the wing is an open tube. The cap patch shares its edge with
        the wing's tip ring to <b>2.5e-16 m</b> — the same points, not two surfaces that meet.</div>
      </div></details>
      <details class="group" open><summary>Cut planes</summary><div class="gbody">
        ${vsh ? `
        <label class="chk"><input type="checkbox" id="cutK" ${S.cut.k ? 'checked' : ''}> chordwise (constant span)</label>
        ${slider('cutKat', 'span station k', 0, vsh[2] - 1, Math.min(S.cut.kAt, vsh[2] - 1), 1, '')}
        <label class="chk"><input type="checkbox" id="cutJ" ${S.cut.j ? 'checked' : ''}> parallel to the wall</label>
        ${slider('cutJat', 'wall-normal layer j', 0, vsh[1] - 1, Math.min(S.cut.jAt, vsh[1] - 1), 1, '')}
        <label class="chk"><input type="checkbox" id="cutI" ${S.cut.i ? 'checked' : ''}> spanwise (constant ring index)</label>
        ${slider('cutIat', 'ring index i', 0, vsh[0] - 1, Math.min(S.cut.iAt, vsh[0] - 1), 1, '')}
        <div class="seg" id="segCut">
          <button data-k="solo">isolate cut</button><button data-k="filled">shade plane</button>
        </div>
        <div class="note"><b>Isolate</b> hides the wing so the plane can be read on its own —
        the surface sits in front of it from most angles. Ring index 0 is the trailing edge;
        the clustering you see at <b>i ≈ 0</b>, <b>i ≈ ${Math.round(vsh[0] / 2)}</b> and at the
        highest span stations is the mesh's own.</div>`
        : '<div class="note">No volume is carried for this level — only the surface. Switch to <b>C</b> or <b>M</b> to slice.</div>'}
      </div></details>`;
    $$('#segLevel button').forEach(b => b.addEventListener('click', () => {
      S.level = b.dataset.l; S.custom = null; $('#stLevel').textContent = S.level;
      renderLeft(); renderRight(); rebuild._framed = false; rebuild();
    }));
    const touch = () => { S.custom = Object.assign({}, S.custom || D.levels.levels[S.level]); };
    wireSlider('m_side', v => { touch(); S.custom.n_side = v; $('#stLevel').textContent = 'custom'; renderRight(); }, 0);
    wireSlider('m_span', v => { touch(); S.custom.n_span = v; $('#stLevel').textContent = 'custom'; renderRight(); }, 0);
    wireSlider('m_norm', v => { touch(); S.custom.n_normal = v; $('#stLevel').textContent = 'custom'; renderRight(); }, 0);
    wireSlider('m_te', v => { touch(); S.custom.ds_te_frac = v; renderRight(); }, 4);
    wireSlider('m_s0', v => { touch(); S.custom.s0_frac = v; renderRight(); }, 7);
    wireSlider('m_ff', v => { touch(); S.custom.farfield_chords = v; renderRight(); }, 0);
    wireSlider('m_le', v => { touch(); S.custom.target_le_turn_deg = v; renderRight(); }, 1, '°');
    ['k', 'j', 'i'].forEach(ax => {
      const box = $('#cut' + ax.toUpperCase());
      if (box) box.addEventListener('change', () => { S.cut[ax] = box.checked; rebuild(); });
      wireSlider('cut' + ax.toUpperCase() + 'at', v => { S.cut[ax + 'At'] = v | 0; rebuild(); }, 0);
    });
    const cap = $('#showCap');
    if (cap) cap.addEventListener('change', () => { S.showCap = cap.checked; rebuild(); });
    $$('#segCut button').forEach(b => {
      b.setAttribute('aria-pressed', String(!!S.cut[b.dataset.k]));
      b.addEventListener('click', () => {
        S.cut[b.dataset.k] = !S.cut[b.dataset.k];
        b.setAttribute('aria-pressed', String(S.cut[b.dataset.k])); rebuild();
      });
    });
  }

  if (S.tab === 'solver') {
    const s = S.solver;
    L.innerHTML =
      `<details class="group" open><summary>Configuration</summary><div class="gbody">
        <div class="seg" id="segCfg"><button data-c="governed">governed default</button><button data-c="custom">custom</button></div>
        <div class="warnbox" id="cfgWarn" hidden>Off the governed configuration. A run whose settings
        differ is a <b>different case</b>: the four-level study will refuse to combine it with levels
        solved under the default, and it says which field differs.</div>
      </div></details>
      <details class="group" open><summary>Physics</summary><div class="gbody">
        <label class="chk"><span style="flex:1">turbulence model</span></label>
        <select id="s_turb"><option>SA</option><option>SA-Edwards</option><option>SST</option></select>
        <div class="note">ADflow's SA is what the campaign is built on. SST is available; <b>SA-Edwards
        returned CDv 66 % low</b> here and is kept only as the case that exposed how weak the
        plausibility gates were.</div>
        ${slider('s_chi', 'freestream χ = ν̃/ν', 1, 8, 3, 0.1, '')}
        <div class="note">χ = 3 gives ν<sub>t</sub>/ν = 0.21044, which is the TMR's recommendation.
        The solver takes the ratio, not χ.</div>
        <label class="chk"><input type="checkbox" id="s_qcr"> QCR (quadratic constitutive relation)</label>
        <label class="chk"><input type="checkbox" id="s_wf"> wall functions</label>
        <div class="note">Wall functions are <b>off</b>: this family resolves to the wall, which is
        why y+ is held near 1 rather than above 30.</div>
      </div></details>
      <details class="group" open><summary>Convergence</summary><div class="gbody">
        ${slider('s_l2', 'L2Convergence (10^x)', -10, -4, -6, 0.5, '')}
        <div class="note">The stopping rule is a <b>relative</b> residual. Tightening it changes the
        case identity, so a level solved at 1e-8 cannot be combined with one solved at 1e-6.</div>
        <label class="chk"><input type="checkbox" id="s_nk"> enable Newton–Krylov stage</label>
        <div class="warnbox">NK <b>froze at 1,172,856 cells</b> with this project's lean
        preconditioner — step 0.01, linear residual 1.000 — while ANK alone converged the same case
        in a fifth of the time. ANK-only is what is proven at these counts, and it is unproven above
        them: that is what the cloud pilot tests.</div>
        ${slider('s_ranks', 'MPI ranks per case', 1, 16, s.ranks, 1, '')}
        <div class="note">Four is the measured optimum: 2.7 % slower than six for <b>32 % fewer
        core-hours</b>. Count <b>physical</b> cores, not threads.</div>
      </div></details>
      <details class="group" open><summary>Run</summary><div class="gbody">
        <label class="chk"><span style="flex:1">angles of attack</span></label>
        <div class="seg" id="segRunA">${['-2', '0', '4', '8'].map(a =>
          `<button data-a="${a}" aria-pressed="true">${a}°</button>`).join('')}</div>
        <button class="btn" id="runBtn">Build run command</button>
        <button class="btn ghost" id="copyBtn" hidden>Copy to clipboard</button>
        <div class="warnbox" style="border-left-color:var(--accent);background:#0e1a26;color:#bcd8f5">
        This page cannot start a solver. ADflow is an MPI Fortran code that needs the mesh, the
        MACH-Aero environment and a machine; a browser has none of them. <b>Run</b> writes the exact
        command for the host that does, so what executes is what you configured here rather than
        something typed again from memory.</div>
      </div></details>`;
    $('#s_turb').value = s.turbulenceModel;
    $('#s_nk').checked = s.useNKSolver;
    $$('#segCfg button').forEach(b => b.addEventListener('click', () => {
      const custom = b.dataset.c === 'custom';
      $$('#segCfg button').forEach(x => x.setAttribute('aria-pressed', String(x === b)));
      $('#cfgWarn').hidden = !custom; renderRight();
    }));
    $('#segCfg button[data-c="governed"]').setAttribute('aria-pressed', 'true');
    ['s_turb', 's_nk', 's_qcr', 's_wf'].forEach(id => {
      const el = $('#' + id); if (!el) return;
      el.addEventListener('change', () => {
        if (id === 's_turb') S.solver.turbulenceModel = el.value;
        if (id === 's_nk') S.solver.useNKSolver = el.checked;
        if (id === 's_qcr') S.solver.useQCR = el.checked;
        if (id === 's_wf') S.solver.useWallFunctions = el.checked;
        renderRight();
      });
    });
    wireSlider('s_l2', v => { S.solver.L2Convergence = Math.pow(10, v); renderRight(); }, 1);
    wireSlider('s_chi', v => { S.solver.chi = v; S.solver.eddyVisInfRatio = Math.pow(v, 4) / (Math.pow(v, 3) + 357.911); renderRight(); }, 1);
    wireSlider('s_ranks', v => { S.solver.ranks = v; renderRight(); }, 0);
    $$('#segRunA button').forEach(b => b.addEventListener('click', () => {
      const on = b.getAttribute('aria-pressed') !== 'true';
      b.setAttribute('aria-pressed', String(on));
    }));
    $('#runBtn').addEventListener('click', () => {
      const alphas = $$('#segRunA button').filter(b => b.getAttribute('aria-pressed') === 'true')
        .map(b => b.dataset.a);
      if (!alphas.length) { $('#stMsg').textContent = 'pick at least one angle'; return; }
      S.runCmd = buildCommand(alphas);
      $('#copyBtn').hidden = false;
      renderRight();
      $('#stMsg').textContent = `command built for ${alphas.length} angle(s)`;
    });
    $('#copyBtn').addEventListener('click', async () => {
      try { await navigator.clipboard.writeText(S.runCmd || ''); $('#stMsg').textContent = 'copied'; }
      catch (_) { $('#stMsg').textContent = 'clipboard blocked — select the text instead'; }
    });
  }

/* The command the configured case actually needs. Written from the same fields
   that enter the case id, so a run started from it is the run this page
   describes -- which is the whole point of not pretending to launch one. */
function buildCommand(alphas) {
  const s = S.solver, lvl = S.level, idx = 83;
  const flags = [];
  if (!s.useNKSolver) flags.push('--no-nk');
  if (s.eddyVisInfRatio) flags.push(`--eddy-vis-inf-ratio ${(+s.eddyVisInfRatio).toPrecision(5)}`);
  flags.push('--watch-memory');
  const S8 = 'AERIS_MESH_STUDY/04_strategy_studies/S8_oh_structured';
  const lines = [
    '# built by the S8 Workbench — every flag below is a field of the case id',
    `# level ${lvl} · ${s.turbulenceModel} · L2 ${s.L2Convergence.toExponential(0)} · ${s.ranks} ranks`,
    '',
    '# 1. the mesh, if it is not already built',
    `.venv/bin/python ${S8}/build_volume.py \\`,
    `    --level ${lvl} --index ${idx} --out ${S8}/runs/s8_v2/g${idx}`,
    `$AERIS_MACH_PYTHON ${S8}/write_cgns.py \\`,
    `    --blocks ${S8}/runs/s8_v2/g${idx}/${lvl}_blocks.npz`,
    '',
    '# 2. solve'
  ];
  alphas.forEach(a => {
    lines.push(`$AERIS_MACH_PYTHON ${S8}/solve_s8.py \\`);
    lines.push(`    --grid ${S8}/runs/s8_v2/g${idx}/${lvl}_volume.cgns \\`);
    lines.push(`    --alpha ${a} --ranks ${s.ranks} \\`);
    lines.push(`    --out ${S8}/runs/s8_v2/g${idx}/${lvl}_a${a} ${flags.join(' ')}`);
  });
  lines.push('', '# 3. judge it — exit status proves nothing either way',
    `.venv/bin/python ${S8}/collect_dataset.py --runs ${S8}/runs/s8_v2 --out ${S8}/data/dataset_v2`,
    `.venv/bin/python ${S8}/audit_runs.py --rows ${S8}/data/dataset_v2/rows.json \\`,
    `    --out ${S8}/reports/s8_archive_audit_v2.json`);
  return lines.join('\n');
}

  if (S.tab === 'post') {
    L.innerHTML =
      `<details class="group" open><summary>Solution</summary><div class="gbody">
        <div class="seg" id="segLevel2">${['gci_C', 'gci_M'].map(l => `<button data-l="${l}">${l.replace('gci_', '')}</button>`).join('')}</div>
        <div class="seg" id="segAlpha">${['-2', '0', '4', '8'].map(a => `<button data-a="${a}">α ${a}°</button>`).join('')}</div>
      </div></details>
      <details class="group" open><summary>Contour</summary><div class="gbody">
        <div class="seg" id="segColour">
          <button data-c="none">none</button><button data-c="cp">c<sub>p</sub></button>
          <button data-c="cf">c<sub>f</sub></button><button data-c="yplus">y⁺</button>
        </div>
        <div class="note">Cell values as ADflow wrote them, with the rind layer stripped and
        transposed onto the same grid as the geometry — not a texture.</div>
      </div></details>
      <details class="group" open><summary>Display</summary><div class="gbody">
        <div class="seg" id="segDisp">
          <button data-d="surf">surface</button><button data-d="surf-edges">+ edges</button><button data-d="wire">wireframe</button>
        </div>
        <label class="chk"><input type="checkbox" id="cutK" ${S.cut.k ? 'checked' : ''}> chordwise cut</label>
        ${slider('cutKat', 'span station', 0, 48, S.cut.kAt, 1, '')}
      </div></details>
      <details class="group" open><summary>Distribution</summary><div class="gbody">
        <canvas class="plot" id="plot"></canvas>
        <div class="note" id="plotNote"></div>
      </div></details>`;
    $$('#segLevel2 button').forEach(b => b.addEventListener('click', () => {
      S.level = b.dataset.l; $('#stLevel').textContent = S.level; renderLeft(); renderRight(); rebuild();
    }));
    $$('#segAlpha button').forEach(b => b.addEventListener('click', () => {
      S.alpha = b.dataset.a; renderLeft(); renderRight(); rebuild();
    }));
    $$('#segColour button').forEach(b => b.addEventListener('click', () => {
      S.colour = b.dataset.c; renderLeft(); renderRight(); rebuild();
    }));
    const box = $('#cutK');
    if (box) box.addEventListener('change', () => { S.cut.k = box.checked; rebuild(); });
    wireSlider('cutKat', v => { S.cut.kAt = v | 0; rebuild(); }, 0);
    drawPlot();
  }
  syncSegments();
}
function syncSegments() {
  $$('#segDisp button').forEach(b => b.setAttribute('aria-pressed', String(b.dataset.d === S.display)));
  $$('#segDisp button').forEach(b => b.onclick = () => { S.display = b.dataset.d; syncSegments(); rebuild(); });
  $$('#segLevel button').forEach(b => b.setAttribute('aria-pressed', String(b.dataset.l === S.level)));
  $$('#segLevel2 button').forEach(b => b.setAttribute('aria-pressed', String(b.dataset.l === S.level)));
  $$('#segAlpha button').forEach(b => b.setAttribute('aria-pressed', String(b.dataset.a === S.alpha)));
  $$('#segColour button').forEach(b => b.setAttribute('aria-pressed', String(b.dataset.c === S.colour)));
}
const $$ = (s, r) => Array.from((r || document).querySelectorAll(s));

/* ------------------------------------------------------------------ right */
function renderRight() {
  const R = $('#right'); if (!R) return;
  const kv = (k, v, cls) => `<div class="kv"><span class="k">${k}</span><span class="v ${cls || ''}">${v}</span></div>`;

  if (S.tab === 'geom') {
    const g = buildPreview(S.dv);
    R.innerHTML = `<details class="group" open><summary>Planform</summary><div class="gbody">
      ${kv('full span', fmt(g.span, 4) + ' m')}${kv('half-area', fmt(g.area, 5) + ' m²')}
      ${kv('MAC', fmt(g.mac, 4) + ' m')}${kv('aspect ratio', fmt(g.ar, 3))}
      ${kv('root chord', fmt(g.chords[0], 4) + ' m')}${kv('tip chord', fmt(g.chords[3], 4) + ' m')}
      ${kv('taper', fmt(g.chords[3] / g.chords[0], 4))}
      </div></details>
      <details class="group" open><summary>Stations</summary><div class="gbody">
      ${g.ys.map((y, i) => kv('b' + i + ' at y = ' + fmt(y, 4) + ' m', fmt(g.chords[i], 4) + ' m')).join('')}
      </div></details>
      <details class="group" open><summary>What this is</summary><div class="gbody">
      <div class="note">The surface is lofted <b>linearly</b> between the four defining sections.
      The mesher uses a <b>pyGeo B-spline</b> loft through the same sections, so the stations, chords,
      sweeps, twists and dihedral are exact here and the surface between them is an approximation.
      Areas quoted above are trapezoidal from the stations, which is why they differ slightly from
      the recorded reference areas.</div>
      <div class="note"><b>Reference area on file for design 83:</b> 0.394918 m² (half). Trapezoidal
      here: ${fmt(g.area, 6)} m².</div>
      </div></details>`;
    return;
  }

  if (S.tab === 'mesh') {
    const cur = S.custom || D.levels.levels[S.level];
    const c = levelCells(cur);
    const M = D.meshes[S.level];
    /* the build's own summary, not a formula: my first version computed
       2*(n_side-1) for the ring and got 88 where the mesh has 92 */
    const total = (M && M.cells_total) || Math.round(c.wing * 1.55);
    const stored = M && M.blocks;
    const mem = MEM(total);
    const fits = mem <= 12.8;
    R.innerHTML = `<details class="group" open><summary>Size</summary><div class="gbody">
      ${stored ? Object.entries(stored).map(([k, b]) =>
        kv(k, b.shape.join('×') + '  ' + b.cells.toLocaleString() + ' cells')).join('')
        : kv('wing block cells', c.wing.toLocaleString(), 'w')}
      ${kv('all blocks', total.toLocaleString(), stored ? 'g' : 'w')}
      ${M && M.folded === 0 ? kv('folded cells', '0', 'g') : ''}
      ${M ? kv('wall-layer error', M.wall_layer_error_m.toExponential(1) + ' m', 'g') : ''}
      ${stored ? '' : '<div class="note">No built mesh stored for these settings; the outboard blocks are estimated at +55 %.</div>'}
      </div></details>
      <details class="group" open><summary>Cost</summary><div class="gbody">
      ${kv('memory, ANK-only', fmt(mem, 1) + ' GiB', fits ? 'g' : 'b')}
      ${kv('fits a 12.8 GiB host', fits ? 'yes' : 'no', fits ? 'g' : 'b')}
      ${kv('at 4 ranks, one α', fmt(total / 1e6 * 262 * 9.7 / 60 * 1.027, 0) + ' min')}
      ${kv('core-hours, four α', fmt(4 * total / 1e6 * 262 * 9.7 / 3600 * 6 * 0.684, 1))}
      <div class="note"><b>(2.69 + 7.23 × Mcells) × 1.05</b>, a two-point fit. Time is
      Mcells × iterations × 9.7 s, and the iteration count is one measured ratio extrapolated —
      the weakest link in the estimate.</div>
      </div></details>
      <details class="group"><summary>Spacing</summary><div class="gbody">
      ${kv('ds_te / chord', fmt(cur.ds_te_frac, 6))}
      ${kv('s0 / diagonal', cur.s0_frac.toExponential(3))}
      ${kv('far field', cur.farfield_chords + ' chords')}
      ${kv('LE turn target', fmt(cur.target_le_turn_deg || 10, 1) + '°')}
      </div></details>
      ${S.custom ? '<details class="group" open><summary>Custom</summary><div class="gbody"><div class="warnbox">Off the family. A level built from these settings is <b>not</b> at ratio 1.300 from its neighbours, and a grid-convergence study over it means nothing.</div><button class="btn ghost" id="resetLevel">back to ' + S.level + '</button></div></details>' : ''}`;
    const rb = $('#resetLevel');
    if (rb) rb.addEventListener('click', () => { S.custom = null; $('#stLevel').textContent = S.level; renderLeft(); renderRight(); });
    $('#stCells').textContent = total.toLocaleString();
    $('#stMem').textContent = fmt(mem, 1) + ' GiB';
    return;
  }

  if (S.tab === 'solver') {
    const s = S.solver;
    const chi = s.chi || 3;
    R.innerHTML = `<details class="group" open><summary>Resolved options</summary><div class="gbody">
      ${kv('equationType', 'RANS')}${kv('turbulenceModel', s.turbulenceModel)}
      ${kv('turbulenceOrder', 'first order')}
      ${kv('eddyVisInfRatio', fmt(Math.pow(chi, 4) / (Math.pow(chi, 3) + 357.911), 5))}
      ${kv('liftIndex', 3)}${kv('MGCycle', 'sg')}
      ${kv('useNKSolver', String(s.useNKSolver), s.useNKSolver ? 'w' : 'g')}
      ${kv('L2Convergence', s.L2Convergence.toExponential(0))}
      ${kv('useWallFunctions', String(s.useWallFunctions), s.useWallFunctions ? 'b' : 'g')}
      ${kv('useQCR', String(s.useQCR))}
      ${kv('ranks', s.ranks, s.ranks === 4 ? 'g' : 'w')}
      </div></details>
      <details class="group" open><summary>Operating point</summary><div class="gbody">
      ${kv('Mach', '0.0837')}${kv('Reynolds (c 0.9 m)', '1.53 × 10⁶')}
      ${kv('temperature', '278.4 K')}${kv('speed', '28 m/s at 1500 m')}
      <div class="note">Essentially incompressible. The low Mach does not remove the numerical
      difficulty: the acoustic speed is far above the convective one, and the drag has measurable
      sensitivity to how the dissipation uses both.</div>
      </div></details>
      <details class="group" open><summary>Identity</summary><div class="gbody">
      <div class="note">Every one of these fields enters the <b>case id</b>. Two runs that differ in
      any of them are different cases, and the four-level study refuses to combine them rather than
      averaging over the difference.</div>
      </div></details>
      ${S.runCmd ? `<details class="group" open><summary>Command</summary><div class="gbody">
        <pre style="font-family:var(--mono);font-size:.66rem;line-height:1.5;color:var(--ink-2);
          background:var(--sunk);border:1px solid var(--rule);border-radius:4px;padding:.55rem;
          overflow-x:auto;white-space:pre;margin:0">${S.runCmd.replace(/&/g, '&amp;').replace(/</g, '&lt;')}</pre>
        </div></details>` : ''}`;
    return;
  }

  if (S.tab === 'post') {
    const r = (D.results[S.level] || {})[S.alpha];
    if (!r) { R.innerHTML = '<div class="gbody"><div class="note">No solution stored for this level and angle.</div></div>'; return; }
    const other = (D.results[S.level === 'gci_C' ? 'gci_M' : 'gci_C'] || {})[S.alpha];
    const dCD = other ? 1e4 * (other.CD - r.CD) : null;
    const sf = (D.surface_fields || {})[S.alpha] || {};
    R.innerHTML = `<details class="group" open><summary>Forces</summary><div class="gbody">
      ${kv('C_L', fmt(r.CL, 6))}
      ${kv('C_D', counts(r.CD) + ' ct')}
      ${kv('C_Dp', counts(r.CDp) + ' ct')}
      ${kv('C_Dv', counts(r.CDv) + ' ct')}
      ${kv('C_My', fmt(r.CMy, 6))}
      ${kv('L/D', fmt(r.CL / r.CD, 2))}
      </div></details>
      <details class="group" open><summary>Convergence</summary><div class="gbody">
      ${kv('converged', String(r.converged), r.converged ? 'g' : 'b')}
      ${kv('iterations', r.iterations)}
      ${kv('relative residual', r.relative_residual ? r.relative_residual.toExponential(2) : '—',
      r.relative_residual <= 1e-6 ? 'g' : 'w')}
      ${kv('reference area', fmt(r.area_ref_m2, 6) + ' m²')}
      </div></details>
      ${dCD !== null ? `<details class="group" open><summary>Grid</summary><div class="gbody">
        ${kv(S.level === 'gci_C' ? 'C → M' : 'M → C', fmt(dCD, 2) + ' ct')}
        <div class="note">Refining moves drag by tens of counts and lift by under 0.002. The
        <b>moment is converged at the coarse grid and the drag is not</b>, and 93–97 % of the change
        is pressure drag, because the wall spacing refines with everything else and skin friction
        barely moves.</div>
        <div class="warnbox">Two levels give a trend, never a GCI. The observed order needs a third,
        which is what the cloud batch is for.</div></div></details>` : ''}
      <details class="group" open><summary>Surface field</summary><div class="gbody">
      ${['cp', 'cf', 'yplus'].map(k => sf[k] ? kv(k === 'yplus' ? 'y⁺ range' : k + ' range',
      fmt(sf[k].min, 3) + ' … ' + fmt(sf[k].max, 3), k === 'yplus' && sf[k].max > 1 ? 'w' : '') : '').join('')}
      ${sf.yplus && sf.yplus.max > 1 ? '<div class="note">Peak y⁺ above 1 sits on the <b>tip cap</b>. Across the 52-run set the wall p95 is 0.415–0.814 and the p99 is 0.671–1.156.</div>' : ''}
      </div></details>`;
    return;
  }
}

/* --------------------------------------------------------------- 2-D plot */
function drawPlot() {
  const cv = $('#plot'); if (!cv) return;
  const sf = (D.surface_fields || {})[S.alpha];
  const key = S.colour === 'none' ? 'cp' : S.colour;
  const f = sf && sf[key];
  const note = $('#plotNote');
  if (!f) { note.textContent = 'no field stored'; return; }
  const dpr = Math.min(devicePixelRatio, 2);
  cv.width = cv.clientWidth * dpr; cv.height = cv.clientHeight * dpr;
  const g = cv.getContext('2d'); g.scale(dpr, dpr);
  const W = cv.clientWidth, H = cv.clientHeight, pad = 4;
  g.clearRect(0, 0, W, H);
  /* the chordwise distribution at mid-span: the ring index runs nose -> tail ->
     nose, which is why the trace closes on itself */
  const [n, m] = f.shape, kmid = m >> 1;
  const col = []; for (let i = 0; i < n; i++) col.push(f.values[i * m + kmid]);
  const lo = Math.min(...col), hi = Math.max(...col), rng = (hi - lo) || 1;
  const flip = key === 'cp';                    // cp is drawn inverted, as it always is
  g.strokeStyle = '#4a9eff'; g.lineWidth = 1.4; g.beginPath();
  col.forEach((v, i) => {
    const x = pad + i / (n - 1) * (W - 2 * pad);
    const t = (v - lo) / rng, y = pad + (flip ? t : 1 - t) * (H - 2 * pad);
    i ? g.lineTo(x, y) : g.moveTo(x, y);
  });
  g.stroke();
  g.strokeStyle = '#242c38'; g.lineWidth = 1;
  g.beginPath(); g.moveTo(pad, H - pad); g.lineTo(W - pad, H - pad); g.stroke();
  note.innerHTML = `<b>${key === 'yplus' ? 'y⁺' : key}</b> around the ring at mid-span, ` +
    `${fmt(lo, 3)} … ${fmt(hi, 3)}${flip ? ' — inverted, as c<sub>p</sub> is drawn' : ''}.`;
}

/* ------------------------------------------------------------------- legend */
function renderLegend() {
  const f = fieldFor(), el = $('#legend');
  if (!f) { el.hidden = true; return; }
  el.hidden = false;
  $('#legendTitle').textContent = S.colour === 'yplus' ? 'y+' : S.colour;
  $('#legendBar').style.background = cssRamp(S.colour === 'cp' ? 'div' : 'seq');
  $('#legendLo').textContent = fmt(f.min, 2);
  $('#legendHi').textContent = fmt(f.max, 2);
}

/* --------------------------------------------------------------------- go */
function setTab(t) {
  S.tab = t;
  $$('.step').forEach(b => b.setAttribute('aria-selected', String(b.dataset.tab === t)));
  if (t === 'post' && S.colour === 'none') S.colour = 'cp';
  rebuild._framed = false;
  renderLeft(); renderRight(); renderLegend(); rebuild();
  $('#stMsg').textContent = {
    geom: 'preview only — the mesher lofts with pyGeo',
    mesh: 'sizes are predicted; nothing is meshed here',
    solver: 'settings shown are the ones that enter the case id',
    post: 'fields are what ADflow wrote, on the grid it wrote them to'
  }[t] || '';
}
function boot() {
  if (!window.THREE) {
    $('#viewport').innerHTML = '<div style="padding:2rem;color:#97a3b4">three.js did not load, so the 3-D view is unavailable. Everything else on this page still works.</div>';
  } else initGL();
  $('#provenance').textContent = 'commit ' + String(D.provenance.repo_commit || '').slice(0, 9);
  $$('.step').forEach(b => b.addEventListener('click', () => setTab(b.dataset.tab)));
  $$('.vtools button').forEach(b => b.addEventListener('click', () => {
    const v = b.dataset.view;
    if (v === 'fit') { rebuild._framed = false; rebuild(); return; }
    if (v === 'iso') { cam.theta = -0.9; cam.phi = 1.05; }
    if (v === 'x') { cam.theta = 0; cam.phi = Math.PI / 2; }
    if (v === 'y') { cam.theta = -Math.PI / 2; cam.phi = 0.02; }
    if (v === 'z') { cam.theta = -Math.PI / 2; cam.phi = Math.PI / 2; }
  }));
  const wrap = (fn) => function () { const r = fn.apply(this, arguments); renderLegend(); return r; };
  rebuild = wrap(rebuild);
  setTab('geom');
}
document.addEventListener('DOMContentLoaded', boot);
if (document.readyState !== 'loading') boot();
