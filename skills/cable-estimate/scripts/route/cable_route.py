"""Cable route engine: shortest path along tray centre-lines, from a panel to its loads.

Data comes from the cad-qto cache (C:/qto/<project>): geom/<folder>__<stem>.json (exploded geometry,
texts) and extract/<folder>__<stem>.json (top-level inserts). Every drawing is moved into one
reference frame per building by its grid bubbles (translation only).
"""
import json, re, math, statistics, collections
import networkx as nx

QTO = "C:/qto/project"
_cache = {}


def geom(stem):
    k = ("g", stem)
    if k not in _cache:
        _cache[k] = json.load(open(f"{QTO}/geom/{stem}.json", encoding="utf8"))
    return _cache[k]


def extract(stem):
    k = ("e", stem)
    if k not in _cache:
        _cache[k] = json.load(open(f"{QTO}/extract/{stem}.json", encoding="utf8"))
    return _cache[k]


VGRID = re.compile(r"^\d{1,2}-[A-Z]\d?$")      # 6-A, 6-A1, 7-C : vertical grid line -> x
HGRID = re.compile(r"^\d{1,2}[A-Z]-\d\d$")     # 6B-01, 7B-03   : horizontal grid line -> y


def grid_marks(stem):
    v, h = collections.defaultdict(list), collections.defaultdict(list)
    for x in geom(stem):
        if x[0] != "T":
            continue
        t = str(x[5]).strip()
        if VGRID.match(t):
            v[t].append(x[3])
        elif HGRID.match(t):
            h[t].append(x[4])
    return v, h


def offset(stem, ref):
    """(dx, dy) to add to `stem` coordinates to land in `ref` frame."""
    if stem == ref:
        return 0.0, 0.0
    v1, h1 = grid_marks(stem)
    v0, h0 = grid_marks(ref)
    dx = [statistics.median(v0[k]) - statistics.median(v1[k]) for k in v1 if k in v0]
    dy = [statistics.median(h0[k]) - statistics.median(h1[k]) for k in h1 if k in h0]
    if not dx or not dy:
        raise ValueError(f"no common grid between {stem} and {ref}")
    return statistics.median(dx), statistics.median(dy)


# ---------------------------------------------------------------- tray graph
def seg_point_dist(p, a, b):
    ax, ay = a; bx, by = b; px, py = p
    dx, dy = bx - ax, by - ay
    L2 = dx * dx + dy * dy
    t = 0.0 if L2 == 0 else max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / L2))
    q = (ax + t * dx, ay + t * dy)
    return math.dist(p, q), q, t


class TrayGraph:
    def __init__(self, segs, gap=1500.0):
        self.segs = [(tuple(a), tuple(b)) for a, b in segs if math.dist(a, b) > 1]
        splits = [[0.0, 1.0] for _ in self.segs]
        extra = []
        for i, (a, b) in enumerate(self.segs):
            for p in (a, b):
                for j, (c, d) in enumerate(self.segs):
                    if i == j:
                        continue
                    dist, q, t = seg_point_dist(p, c, d)
                    if dist < gap:
                        splits[j].append(t)
                        extra.append((p, q, dist))
        # crossings
        for i, (a, b) in enumerate(self.segs):
            for j in range(i + 1, len(self.segs)):
                c, d = self.segs[j]
                r = _cross(a, b, c, d)
                if r:
                    splits[i].append(r[0]); splits[j].append(r[1])
        G = nx.Graph()
        for (a, b), ts in zip(self.segs, splits):
            pts = [(_r(a[0] + t * (b[0] - a[0])), _r(a[1] + t * (b[1] - a[1]))) for t in sorted(set(ts))]
            for p, q in zip(pts, pts[1:]):
                if p != q:
                    G.add_edge(p, q, w=math.dist(p, q))
        for p, q, dist in extra:
            p, q = (_r(p[0]), _r(p[1])), (_r(q[0]), _r(q[1]))
            if p != q:
                G.add_edge(p, q, w=dist)
        self.G = G

    def snap(self, p):
        """Nearest point on the network: (dist, point, edge)."""
        best = None
        for u, v in self.G.edges:
            d, q, _ = seg_point_dist(p, u, v)
            if best is None or d < best[0]:
                best = (d, (_r(q[0]), _r(q[1])), (u, v))
        return best

    def add_point(self, p):
        d, q, (u, v) = self.snap(p)
        if q not in self.G:
            w = self.G[u][v]["w"]
            self.G.remove_edge(u, v)
            self.G.add_edge(u, q, w=math.dist(u, q))
            self.G.add_edge(q, v, w=math.dist(q, v))
        return q, d

    def path(self, a, b):
        pts = nx.shortest_path(self.G, a, b, weight="w")
        return pts, sum(math.dist(p, q) for p, q in zip(pts, pts[1:]))


def _r(v):
    return round(v, 1)


def _cross(a, b, c, d):
    (x1, y1), (x2, y2), (x3, y3), (x4, y4) = a, b, c, d
    den = (x1 - x2) * (y3 - y4) - (y1 - y2) * (x3 - x4)
    if abs(den) < 1e-9:
        return None
    t = ((x1 - x3) * (y3 - y4) - (y1 - y3) * (x3 - x4)) / den
    u = -((x1 - x2) * (y1 - y3) - (y1 - y2) * (x1 - x3)) / den
    if 0 < t < 1 and 0 < u < 1:
        return t, u
    return None


def manhattan(a, b):
    """L-shaped connector a -> b (x first)."""
    if abs(a[0] - b[0]) < 1 or abs(a[1] - b[1]) < 1:
        return [a, b]
    return [a, (b[0], a[1]), b]


def plen(pts):
    return sum(math.dist(p, q) for p, q in zip(pts, pts[1:]))


def dedupe(pts, tol=100):
    """Merge devices closer than tol mm - adjacent sheets both draw the strip at their shared grid line."""
    out = []
    for p in pts:
        if all(math.dist(p, q) >= tol for q in out):
            out.append(p)
    return out


assert dedupe([(0, 0), (1, 1), (500, 0)]) == [(0, 0), (500, 0)]


def column_face(stem, centre, sym_half=700, reach=2500):
    """Wall/column-mounted device (power box, typical detail 4): the cable ends on the face of the steel
    column it is bolted to. Returns the point on the nearest column face at the device's y (same frame as
    `stem`), or None when no column is drawn beside the device."""
    cx, cy = centre
    pts = []
    for x in geom(stem):
        if "COLUMN" not in x[1].upper():
            continue
        cand = [(x[3], x[4]), (x[5], x[6])] if x[0] == "L" else [tuple(p) for p in x[3]] if x[0] == "P" else []
        pts += [p for p in cand if abs(p[1] - cy) < 400 and sym_half * 0.8 < abs(p[0] - cx) < reach]
    if not pts:
        return None
    fx = min(pts, key=lambda p: abs(p[0] - cx))[0]
    return (fx, cy)
