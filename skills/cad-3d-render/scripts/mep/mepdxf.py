"""Parse MEP DXF copies (Revit exports, mm, Revit frame): double-line pipes/ducts -> centrelines + size,
sprinkler heads, equipment inserts, level labels (COP/BOP/BOD). Results cached as JSON next to the DXF."""
import ezdxf, json, os, re, math, sys, collections

def pair_lines(segs, dmin, dmax, min_len=300):
    """segs: [(x1,y1,x2,y2)] axis-aligned; returns centrelines [(x1,y1,x2,y2,d)] in mm"""
    out = []
    for axis in ('h', 'v'):
        L = []
        for x1, y1, x2, y2 in segs:
            if axis == 'h' and abs(y1 - y2) < 2 and abs(x2 - x1) >= min_len: L.append((y1, min(x1, x2), max(x1, x2)))
            if axis == 'v' and abs(x1 - x2) < 2 and abs(y2 - y1) >= min_len: L.append((x1, min(y1, y2), max(y1, y2)))
        L.sort()
        used = [False] * len(L)
        for i, (c, a, b) in enumerate(L):
            if used[i]: continue
            best = None
            for j in range(i + 1, len(L)):
                c2, a2, b2 = L[j]
                if c2 - c > dmax: break
                if c2 - c < dmin or used[j]: continue
                ov = min(b, b2) - max(a, a2)
                if ov > .6 * min(b - a, b2 - a2):
                    best = j; break
            if best is None: continue
            c2, a2, b2 = L[best]; used[i] = used[best] = True
            a0, b0, cm, d = max(a, a2), min(b, b2), (c + c2) / 2, c2 - c
            out.append((a0, cm, b0, cm, d) if axis == 'h' else (cm, a0, cm, b0, d))
    return out

def parse(path, pipe_layers, head_rx=r'^SPK', equip_rx=None, dmin=20, dmax=260):
    cache = path + '.json'
    if os.path.exists(cache) and os.path.getmtime(cache) > os.path.getmtime(path): return json.load(open(cache))
    doc = ezdxf.readfile(path); msp = doc.modelspace()
    segs, heads, labels, equip, gx, gy = [], [], [], [], set(), set()
    for e in msp:
        t, lay = e.dxftype(), e.dxf.layer
        if t == 'LINE' and 'GRID' in lay.upper():
            s0, e0 = e.dxf.start, e.dxf.end
            if abs(s0.x - e0.x) < 1 and abs(s0.y - e0.y) > 5000: gx.add(round(s0.x))
            if abs(s0.y - e0.y) < 1 and abs(s0.x - e0.x) > 5000: gy.add(round(s0.y))
        if t == 'LINE' and any(re.search(p, lay) for p in pipe_layers):
            s, en = e.dxf.start, e.dxf.end; segs.append((s.x, s.y, en.x, en.y))
        elif t == 'INSERT':
            n = e.dxf.name; p = e.dxf.insert
            if re.search(head_rx, n): heads.append((round(p.x), round(p.y)))
            elif equip_rx and re.search(equip_rx, n): equip.append((n[:60], round(p.x), round(p.y), round(e.dxf.rotation, 1)))
        elif t in ('MTEXT', 'TEXT'):
            txt = e.plain_text() if t == 'MTEXT' else e.dxf.text
            m = re.search(r'(COP|BOP|BOD|COD)\s*[:=]?\s*FFL\s*\+?\s*(\d{3,5})', txt.replace('\n', ' '))
            if m:
                p = e.dxf.insert; labels.append((m.group(1), int(m.group(2)), round(p.x), round(p.y)))
    cl = pair_lines(segs, dmin, dmax)
    r = dict(gx=sorted(gx), gy=sorted(gy), centre=[[round(v) for v in c] for c in cl], heads=heads, labels=labels, equip=equip, nseg=len(segs))
    json.dump(r, open(cache, 'w')); return r

if __name__ == '__main__':
    r = parse(sys.argv[1], sys.argv[2].split(','))
    print(r['nseg'], 'segs ->', len(r['centre']), 'centrelines;', len(r['heads']), 'heads;', len(r['labels']), 'labels')
    print(collections.Counter(round(c[4]) for c in r['centre']).most_common(12))
    print(r['labels'][:12])
