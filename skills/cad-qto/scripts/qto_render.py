"""Pictures for checking by eye - no CAD program needed to look at them.

  Zoom on a point of one drawing:
    python qto_render.py point --dwg <file.dwg|file.dxf> --at X,Y [--half 3000] --out a.png

  A few samples of every device code (or of one code) from the counted devices:
    python qto_render.py sample --config qto_config.json --src <drawings folder>
                                [--code ISW] [--n 3] [--half 2500]

  Mark every counted device on a drawing, as a DXF any CAD program can open:
    python qto_render.py highlight --config qto_config.json --src <drawings folder>
                                   --sheet <drawing name> [--out file.dxf]

The DXF needed for a picture is converted on demand and cached in <workdir>/dxf.
The highlight file is written as a NEW file - the client's drawing is never modified.
"""
import argparse
import csv
import os
import re
import sys
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from qto_common import load_config, workdir_of, decode_text  # noqa: E402

import ezdxf  # noqa: E402
import matplotlib  # noqa: E402
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.patches import Arc, Circle  # noqa: E402

_ENTS = {}


def ensure_dxf(path, workdir, backend="auto", attach=False):
    """A DXF for `path`: itself if already DXF, else a cached conversion."""
    if path.lower().endswith(".dxf"):
        return path
    import qto_convert
    cache = os.path.join(workdir, "dxf")
    os.makedirs(cache, exist_ok=True)
    dst = os.path.join(cache, os.path.splitext(os.path.basename(path))[0] + ".dxf")
    if not os.path.exists(dst):
        be = qto_convert.pick_backend(backend, attach=attach)
        be.start()
        try:
            be.convert(path, dst)
        finally:
            be.stop()
    return dst


def entities(dxf):
    if dxf in _ENTS:
        return _ENTS[dxf]
    doc = ezdxf.readfile(dxf)
    out = []

    def walk(container, depth=0):
        for e in container:
            t = e.dxftype()
            try:
                lay = e.dxf.layer
                if t == "LINE":
                    a, b = e.dxf.start, e.dxf.end
                    out.append(("L", (a[0], a[1]), (b[0], b[1]), lay))
                elif t == "CIRCLE":
                    c = e.dxf.center
                    out.append(("C", (c[0], c[1]), e.dxf.radius, lay))
                elif t == "ARC":
                    c = e.dxf.center
                    out.append(("A", (c[0], c[1]),
                                (e.dxf.radius, e.dxf.start_angle, e.dxf.end_angle), lay))
                elif t in ("LWPOLYLINE", "POLYLINE"):
                    pts = ([(p[0], p[1]) for p in e.get_points()] if t == "LWPOLYLINE"
                           else [(v.dxf.location[0], v.dxf.location[1]) for v in e.vertices])
                    for i in range(len(pts) - 1):
                        out.append(("L", pts[i], pts[i + 1], lay))
                    if getattr(e, "closed", False) and len(pts) > 2:
                        out.append(("L", pts[-1], pts[0], lay))
                elif t in ("TEXT", "MTEXT"):
                    s = e.plain_text() if hasattr(e, "plain_text") else e.dxf.text
                    p = e.dxf.insert
                    out.append(("T", (p[0], p[1]), decode_text(s), lay))
                elif t == "INSERT" and depth < 3:
                    walk(e.virtual_entities(), depth + 1)
            except Exception:
                pass
    walk(doc.modelspace())
    _ENTS[dxf] = out
    return out


def colour(layer):
    L = (layer or "").upper()
    if "GRID" in L:
        return "#34495e"
    if "TEXT" in L or "IDEN" in L or "NOTE" in L or "ANNO" in L:
        return "#ff6b6b"
    if "LITE" in L or "LT-" in L:
        return "#ffd24a"
    if "POWR" in L or "SOCK" in L or "SO-" in L:
        return "#4aa3ff"
    if "FIRE" in L or "FA" in L:
        return "#ff9f43"
    return "#9aa0a6"


def draw(dxf, cx, cy, half, out_png, title="", marks=()):
    ents = entities(dxf)
    x0, x1, y0, y1 = cx - half, cx + half, cy - half, cy + half
    fig, ax = plt.subplots(figsize=(10, 10), dpi=110)
    ax.set_facecolor("black")
    n = 0
    for kind, p, v, lay in ents:
        col = colour(lay)
        if kind == "L":
            if max(p[0], v[0]) < x0 or min(p[0], v[0]) > x1 or max(p[1], v[1]) < y0 or min(p[1], v[1]) > y1:
                continue
            ax.plot([p[0], v[0]], [p[1], v[1]], color=col, lw=1.0)
        elif kind == "C":
            if not (x0 - v <= p[0] <= x1 + v and y0 - v <= p[1] <= y1 + v):
                continue
            ax.add_patch(Circle(p, v, fill=False, color=col, lw=1.0))
        elif kind == "A":
            r, a1, a2 = v
            if not (x0 - r <= p[0] <= x1 + r and y0 - r <= p[1] <= y1 + r):
                continue
            ax.add_patch(Arc(p, 2 * r, 2 * r, theta1=a1, theta2=a2, color=col, lw=1.0))
        elif kind == "T":
            if not (x0 <= p[0] <= x1 and y0 <= p[1] <= y1) or not str(v).strip():
                continue
            ax.text(p[0], p[1], str(v)[:28], color="#ff6b6b", fontsize=9, clip_on=True)
        else:
            continue
        n += 1
    for mx, my, lab in marks:
        ax.add_patch(Circle((mx, my), half * 0.07, fill=False, color="#00e676", lw=2.2))
        if lab:
            ax.text(mx + half * 0.08, my + half * 0.08, lab, color="#00e676", fontsize=10)
    ax.set_xlim(x0, x1)
    ax.set_ylim(y0, y1)
    ax.set_aspect("equal")
    ax.axis("off")
    ax.set_title(f"{title}  @({cx:.0f},{cy:.0f})  ±{half:.0f}", color="white", fontsize=10)
    fig.savefig(out_png, bbox_inches="tight", facecolor="black")
    plt.close(fig)
    return n


