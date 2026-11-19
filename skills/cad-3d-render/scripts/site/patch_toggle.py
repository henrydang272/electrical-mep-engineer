import sys
F = sys.argv[1]; s = open(F, encoding='utf-8').read()
def rep(a, b, n=1):
    global s
    c = s.count(a); assert c == n, (a[:90], c); s = s.replace(a, b)

rep("const views = {\n", r"""// ---- show / hide buildings: Phase-16 package list (A-2001 table) + existing context ----
const P16 = [['06B', 'Canning Area & Unloading Bay', '16.2 m'], ['07B', 'Finished Goods Warehouse', '16.2 m'], ['LBY', 'Loading & Unloading Yard', '16.2 m'],
  ['04B', 'Utility Building', '5 m'], ['M01', 'Motorcycle Parking 1', '5 m'], ['M02', 'Motorcycle Parking 2', '5 m'], ['17B', 'Waste Handling Area', '5.9 m'],
  ['UD1', 'Unloading Docks', 'as existing'], ['057', 'New Packaging Substation', '5.5 m'], ['BMF', 'BMF', '-'], ['EST', 'Energy Storage Tank', '-'], ['ET1', 'Bottle Yard', '-']];
const hiddenTags = new Set(); let shuttersOpen = true;
function applyTags() {
  Object.values(groups).forEach(g => g.traverse(o => { const t = o.userData.tag; if (!t) return;
    if (o.userData.merged) o.visible = !hiddenTags.has(t);
    else if (shutters.includes(o)) o.visible = !hiddenTags.has(t) && !shuttersOpen; }));
  codeLabels.children.forEach(l => l.visible = !hiddenTags.has(l.userData.tag));
  renderer.shadowMap.needsUpdate = true;
}
window.setHidden = codes => { hiddenTags.clear(); (codes || []).forEach(c => hiddenTags.add(c)); applyTags(); };
// floating code tags above each Phase-16 building (screen-size sprites)
const codeLabels = new THREE.Group(); codeLabels.visible = false; scene.add(codeLabels);
{ const top = {};
  BUILDINGS.forEach(b => { if (!b.code) return; const t = top[b.code] ||= { x0: 1e9, x1: -1e9, y0: 1e9, y1: -1e9, h: 0 };
    b.pts.forEach(([x, y]) => { t.x0 = Math.min(t.x0, x); t.x1 = Math.max(t.x1, x); t.y0 = Math.min(t.y0, y); t.y1 = Math.max(t.y1, y); }); t.h = Math.max(t.h, b.h); });
  top['17B'] = { x0: -274.08, x1: -202.08, y0: 144.5, y1: 154.5, h: 5.9 }; top['057'] = { x0: -193.41, x1: -176.41, y0: 84.1, y1: 89.6, h: 5.5 };
  P16.forEach(([code, name]) => { const t = top[code]; if (!t) return;
    const c = document.createElement('canvas'); c.width = 512; c.height = 160; const g = c.getContext('2d');
    g.fillStyle = 'rgba(16,32,58,.9)'; g.beginPath(); g.roundRect(4, 4, 504, 152, 30); g.fill(); g.strokeStyle = '#ffd25e'; g.lineWidth = 5; g.stroke();
    g.textAlign = 'center'; g.fillStyle = '#ffd25e'; g.font = 'bold 66px Segoe UI, Arial'; g.fillText(code, 256, 74);
    g.fillStyle = '#fff'; g.font = '600 34px Segoe UI, Arial'; g.fillText(name.length > 26 ? name.slice(0, 25) + '…' : name, 256, 128);
    const tx = new THREE.CanvasTexture(c); tx.colorSpace = THREE.SRGBColorSpace;
    const sp = new THREE.Sprite(new THREE.SpriteMaterial({ map: tx, depthTest: false, sizeAttenuation: false }));
    sp.scale.set(.16, .05, 1); sp.position.copy(V((t.x0 + t.x1) / 2, (t.y0 + t.y1) / 2, t.h + 4)); sp.renderOrder = 20; sp.userData.tag = code; codeLabels.add(sp); }); }

const views = {
""")
rep("  'site-dusk-aerial':", "  'phase16-package-only': { mood: 'day', cam: [-780, -560, 560], tgt: [-230, 40, 0], fov: 36, roof: true, sh: 650, hide: ['EXIST'], codes: true },\n  'phase16-package-labelled': { mood: 'day', cam: [-780, -560, 560], tgt: [-230, 40, 0], fov: 36, roof: true, sh: 650, codes: true },\n  'site-dusk-aerial':")
rep("  groups.roof.visible = v.roof; groups.labels.visible = !!v.labels; shutters.forEach(p => p.visible = !v.open);",
    "  groups.roof.visible = v.roof; groups.labels.visible = !!v.labels; shuttersOpen = !!v.open; window.setHidden(v.hide); codeLabels.visible = !!v.codes;")
