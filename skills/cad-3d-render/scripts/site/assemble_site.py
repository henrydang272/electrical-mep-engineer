"""Assemble the whole-project site scene: engine from the skill template + georeferenced ground +
massing for every master-plan footprint + the detailed 17B and 057 blocks relocated to their
site-plan positions (site coords in metres, A-2001 frame)."""
import json, os, sys
S = sys.argv[1]; SITE = S + '/site'
tpl = open(os.path.expanduser('~/.claude/skills/cad-3d-render/templates/render_scene.html'), encoding='utf-8').read()
b057 = open(os.path.expanduser('~/.claude/skills/cad-3d-render/examples/057_HVAC/building_057.js'), encoding='utf-8').read()
B = json.load(open(SITE + '/buildings.json')); TREES = json.load(open(SITE + '/trees.json'))
G = json.load(open(SITE + '/site_ground.json')); GURI = open(SITE + '/ground_datauri.txt').read()
O17 = (-274.08, 144.5); O57 = (-193.52, 84.1)

def rep(s, a, b, n=1):
    assert a in s, 'missing: ' + a[:80]
    return s.replace(a, b, n)
s = tpl
# ---- CFG ----
s = rep(s, "code: '17B',", "code: 'SITE',")
s = rep(s, "title: '17B Waste Handling Area',", "title: 'Project A - Master Plan',")
s = rep(s, "project: 'Project A',", "project: 'Client site',")
# ---- relocatable coordinates: V() and prism() honour a site offset ----
s = rep(s, "const V = (x, y, z) => new THREE.Vector3(x, z, -y);",
        "let OX = 0, OY = 0;   // site offset of the building block being built (metres)\nconst V = (x, y, z) => new THREE.Vector3(x + OX, z, -(y + OY));")
s = rep(s, "if (axis === 'x') { me.position.set(0, 0, -b); }\n  else { me.rotation.y = Math.PI / 2; me.position.set(a, 0, 0); }",
        "if (axis === 'x') { me.position.set(OX, 0, -b - OY); }\n  else { me.rotation.y = Math.PI / 2; me.position.set(a + OX, 0, -OY); }")
# ---- extract 17B block and tree generator from the template ----
i_site = s.index("// ---------------- site ----------------")
i_trees = s.index("// trees for context")
i_road = s.index("// road marking & kerbs/grass for context")
i_sky = s.index("// ---------------- lights / sky ----------------")
trees_code = s[i_trees:i_road]
blk17 = s[i_road:i_sky]
for a in ["box(-30, -9, -0.2, 110, -8.85, -0.19, M({ color: 0xf2f2f2, roughness: .8 }), groups.site, { cast: false });\n",
          "box(-40, -16.2, -0.25, 120, -15.0, 0.0, mat.apron, groups.site);\n", "box(-40, 22.0, -0.25, 120, 23.2, 0.0, mat.apron, groups.site);\n",
          "const shutters = [];\n", "const fx = [];\n", "const areaLights = [];\n"]:
    blk17 = rep(blk17, a, "")
for a in ["// site: concrete yard + road marking\n", "box(-8, -9, -0.2, 26, 9, -0.01, mat.apron, groups.site, { cast: false });\n",
          "box(-8, -7.6, -0.01, 26, -7.45, 0.0, M({ color: 0xf2f2f2, roughness: .8 }), groups.site, { cast: false });\n",
          "const shutters = [];\n", "const fx = [];\n", "const areaLights = [];\n"]:
    b057 = rep(b057, a, "")
# site trees: lighter geometry, positions from the lawn verges
trees_code = rep(trees_code, "new THREE.IcosahedronGeometry(r, 3)", "new THREE.IcosahedronGeometry(r, 2)")
trees_code = rep(trees_code, "for (let i = 0; i < 10; i++) {\n      const a = rnd() * Math.PI * 2, el = (rnd() - .15) * 1.3",
                 "for (let i = 0; i < 6; i++) {\n      const a = rnd() * Math.PI * 2, el = (rnd() - .15) * 1.3")