def find_dwg(src, sheet):
    for root, _d, files in os.walk(src):
        for f in files:
            if os.path.splitext(f)[0] == sheet and f.lower().endswith(".dwg"):
                return os.path.join(root, f)
    return None


def read_devices(wd):
    with open(os.path.join(wd, "out", "devices.csv"), encoding="utf-8-sig") as fh:
        return list(csv.DictReader(fh))


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p1 = sub.add_parser("point")
    p1.add_argument("--dwg", required=True)
    p1.add_argument("--at", required=True, help="X,Y")
    p1.add_argument("--half", type=float, default=3000)
    p1.add_argument("--out", required=True)
    p1.add_argument("--workdir", default=".")
    for p in (sub.add_parser("sample"), sub.add_parser("highlight")):
        p.add_argument("--config", required=True)
        p.add_argument("--src", required=True, help="drawings folder")
        p.add_argument("--workdir")
        p.add_argument("--backend", default="auto")
        p.add_argument("--attach", action="store_true")
        if p.prog.endswith("sample"):
            p.add_argument("--code")
            p.add_argument("--n", type=int, default=3)
            p.add_argument("--half", type=float, default=2500)
        else:
            p.add_argument("--sheet", required=True)
            p.add_argument("--out")
    a = ap.parse_args()

    if a.cmd == "point":
        dxf = ensure_dxf(a.dwg, a.workdir)
        x, y = (float(v) for v in a.at.split(","))
        n = draw(dxf, x, y, a.half, a.out, os.path.basename(a.dwg))
        print(f"-> {a.out}  ({n} entities)")
        return 0

    cfg = load_config(a.config)
    wd = workdir_of(cfg, a.workdir)
    devs = read_devices(wd)

    if a.cmd == "sample":
        out_dir = os.path.join(wd, "render")
        os.makedirs(out_dir, exist_ok=True)
        by_code = defaultdict(list)
        for r in devs:
            if r["x"] and (not a.code or r["code"] == a.code):
                by_code[r["code"] or "(none)"].append(r)
        for code, items in sorted(by_code.items()):
            picked, sheets = [], set()
            for r in items:                     # prefer different drawings
                if r["dwg"] not in sheets:
                    picked.append(r)
                    sheets.add(r["dwg"])
                if len(picked) >= a.n:
                    break
            for k, r in enumerate(picked, start=1):
                dwg = find_dwg(a.src, r["dwg"])
                if not dwg:
                    print(f"   {code}: drawing {r['dwg']} not found under --src")
                    continue
                dxf = ensure_dxf(dwg, wd, a.backend, a.attach)
                x, y = float(r["x"]), float(r["y"])
                safe = re.sub(r"[^\w.-]+", "_", code)
                png = os.path.join(out_dir, f"{safe}_{k}.png")
                draw(dxf, x, y, a.half, png, f"{code} — {r['dwg']}", [(x, y, code)])
                print(f"   {code:<14} -> {png}")
        return 0

    # highlight
    dwg = find_dwg(a.src, a.sheet)
    if not dwg:
        raise SystemExit(f"{a.sheet}.dwg not found under {a.src}")
    dxf = ensure_dxf(dwg, wd, a.backend, a.attach)
    doc = ezdxf.readfile(dxf)
    if "QTO_HIGHLIGHT" not in doc.layers:
        doc.layers.add("QTO_HIGHLIGHT", color=3)
    msp = doc.modelspace()
    items = [r for r in devs if r["dwg"] == a.sheet and r["x"]]
    for r in items:
        x, y = float(r["x"]), float(r["y"])
        msp.add_circle((x, y), 600, dxfattribs={"layer": "QTO_HIGHLIGHT", "color": 3})
        msp.add_text(r["code"] or "?", height=250,
                     dxfattribs={"layer": "QTO_HIGHLIGHT", "color": 3}).set_placement((x + 650, y + 650))
    out = a.out or os.path.join(wd, "render", f"{a.sheet}_HIGHLIGHT.dxf")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    doc.saveas(out)
    print(f"-> {out}  ({len(items)} devices circled on layer QTO_HIGHLIGHT)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
