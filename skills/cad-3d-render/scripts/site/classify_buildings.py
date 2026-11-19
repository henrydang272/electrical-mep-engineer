"""Turn the labelled master-plan footprints into a building list for the site scene.
Heights: Phase-16 buildings from the A-2001 area/height table; existing buildings ESTIMATED
from the A-0002 3D master-plan view (marked 'est': True) - no drawing gives them.
"""
import json, sys
d = sys.argv[1]
data = json.load(open(d + '/footprints.json'))
polys = data['polys']

def inside(p, P):
    x, y = p; c = False
    for i in range(len(P)):
        (x1, y1), (x2, y2) = P[i], P[(i + 1) % len(P)]
        if (y1 > y) != (y2 > y) and x < (x2 - x1) * (y - y1) / (y2 - y1) + x1: c = not c
    return c
def centroid(P): return (sum(a for a, b in P) / len(P), sum(b for a, b in P) / len(P))

# label -> (height m, kind, name, estimated?)
H = {
  '06B': (16.2, 'new', '06B/07B/LBY Canning area, FG warehouse, loading yard', False),
  'ET': (0.3, 'yard', 'ET1 Bottle yard (renovation)', False),
  '7A': (13, 'hall', 'Existing packaging halls 5/6/6A/7/7A', True),
  '3A': (24, 'process', 'Brewing / cellar block 3-3A', True), '3B': (16, 'process', '3B', True), '3C': (16, 'process', '3C', True),
  '2': (18, 'process', 'Brew house & service block 2', True), '2B': (12, 'process', '2B', True), 'BF': (12, 'process', 'BMF (renovation)', True),
  '4': (14, 'process', 'Utility 4', True), 'ES': (12, 'process', 'Utility 4 / ES', True),
  '18': (7, 'tank', 'Waste water treatment 18', True), '18A': (9, 'shed', '18A', True),
  '40': (9, 'office', 'Office 40', True), '39': (8, 'office', '39', True),
  '1B': (10, 'process', '1B', True), '1C': (10, 'process', '1C', True), '1D': (10, 'process', '1D', True), '32': (8, 'shed', '32', True),
  '16': (8, 'shed', '16', True), '13': (6, 'shed', '13', True), '14': (6, 'shed', '14', True), '20': (6, 'shed', '20', True),
  '21': (5, 'shed', '21', True), '23': (5, 'shed', '23', True), '62': (8, 'shed', '62', True), 'WA': (4, 'shed', 'WA', True),
  '24': (0.3, 'yard', 'Wooden pallet area 24', True),
  '15': (7, 'piperack', 'Pipe rack 15/15B', True), '15B': (7, 'piperack', 'Pipe rack 15/15B', True),
  '41': (3.1, 'walkway', 'Covered walkway 41', True),
}
SKIP_BBOX = {  # replaced by the detailed models
  '17B': [-274.08, 144.5, -202.08, 154.5], '057': [-193.52, 84.1, -176.52, 89.6]}
SPECIAL = {   # unlabeled polygons identified from the site plan / labels nearby
  (-41.46, 100.1): (5, 'new', '04B Utility building (Phase 16)', False),
  (-130.07, 78.67): (10, 'tankEST', 'EST Energy storage tank', False),
  (-199.51, 344.21): (5, 'canopy', 'M01 Motorcycle parking 1', False), (-192.51, 344.21): (5, 'canopy', 'M01 Motorcycle parking 1', False),
  (62.82, -145.81): (14, 'hall', 'Existing hall 30', True), (62.62, -253.88): (12, 'hall', 'Existing 27B/28', True),
}
out = []; seen = set()
big = sorted(polys, key=lambda p: -p['area'])
for p in big:
    bb = p['bbox']; P = [tuple(q) for q in p['pts']]
    if any(abs(bb[0] - v[0]) < .3 and abs(bb[1] - v[1]) < .3 for v in SKIP_BBOX.values()): continue
    key = (round(bb[0], 2), round(bb[1], 2), round(bb[2], 2), round(bb[3], 2))
    if key in seen: continue
    seen.add(key)
    spec = next((v for k, v in SPECIAL.items() if abs(bb[0] - k[0]) < .3 and abs(bb[1] - k[1]) < .3), None)
    lab = next((l for l in p['label'] if l in H), None)
    if spec: h, kind, name, est = spec
    elif lab:
        h, kind, name, est = H[lab]
        if lab in ('15', '15B') and p['area'] < 1000: continue
    else:
        # unlabeled: skip if it sits inside a bigger already-kept footprint (inner rooms/equipment outlines)
        c = centroid(P)
        if any(inside(c, [tuple(q) for q in o['pts']]) for o in out if o['kind'] in ('hall', 'process', 'new')): continue
        import math
        per = sum(math.dist(P[i], P[(i + 1) % len(P)]) for i in range(len(P)))
        w = 2 * p['area'] / per          # true width (bbox width misses L-shaped walkways)
        if w < 4: h, kind, name, est = 3.1, 'walkway', 'Covered walkway / canopy', True
        else: h, kind, name, est = 6, 'shed', 'Existing ancillary building', True
    out.append({'name': name, 'kind': kind, 'h': h, 'est': est, 'area': p['area'], 'pts': [[round(a, 2), round(b, 2)] for a, b in P]})
json.dump(out, open(d + '/buildings.json', 'w'))
from collections import Counter
print(len(out), 'footprints kept;', Counter(o['kind'] for o in out))
for o in out[:25]: print(f"{o['area']:>9} {o['h']:>5} {o['kind']:<9} {'EST' if o['est'] else 'DWG'} {o['name']}")