i_loop = trees_code.index("  for (let x = -24; x <= 100; x += 10)")
j_loop = trees_code.index("\n", i_loop)
trees_code = trees_code[:i_loop] + "  TREES.forEach(([x, y]) => tree(x, y, .75 + rnd() * .45));" + trees_code[j_loop:]

site_block = """// ---------------- site (whole project, A-2001 site coordinates, metres) ----------------
const TREES = %s;
const BUILDINGS = %s;
const GROUND = %s;
const shutters = [], fx = [], areaLights = [];
let gx = [];
// outer grass + georeferenced ground (roads / lawns / paving classified from C-0100)
const grassTex = canvasTex(512, 512, (g, w, h) => { g.fillStyle = '#6e8f47'; g.fillRect(0, 0, w, h); for (let i = 0; i < 9000; i++) { g.fillStyle = `hsl(${85 + Math.random() * 25},${35 + Math.random() * 20}%%,${28 + Math.random() * 18}%%)`; g.fillRect(Math.random() * w, Math.random() * h, 2, 2); } }, 1500, 1500);
const ground = new THREE.Mesh(new THREE.PlaneGeometry(9000, 9000), M({ map: grassTex, roughness: 1 })); ground.rotation.x = -Math.PI / 2; ground.position.y = -1.5;
ground.receiveShadow = true; groups.site.add(ground);
let _groundOk; window._groundReady = new Promise(r => _groundOk = r);   // shots must wait for the ground texture to decode
{ const tex = new THREE.TextureLoader().load('%s', () => _groundOk()); tex.colorSpace = THREE.SRGBColorSpace; tex.anisotropy = 8;
  const w = GROUND.x1 - GROUND.x0, h = GROUND.y1 - GROUND.y0;
  const pad = new THREE.Mesh(new THREE.PlaneGeometry(w, h), M({ map: tex, roughness: .95 })); pad.rotation.x = -Math.PI / 2;
  pad.position.copy(V((GROUND.x0 + GROUND.x1) / 2, (GROUND.y0 + GROUND.y1) / 2, -0.02)); pad.receiveShadow = true; groups.site.add(pad); }
%s
// ---- massing for every master-plan footprint (heights: A-2001 table for Phase 16, estimated for existing) ----
const mm = {
  newWall: M({ map: corrTex('#e7ecf0', '#bcc5cd', true), roughness: .45, metalness: .3 }), newRoof: M({ map: corrTex('#f2f4f5', '#d3d8dc', false), roughness: .45, metalness: .35 }),
  hallWall: M({ map: corrTex('#cfd4d8', '#a8b0b7', true), roughness: .5, metalness: .3 }), hallRoof: M({ map: corrTex('#a9b0b6', '#8d959c', false), roughness: .5, metalness: .4 }),
  procWall: M({ color: 0xe2e1dc, roughness: .85 }), procRoof: M({ color: 0x9da2a6, roughness: .8 }),
  office: M({ map: canvasTex(256, 256, (g, w, h) => { g.fillStyle = '#e8e6e0'; g.fillRect(0, 0, w, h); g.fillStyle = '#4b6378'; g.fillRect(0, h * .35, w, h * .3); g.fillStyle = '#e8e6e0'; for (let i = 0; i < 8; i++) g.fillRect(i * w / 8, h * .35, 4, h * .3); }, 1, 1), roughness: .6 }),
  shedWall: M({ color: 0xd6d6cf, roughness: .8 }), shedRoof: M({ color: 0x8f9499, roughness: .7, metalness: .2 }),
  yard: M({ map: concTex, color: 0xdedbd2, roughness: .95 }), tank: M({ color: 0xdcdfe2, roughness: .35, metalness: .6 }),
  rack: M({ color: 0x8a8f94, roughness: .5, metalness: .6 }), canopy: M({ color: 0xc9d0d6, roughness: .5, metalness: .4 }),
  skylight: M({ color: 0x2f5fa8, roughness: .2, metalness: .3, emissive: 0x0b1f3d }),
};
function extrude(pts, z0, z1, wallM, roofM, grp = groups.building) {
  pts = pts.filter((p, i) => { const q = pts[(i + 1) % pts.length]; return Math.hypot(p[0] - q[0], p[1] - q[1]) > .02; });   // drop repeated / closing points (NaN in ExtrudeGeometry)
  if (pts.length < 3) return null;
  const shape = new THREE.Shape(pts.map(([x, y]) => new THREE.Vector2(x, y)));
  const g = new THREE.ExtrudeGeometry(shape, { depth: z1 - z0, bevelEnabled: false });
  const me = new THREE.Mesh(g, [roofM, wallM]); me.rotation.x = -Math.PI / 2; me.position.y = z0;
  me.castShadow = true; me.receiveShadow = true; grp.add(me); return me;
}
function posts(pts, z1, every, m) {
  for (let i = 0; i < pts.length; i++) {
    const [ax, ay] = pts[i], [bx, by] = pts[(i + 1) %% pts.length], L = Math.hypot(bx - ax, by - ay), n = Math.max(1, Math.round(L / every));
    for (let k = 0; k < n; k++) { const x = ax + (bx - ax) * k / n, y = ay + (by - ay) * k / n; box(x - .15, y - .15, 0, x + .15, y + .15, z1, m); }
  }
}
BUILDINGS.forEach(b => {
  const P = b.pts, h = b.h;
  if (b.kind === 'new') {
    extrude(P, 0, 1.2, mat.navy, mm.newRoof); extrude(P, 1.2, h, mm.newWall, mm.newRoof);
    if (b.area > 10000) {                       // 06B/07B roof skylights (blue strips, as in the A-0002 3D view)
      const xs = P.map(p => p[0]), ys = P.map(p => p[1]), x0 = Math.min(...xs), x1 = Math.max(...xs), y0 = Math.min(...ys), y1 = Math.max(...ys);
      [[x0 + 30, 30.5, 2.4, 60], [x0 + 110, 30.5, 2.4, 60], [x0 + 190, 30.5, 2.4, 60], [x1 - 70, 70, 2.4, 50]].forEach(([sx, sy, sw, sl]) => box(sx, sy, h, sx + sl, sy + sw, h + .25, mm.skylight));
    }
  } else if (b.kind === 'hall') extrude(P, 0, h, mm.hallWall, mm.hallRoof);
  else if (b.kind === 'process') { extrude(P, 0, h, mm.procWall, mm.procRoof); }
  else if (b.kind === 'office') extrude(P, 0, h, mm.office, mm.procRoof);
  else if (b.kind === 'shed' || b.kind === 'tank') extrude(P, 0, h, mm.shedWall, mm.shedRoof);
  else if (b.kind === 'yard') extrude(P, 0, h, mm.yard, mm.yard, groups.site);
  else if (b.kind === 'tankEST') { const xs = P.map(p => p[0]), ys = P.map(p => p[1]), cx = (Math.min(...xs) + Math.max(...xs)) / 2, cy = (Math.min(...ys) + Math.max(...ys)) / 2, r = Math.min(Math.max(...xs) - Math.min(...xs), Math.max(...ys) - Math.min(...ys)) / 2;
    const t = new THREE.Mesh(new THREE.CylinderGeometry(r, r, h, 40), mm.tank); t.position.copy(V(cx, cy, h / 2)); t.castShadow = true; t.receiveShadow = true; groups.building.add(t); }
  else if (b.kind === 'canopy' || b.kind === 'walkway') { extrude(P, h - .25, h, mm.canopy, mm.canopy); posts(P, h - .25, 6, mm.rack); }
  else if (b.kind === 'piperack') { extrude(P, h - 1.2, h, mm.rack, mm.rack); posts(P, h - 1.2, 8, mm.rack); }
});

// ---- detailed building 17B (template block), relocated: grid 17-01/17-A -> site %s ----
OX = %s; OY = %s;
{ const n0 = fx.length;
%s
  for (let i = n0; i < fx.length; i++) { fx[i][0] += OX; fx[i][1] += OY; } }
// ---- detailed building 057 (HVAC example block), relocated: grid 57-1/57-A -> site %s ----
OX = %s; OY = %s;
{ const n0 = fx.length;
%s
  for (let i = n0; i < fx.length; i++) { fx[i][0] += OX; fx[i][1] += OY; } }
OX = 0; OY = 0;

""" % (json.dumps(TREES), json.dumps(B), json.dumps(G), GURI, trees_code,
       O17, O17[0], O17[1], blk17, O57, O57[0], O57[1], b057)