rep("const setShutters = open => shutters.forEach(s => s.visible = !open);",
    "const setShutters = open => { shuttersOpen = open; shutters.forEach(s => s.visible = !open && !hiddenTags.has(s.userData.tag)); };")
rep("  show(Q.get('v') || 'site-aerial-southwest');\n", "  show(Q.get('v') || 'site-aerial-southwest');\n  if (Q.get('hide')) { window.setHidden(Q.get('hide').split(',')); composer.render(); }\n")
rep("if (b.max.y - b.min.y > .3) boxes.push(b);", "if (b.max.y - b.min.y > .3) { b.tag = o.userData.tag; boxes.push(b); }")
rep("      if (b.max.y <= lo || b.min.y >= hi) continue;\n", "      if (b.max.y <= lo || b.min.y >= hi || hiddenTags.has(b.tag)) continue;\n")
rep("const h = ray.intersectObjects(groundList, false)[0];", "const h = ray.intersectObjects(groundList, false).find(i => !hiddenTags.has(i.object.userData.tag));")
rep("    <div id=\"hud\"></div><div id=\"cross\"></div><div id=\"toast\"></div>`);\n",
r"""    <div id="hud"></div><div id="cross"></div><div id="toast"></div>
    <div id="bp"><h3><span>Khối nhà · Phase 16</span><span id="bpMin">–</span></h3><div class="body">
      ${P16.map(([c, n, h]) => `<label title="${n} · H ${h}"><input type="checkbox" data-t="${c}" checked><code>${c}</code><span>${n}</span></label>`).join('')}
      <label style="margin-top:4px;border-top:1px solid rgba(255,255,255,.12);padding-top:5px"><input type="checkbox" data-t="EXIST" checked><code>—</code><span>Nhà hiện hữu (bối cảnh)</span></label>
      <label><input type="checkbox" id="bpCodes"><code>#</code><span>Nhãn mã nhà</span></label>
      <div class="row"><button data-a="all">Hiện tất cả</button><button data-a="p16">Chỉ Phase 16</button><button data-a="none">Ẩn tất cả</button></div>
      <div class="tip">Phím <b>B</b>: nhả chuột để bấm bảng này</div></div></div>`);
  document.head.insertAdjacentHTML('beforeend', `<style>
    #bp{position:fixed;right:14px;top:14px;z-index:7;background:rgba(16,32,58,.9);color:#fff;font:13px/1.35 Segoe UI,Arial;border:1px solid #3b5b8f;border-radius:12px;padding:10px 12px;width:270px;user-select:none}
    #bp h3{margin:0 0 6px;font-size:14px;display:flex;justify-content:space-between;cursor:pointer} #bp.min .body{display:none}
    #bp label{display:flex;gap:7px;align-items:center;padding:2px 0;cursor:pointer} #bp label:hover{color:#ffd25e}
    #bp code{color:#ffd25e;font:600 12px Consolas,monospace;min-width:30px} #bp .tip{margin-top:6px;color:#9fb6d8;font-size:12px} #bp .tip b{color:#ffd25e}
    #bp .row{display:flex;gap:5px;margin-top:8px} #bp button{flex:1;background:#24406e;color:#fff;border:1px solid #5a7bb5;border-radius:6px;padding:4px 0;font:12px Segoe UI,Arial;cursor:pointer} #bp button:hover{background:#2f5592}
  </style>`);
  { const bp = document.getElementById('bp'), boxesEl = [...bp.querySelectorAll('input[data-t]')];
    bp.addEventListener('mousedown', e => e.stopPropagation()); bp.addEventListener('click', e => e.stopPropagation());
    const sync = () => window.setHidden(boxesEl.filter(i => !i.checked).map(i => i.dataset.t));
    boxesEl.forEach(i => i.addEventListener('change', sync));
    bp.querySelector('#bpCodes').addEventListener('change', e => codeLabels.visible = e.target.checked);
    bp.querySelectorAll('button').forEach(b => b.addEventListener('click', () => { const a = b.dataset.a; boxesEl.forEach(i => i.checked = a === 'all' || (a === 'p16' && i.dataset.t !== 'EXIST')); sync(); }));
    bp.querySelector('h3').addEventListener('click', () => { bp.classList.toggle('min'); document.getElementById('bpMin').textContent = bp.classList.contains('min') ? '+' : '–'; }); }
""")
rep("        <tr><td><kbd>Esc</kbd></td><td>Thoát điều khiển</td></tr>", "        <tr><td><kbd>B</kbd></td><td>Bảng ẩn / hiện từng khối nhà (Phase 16)</td></tr>\n        <tr><td><kbd>Esc</kbd></td><td>Thoát điều khiển</td></tr>")
rep("    if (e.code === 'KeyF') {", "    if (e.code === 'KeyB') { controls.unlock(); document.getElementById('bp').classList.remove('min'); return; }\n    if (e.code === 'KeyF') {")
open(F, 'w', encoding='utf-8').write(s); print('ok')
