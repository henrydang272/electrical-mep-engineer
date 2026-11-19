import sys, json, re
d = sys.argv[1]
rows = [l.rstrip('\n').split('|') for l in open(d + '/site_dump.txt', encoding='utf-8-sig')]
pts = lambda s: [tuple(map(float, p.split(','))) for p in s.split(' ') if p]
def area(P): return abs(sum(P[i][0]*P[(i+1)%len(P)][1]-P[(i+1)%len(P)][0]*P[i][1] for i in range(len(P))))/2
def inside(p, P):
    x, y = p; c = False
    for i in range(len(P)):
        (x1, y1), (x2, y2) = P[i], P[(i+1) % len(P)]
        if (y1 > y) != (y2 > y) and x < (x2-x1)*(y-y1)/(y2-y1)+x1: c = not c
    return c
labels = []
for r in rows:
    if r[1] == 'T':
        t = r[4].split(';')[-1].strip()
        if re.fullmatch(r'\d{1,2}[A-Z]?|ET|ES|WA|LBY|7B|6B|17B|57|M\d|BF|BT|P\d|EST|04B', t): labels.append((tuple(map(float, r[3].split(','))), t, r[2]))
polys = []
for r in rows:
    if r[1] == 'P':
        P = pts(r[4])
        closed = r[3] == 'True' or (len(P) > 3 and abs(P[0][0]-P[-1][0]) < .05 and abs(P[0][1]-P[-1][1]) < .05)
        if closed and len(P) >= 3 and area(P) > 25: polys.append({'layer': r[2], 'src': r[0], 'pts': P, 'area': round(area(P), 1)})
for p in polys:
    p['label'] = [t for (q, t, L) in labels if inside(q, p['pts'])]
    xs = [a for a, b in p['pts']]; ys = [b for a, b in p['pts']]
    p['bbox'] = [round(min(xs), 2), round(min(ys), 2), round(max(xs), 2), round(max(ys), 2)]
polys.sort(key=lambda p: -p['area'])
for p in polys: print(f"{p['area']:>9} {p['layer']:<20} {str(p['label']):<26} bbox {p['bbox']} n={len(p['pts'])}")
json.dump({'polys': polys, 'labels': labels}, open(d + '/footprints.json', 'w'))
print(len(polys), 'polygons; unlabeled:', sum(1 for p in polys if not p['label']), '; labels:', len(labels))