site_block = site_block.replace('fx.forEach(([x, y]) => {', 'fx.slice(n0).forEach(([x, y]) => {').replace('fx.forEach(([x, y, h]) => {', 'fx.slice(n0).forEach(([x, y, h]) => {')
s = s[:i_site] + site_block + s[i_sky:]

# ---- engine adjustments for a ~1 km site ----
s = rep(s, "const camera = new THREE.PerspectiveCamera(35, W / H, 0.1, 5000);", "const camera = new THREE.PerspectiveCamera(35, W / H, 0.1, 12000);")
s = rep(s, "new THREE.SphereGeometry(1400, 32, 16)", "new THREE.SphereGeometry(5000, 32, 16)")
s = rep(s, "skyDome.position.set(36, 0, -5);", "skyDome.position.set(-170, 0, -20);")
s = s.replace("scene.fog = new THREE.Fog(hor, 160, 1300);", "scene.fog = new THREE.Fog(hor, 900, 4800);")
s = rep(s, "renderer.toneMappingExposure = 1.05; bloom.strength = .55; bloom.threshold = .75;", "renderer.toneMappingExposure = 1.0; bloom.strength = .45; bloom.threshold = .93;")
s = rep(s, "sun.shadow.mapSize.set(4096, 4096);", "sun.shadow.mapSize.set(4096, 4096);")
s = s.replace("hemi.intensity = .75; scene.environmentIntensity = .55;", "hemi.intensity = 1.05; scene.environmentIntensity = .85;")   # brighter fill: deep shadows between tall halls
# per-view sun/shadow frame (aerials need a wide frustum, close-ups a tight one)
s = rep(s, "setMood(v.mood); groups.roof.visible = v.roof;",
        "setMood(v.mood); { const r = v.sh || 120, T = V(...v.tgt), d = sun.position.clone().sub(V(36, 5, 0)).normalize(); sun.target.position.copy(T); sun.position.copy(T).addScaledVector(d, r * 2.5);"
        " Object.assign(sun.shadow.camera, { left: -r, right: r, top: r, bottom: -r, near: 1, far: r * 6 }); sun.shadow.camera.updateProjectionMatrix(); renderer.shadowMap.needsUpdate = true; }\n  groups.roof.visible = v.roof;")
