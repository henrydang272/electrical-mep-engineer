"""Route one circuit and build the SOL numbers (AC number, AD/AB formulas) + polylines to draw."""
import math
from cable_route import manhattan, plen

LOOP_FLOOR, BASE_FLOOR = 1.2, 0.1      # floor-standing panel: bottom +0.1, cable climbs 1.2 to the CBs
LAMP_DROP = 0.35                        # trunking -> lamp gland (typical detail 7)


def f2(v):
    return f"{v:.2f}".rstrip("0").rstrip(".")


class Circuit:
    def __init__(self, net, level_fn, panel_pt, panel_kind="floor"):
        self.net, self.level = net, level_fn
        self.p0 = panel_pt
        self.kind = panel_kind
        self.paths, self.hor = [], 0.0
        self.ab_terms, self.ad_terms = [], []
        self.note = []
        q, d = net.add_point(panel_pt)
        self.cur = q
        lvl = level_fn(panel_pt)
        self.lvl0 = lvl
        conn = manhattan(panel_pt, q)
        self._draw(conn)
        self.ab_terms.append(plen(conn) / 1000)
        if panel_kind == "floor":
            self.ad_terms.append(f"({f2(lvl)}-{f2(BASE_FLOOR)})+{f2(LOOP_FLOOR)}")
        else:  # wall DB, bottom +1.2, loop 0.6
            self.ad_terms.append(f"({f2(lvl)}-1.2)+0.6")

    def _draw(self, pts):
        if len(pts) > 1:
            self.paths.append(pts)
            self.hor += plen(pts)

    def goto(self, p):
        q, d = self.net.add_point(p)
        pts, L = self.net.path(self.cur, q)
        self._draw(pts)
        self.cur = q
        return q, d

    def row(self, a, b, lamps, u_fn):
        """Lighting row on trunking: run to the near end, then to the far end; U at each lamp."""
        if math.dist(self.cur, a) > math.dist(self.cur, b):
            a, b = b, a
        self.goto(a)
        self.goto(b)
        us = []
        vert = abs(a[0] - b[0]) < 1
        sw = (lambda p: (p[1], p[0])) if vert else (lambda p: p)
        ry = sw(a)[1]
        for p, size in lamps:
            x, y = sw(p)
            ul, leg = u_fn(ry, (x, y), size)
            sgn = -1 if y <= ry else 1
            f = ry + sgn * (50 + leg)
            w = (size - 140) / 2 if size < 1000 else 70
            self._draw([sw(q) for q in [(x - w, ry), (x - w, f), (x + w, f), (x + w, ry)]])
            us.append(ul / 1000)
        if us:
            u = sum(us) / len(us)
            self.ab_terms.append(f"{len(us)}*{f2(u)}")
            self.ad_terms.append(f"{len(us)}*({f2(LAMP_DROP)}+{f2(LAMP_DROP)})")
        return len(us)

    def chain(self, devices, mount_h, label=""):
        """Daisy chain of wall / ceiling devices: tray -> device -> back to tray, last one ends there."""
        todo = list(devices)
        n = 0
        while todo:
            p = min(todo, key=lambda d: math.dist(d, self.cur))
            todo.remove(p)
            q, d = self.goto(p)
            last = not todo
            conn = manhattan(q, p)
            if last:
                self._draw(conn)
                self.ab_terms.append(plen(conn) / 1000)
            else:  # U: down to the device and back
                off = 150
                back = [(x + off if abs(conn[0][1] - conn[-1][1]) > abs(conn[0][0] - conn[-1][0]) else x,
                         y if abs(conn[0][1] - conn[-1][1]) > abs(conn[0][0] - conn[-1][0]) else y + off) for x, y in conn[::-1]]
                self._draw(conn + back)
                self.ab_terms.append(2 * plen(conn) / 1000)
            n += 1
        lvl = self.level(self.cur)
        drop = max(lvl - mount_h, 0)
        if n > 1:
            self.ad_terms.append(f"{n - 1}*2*({f2(lvl)}-{f2(mount_h)})+({f2(lvl)}-{f2(mount_h)})")
            self.ab_terms.append(f"{n - 1}*2*({f2(lvl)}-{f2(mount_h)})+({f2(lvl)}-{f2(mount_h)})")
        elif n == 1:
            self.ad_terms.append(f"({f2(lvl)}-{f2(mount_h)})")
            self.ab_terms.append(f"({f2(lvl)}-{f2(mount_h)})")
        return n

    def wall_chain(self, devices, mount_h, run_h=3.0):
        """Wall devices (exit / emergency lights): leave the tray once near the first device, then
        conduit along the walls at run_h from device to device (Manhattan)."""
        if not devices:
            return 0
        todo = list(devices)
        p = min(todo, key=lambda d: math.dist(d, self.cur))
        q, d = self.goto(p)
        lvl = self.level(q)
        pts = manhattan(q, p)
        todo.remove(p)
        while todo:
            nxt = min(todo, key=lambda d: math.dist(d, p))
            todo.remove(nxt)
            pts += manhattan(p, nxt)[1:]
            p = nxt
        self._draw(pts)
        n = len(devices)
        self.ab_terms.append(plen(pts) / 1000)
        v = f"({f2(lvl)}-{f2(run_h)})+{n}*2*({f2(run_h)}-{f2(mount_h)})"
        self.ab_terms.append(v)
        self.ad_terms.append(v)
        return n

    def lamp_chain(self, lamps):
        """Single lamps hung under trunking (e.g. night-light circuits): go to each lamp, drop 0.35 each way."""
        n = 0
        for p in sorted(lamps, key=lambda d: math.dist(d, self.cur)):
            q, d = self.goto(p)
            conn = manhattan(q, p)
            self._draw(conn)
            self.ab_terms.append(2 * plen(conn) / 1000)
            n += 1
        if n:
            self.ad_terms.append(f"{n}*({f2(LAMP_DROP)}+{f2(LAMP_DROP)})")
        return n

    def result(self):
        ab = "=" + "+".join(t if isinstance(t, str) else f2(t) for t in self.ab_terms if t not in (0, "0"))
        ad = "=" + "+".join(self.ad_terms)
        return {"AC": round(self.hor / 1000, 1), "AB": ab, "AD": ad, "paths": self.paths, "note": "; ".join(self.note)}


def evalf(f):
    return eval(f.lstrip("="))