# views
va = s.index("const views = {"); vb = s.index("};", va) + 2
s = s[:va] + """const views = {
  'site-aerial-southwest': { mood: 'day', cam: [-980, -620, 520], tgt: [-180, 40, 0], fov: 32, roof: true, sh: 650 },
  'site-aerial-northeast': { mood: 'day', cam: [420, 720, 470], tgt: [-180, 40, 0], fov: 34, roof: true, sh: 650 },
  'phase16-birdseye': { mood: 'day', cam: [-110, -90, 210], tgt: [-270, 85, 0], fov: 44, roof: true, sh: 260 },
  'relocated-17B-waste-area': { mood: 'day', cam: [-300, 112, 32], tgt: [-238, 150, 3], fov: 42, roof: true, sh: 90 },
  'relocated-057-substation': { mood: 'day', cam: [-178, 71, 4], tgt: [-185.5, 87, 3.2], fov: 56, roof: true, sh: 60 },
  'site-dusk-aerial': { mood: 'dusk', cam: [-760, -470, 330], tgt: [-180, 40, 0], fov: 34, roof: true, sh: 650 },
  'street-north-road': { mood: 'day', cam: [-292, 170, 1.7], tgt: [-205, 152, 5], fov: 60, roof: true, sh: 110 },
};""" + s[vb:]
s = rep(s, "shutters.forEach(p => p.visible = !v.open);", "shutters.forEach(p => p.visible = !v.open);") if "shutters.forEach(p => p.visible = !v.open);" in s else rep(s,
        "groups.labels.visible = !!v.labels;", "groups.labels.visible = !!v.labels; shutters.forEach(p => p.visible = !v.open);")
# tour: aerial -> Phase 16 cluster -> 17B road -> 057 eye level -> rise north-east
ta = s.index("const tour = ["); tb = s.index("];", ta) + 2
s = s[:ta] + """const tour = [
  [0,   -980, -620, 520,  -180, 40, 0],   // master-plan aerial
  [10,  -620, -180, 300,  -260, 60, 0],
  [20,  -360, 20, 140,    -270, 110, 5],  // over 07B / 06B roofs
  [30,  -300, 120, 45,    -238, 150, 4],  // 17B waste handling area (relocated)
  [38,  -282, 168, 6,     -238, 150, 3],  // down onto the north road
  [46,  -225, 168, 1.7,   -195, 150, 3],  // drive along 17B
  [54,  -188, 140, 1.7,   -186, 95, 3],   // turn south towards 057
  [60,  -186, 104, 1.7,   -186, 87, 3.5],
  [66,  -172, 82, 1.7,    -186, 87, 3],   // 057 east side, stairs & EAF
  [74,  -150, 60, 40,     -186, 87, 2],   // rise
  [86,  420, 720, 470,    -180, 40, 0],   // finish north-east aerial
];""" + s[tb:]
# walk mode: zone lights per room in site coords, spawn near 057, HUD shows site coordinates
s = rep(s, "const zoneDefs = [[0.2, 12], [12, 16], [16, 20], [20, 28], [28, 38], [38, 43], [43, 48], [48, 58], [58, 64], [64, 71.8]];",
        "const zoneDefs = [" + ", ".join(f"[{O17[0]+a:.2f}, {O17[0]+b:.2f}, {O17[1]+.2:.2f}, {O17[1]+9.8:.2f}, 4.5]" for a, b in [[0.2, 12], [12, 16], [16, 20], [20, 28], [28, 38], [38, 43], [43, 48], [48, 58], [58, 64], [64, 71.8]])
        + ", " + ", ".join(f"[{O57[0]+a:.2f}, {O57[0]+b:.2f}, {O57[1]+.18:.2f}, {O57[1]+5.32:.2f}, 4.3]" for a, b in [[0.18, 9.75], [9.95, 13.55], [13.75, 16.82]]) + "];")
s = rep(s, "const zones = zoneDefs.map(([a, b]) => {\n    const n = fx.filter(([x]) => x > a && x < b).length, w = b - a - .4, h = 9.2;\n    const l = new THREE.RectAreaLight(0xfff3e0, 0, w, h); l.position.copy(V((a + b) / 2, 5, 4.5)); l.rotation.x = -Math.PI / 2;",
        "const zones = zoneDefs.map(([a, b, c, e, zh]) => {\n    const n = fx.filter(([x, y]) => x > a && x < b && y > c && y < e).length, w = b - a - .4, h = e - c;\n    const l = new THREE.RectAreaLight(0xfff3e0, 0, w, h); l.position.copy(V((a + b) / 2, (c + e) / 2, zh)); l.rotation.x = -Math.PI / 2;")
s = rep(s, "const player = { feet: V(10, -5, 0),", "const player = { feet: V(-170, 72, 0),")
s = rep(s, "camera.lookAt(V(14, 5, 1.8));", "camera.lookAt(V(-186, 87, 2));")
s = rep(s, "Trục ${gridRef(mx)} · cách trục A ${my.toFixed(1)} m", "Site X ${mx.toFixed(0)} · Y ${my.toFixed(0)} m")
s = rep(s, "if (e.code === 'KeyO') { const open = shutters[0].visible;", "if (e.code === 'KeyO' && shutters.length) { const open = shutters[0].visible;")
# render/video mode: merge static meshes too (thousands of meshes otherwise)
s = rep(s, "if (!WALK) {\n  show(Q.get('v') || 'exterior-day-southwest');",
        "if (!WALK) {\n  window.mergeStaticRender && window.mergeStaticRender();\n  show(Q.get('v') || 'site-aerial-southwest');")
os.makedirs(S + '/rsite', exist_ok=True)
open(S + '/rsite/index.html', 'w', encoding='utf-8').write(s)
print('ok', round(len(s) / 1e6, 2), 'MB')
