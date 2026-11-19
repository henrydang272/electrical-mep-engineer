"""Add pictures to the take-off workbook (run after qto_workbook.py).

    python qto_pictures.py --config qto_config.json

  Tổng hợp       inserts a row under the device descriptions with the drawn symbol of every
                 device type, cut from the plan around one counted device of that type.
  Theo khu vực   column C becomes a picture of the drawing area of that row: the plan in grey,
                 every counted device of the row drawn red inside a blue circle.

Needs <workdir>/geom/*.json (qto_geom_cache.py) for every drawing that holds counted devices;
rows without geometry get "(không có hình)". Pictures are drawn from the CAD geometry, never
from PDF. Takes ~8 min for 1 500 devices on 40 Revit sheets (first run builds .npz caches).

Symbol selection: a block device -> the strokes of that block only (source name = family);
a label / note / shape device -> flood-fill over touching strokes on electrical layers from the
nearest one (long straight runs are not followed). When the plan shows nothing readable (no
strokes, or only a dot - e.g. a camera block made of hatches), another counted device of the
same type is tried, then the same block family on a legend sheet (caption "theo bảng ký hiệu").

config "pictures" (all optional):
  "device_layers": regex of electrical layers drawn red      (default below)
  "legend_sheets": [drawing names] for the fallback          (default: sheets with role legend)
  "area_min_pad_mm": minimum margin around a row's devices   (default 15000 - keeps context)
openpyxl reads image sizes back from the files: check display size on img.anchor.ext, not
img.width. Re-running needs a fresh qto_workbook.py output (the symbol row is inserted).
"""
import csv, json, math, os, re, sys, hashlib, argparse
from collections import defaultdict, OrderedDict
import numpy as np
import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.collections import LineCollection
import openpyxl
from openpyxl.drawing.image import Image as XLImage
from openpyxl.utils import get_column_letter
from openpyxl.styles import Alignment, PatternFill, Border, Side, Font
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from qto_common import load_config, workdir_of

_ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
_ap.add_argument("--config", required=True)
_args = _ap.parse_args()
CFG = load_config(_args.config)
W = workdir_of(CFG).replace("\\", "/")
PIC = CFG.get("pictures", {})
XLSX = os.path.join(W, CFG["output_xlsx"])
OUT_SYM, OUT_AREA = W + "/render/sym", W + "/render/area"
os.makedirs(OUT_SYM, exist_ok=True); os.makedirs(OUT_AREA, exist_ok=True)
DEV_LAYER = re.compile(PIC.get("device_layers", r"^(A-ANNO-NOTE|E-|ME-|E\.|EE-|DB$|G-IMPT|ELV|manhole|Existing|New_)"), re.I)
MIN_PAD = float(PIC.get("area_min_pad_mm", 15000))

# ------------------------------------------------------------------ geometry
_G = {}
def geom(dwg):
    """-> dict(s=segments Nx4, d=electrical-layer flag, k=source id per segment, names=source names,
              t=[(x, y, text, src_id)])  for one drawing, cached as .npz"""
    if dwg in _G: return _G[dwg]
    js = [f for f in os.listdir(W + "/geom") if f.endswith("__" + dwg + ".json")]
    if not js: _G[dwg] = None; return None
    npz = W + "/geom/" + js[0][:-5] + ".npz"
    if os.path.exists(npz):
        z = np.load(npz, allow_pickle=True)
        g = dict(s=z["s"], d=z["d"], k=z["k"], names=list(z["names"]), t=list(z["t"]))
        _G[dwg] = g; return g
    segs, dev, kid, texts, names, idx = [], [], [], [], [], {}
    def sid(src):
        if src not in idx: idx[src] = len(names); names.append(src)
        return idx[src]
    for x in json.load(open(W + "/geom/" + js[0], encoding="utf-8")):
        k, lay, src = x[0], x[1], x[2]
        if src.startswith("I:LEGEND"): continue
        isdev = bool(DEV_LAYER.match(lay)); i = sid(src)
        def add(a, b, c, d_):
            segs.append([a, b, c, d_]); dev.append(isdev); kid.append(i)
        if k == "L": add(*x[3:7])
        elif k == "P":
            p = x[3] + ([x[3][0]] if x[4] else [])
            for a_, b_ in zip(p, p[1:]): add(a_[0], a_[1], b_[0], b_[1])
        elif k == "H":
            x0, y0, x1, y1 = x[3:7]
            for a_, b_, c_, d_ in ((x0, y0, x1, y0), (x1, y0, x1, y1), (x1, y1, x0, y1), (x0, y1, x0, y0)): add(a_, b_, c_, d_)
        elif k in "CA":
            cx, cy, r = x[3], x[4], x[5]
            s0, e0 = (0.0, 360.0) if k == "C" else (x[6], x[7] if x[7] > x[6] else x[7] + 360)
            n = max(4, int((e0 - s0) / 12)); t = np.radians(np.linspace(s0, e0, n + 1))
            px, py = cx + r * np.cos(t), cy + r * np.sin(t)
            for j in range(n): add(px[j], py[j], px[j+1], py[j+1])
        elif k == "T":
            s_ = (x[5] or "").strip()
            if s_ and len(s_) <= 16: texts.append((x[3], x[4], s_, i))
    g = dict(s=np.array(segs, float).reshape(-1, 4), d=np.array(dev, bool), k=np.array(kid, np.int32),
             names=names, t=texts)
    np.savez(npz, s=g["s"], d=g["d"], k=g["k"], names=np.array(names, dtype=object), t=np.array(texts, dtype=object))
    _G[dwg] = g; return g

def in_box(s, x0, y0, x1, y1):
    return (np.maximum(s[:, 0], s[:, 2]) >= x0) & (np.minimum(s[:, 0], s[:, 2]) <= x1) &            (np.maximum(s[:, 1], s[:, 3]) >= y0) & (np.minimum(s[:, 1], s[:, 3]) <= y1)

def draw(ax, g, x0, y0, x1, y1, sel=None, lw_bg=.35, lw_dev=.9, text_size=5, sel_texts=()):
    s = g["s"]; m = in_box(s, x0, y0, x1, y1)
    red = np.zeros(len(s), bool) if sel is None else sel
    ax.add_collection(LineCollection(s[m & ~red].reshape(-1, 2, 2), colors="#b4b4b4", linewidths=lw_bg))
    ax.add_collection(LineCollection(s[m & red].reshape(-1, 2, 2), colors="#d62020", linewidths=lw_dev))
    if text_size:
        for (x, y, t, i) in g["t"]:
            if x0 <= x <= x1 and y0 <= y <= y1:
                hot = (x, y) in sel_texts
                ax.text(x, y, t, color="#b00000" if hot else "#707070", fontsize=text_size if hot else text_size * .8, clip_on=True)

def frame(ax, x0, y0, x1, y1):
    ax.set_xlim(x0, x1); ax.set_ylim(y0, y1); ax.set_aspect("equal"); ax.axis("off")

def symbol_sel(g, r, cap=2600.0):
    """-> (mask of the segments forming this device's symbol, centre x, centre y, half-size).
    Block devices: the strokes of that block (source name = family) touching the insert point.
    Label / note / shape devices: flood-fill over touching electrical strokes from the nearest one.
    Long straight runs (cables, trays) are not followed."""
    s = g["s"]; x, y = r["x"], r["y"]
    box = in_box(s, x - cap, y - cap, x + cap, y + cap)
    if r.get("source") == "block" and r.get("fam"):
        pre = "I:" + r["fam"][:38]
        ids = [i for i, n in enumerate(g["names"]) if n.startswith(pre)]
        cand = box & np.isin(g["k"], ids)
        if not cand.any(): cand = box & g["d"]
    else:
        cand = box & g["d"]
    ln = np.hypot(s[:, 2] - s[:, 0], s[:, 3] - s[:, 1])
    cand &= ln < 0.8 * cap
    ix = np.flatnonzero(cand)
    sel = np.zeros(len(s), bool)
    if not len(ix): return sel, x, y, 700.0
    fg = s[ix]
    dist = np.minimum(np.hypot(fg[:, 0] - x, fg[:, 1] - y), np.hypot(fg[:, 2] - x, fg[:, 3] - y))
    near = np.hypot((fg[:, 0] + fg[:, 2]) / 2 - x, (fg[:, 1] + fg[:, 3]) / 2 - y)
    inset = (dist <= max(dist.min() * 1.5, 250)) | (near <= max(near.min() * 1.2, 150))
    for _ in range(14):
        pts = np.r_[fg[inset, :2], fg[inset, 2:]]
        lo, hi = pts.min(0), pts.max(0); gap = 0.08 * max(hi - lo) + 30
        lo, hi = lo - gap, hi + gap
        touch = ((fg[:, 0] >= lo[0]) & (fg[:, 0] <= hi[0]) & (fg[:, 1] >= lo[1]) & (fg[:, 1] <= hi[1])) |                 ((fg[:, 2] >= lo[0]) & (fg[:, 2] <= hi[0]) & (fg[:, 3] >= lo[1]) & (fg[:, 3] <= hi[1]))
        new = inset | touch
        if new.sum() == inset.sum(): break
        inset = new
    sel[ix[inset]] = True
    pts = np.r_[fg[inset, :2], fg[inset, 2:]]
    lo, hi = pts.min(0), pts.max(0)
    cx, cy = (lo + hi) / 2
    return sel, float(cx), float(cy), float(np.clip(max(hi - lo) / 2 * 1.3, 450, cap))

# ------------------------------------------------------------------ devices
rows = list(csv.DictReader(open(W + "/out/devices.csv", encoding="utf-8-sig")))
for r in rows:
    r["x"] = float(r["x"]) if r["x"] else None; r["y"] = float(r["y"]) if r["y"] else None

def safe(s): return hashlib.md5(s.encode("utf-8")).hexdigest()[:10]

def _legend_sheets():
    if PIC.get("legend_sheets"): return PIC["legend_sheets"]
    out = []
    for f in os.listdir(W + "/geom"):
        if f.endswith(".json"):
            name = f[:-5].split("__", 1)[-1]
            m = re.search(CFG.get("sheet_name_regex", "$^"), name)
            ser = m.group("series") if m and "series" in m.groupdict() else ""
            for rule in CFG.get("sheet_roles", []):
                if rule.get("role") == "legend" and "series" in rule and re.search(rule["series"], ser or ""):
                    out.append(name)
    return out
LEGEND_SHEETS = _legend_sheets()
def weak(g, sel):
    """True when the plan strokes do not show a readable symbol (nothing, or only a dot)"""
    if sel.sum() < 3: return True
    s = g["s"][sel]; pts = np.r_[s[:, :2], s[:, 2:]]
    return float(max(pts.max(0) - pts.min(0))) < 150

def legend_symbol(fam):
    """the same block family drawn on a legend sheet -> (g, sel, cx, cy, half, sheet) or None"""
    for sh in LEGEND_SHEETS:
        g = geom(sh)
        if g is None: continue
        ids = [i for i, n in enumerate(g["names"]) if n.startswith("I:" + fam[:38])]
        if not ids: continue
        m = np.flatnonzero(np.isin(g["k"], ids))
        if not len(m): continue
        s0 = g["s"][m[0]]
        r = {"x": (s0[0] + s0[2]) / 2, "y": (s0[1] + s0[3]) / 2, "source": "block", "fam": fam}
        sel, cx, cy, h = symbol_sel(g, r, cap=1200.0)
        if not weak(g, sel): return g, sel, cx, cy, h, sh
    return None

def symbol_png(device_vi):
    devs = [r for r in rows if r["device_vi"] == device_vi and r["x"] is not None and geom(r["dwg"]) is not None]
    if not devs: return None, ""
    # prefer a device from a block or label (its symbol is complete), then the most typical sheet
    by_sheet = defaultdict(list)
    for r in devs: by_sheet[r["dwg"]].append(r)
    pick = None
    for sheet in sorted(by_sheet, key=lambda k: -len(by_sheet[k])):       # most typical sheet first
        cand = sorted(by_sheet[sheet], key=lambda r: (r["x"], r["y"]))
        for r in [cand[len(cand) // 2]] + cand[:3]:
            g = geom(sheet); sel, cx, cy, h = symbol_sel(g, r)
            if pick is None: pick = (sheet, r, g, sel, cx, cy, h)
            if not weak(g, sel): pick = (sheet, r, g, sel, cx, cy, h); break
        else: continue
        break
    sheet, r, g, sel, cx, cy, h = pick
    lab = {(t[0], t[1]) for t in g["t"] if abs(t[0] - r["x"]) < 1 and abs(t[1] - r["y"]) < 1}
    note = ""
    if weak(g, sel) and r.get("source") == "block":
        alt = legend_symbol(r["fam"])
        if alt: g, sel, cx, cy, h, sheet = alt; lab = set(); note = "theo bảng ký hiệu " + sheet[-4:]
    out = f"{OUT_SYM}/{safe(device_vi)}.png"
    fig = plt.figure(figsize=(1.6, 1.6), dpi=110); ax = fig.add_axes([0, 0, 1, 1])
    draw(ax, g, cx - h, cy - h, cx + h, cy + h, sel=sel, lw_bg=.5, lw_dev=1.2, text_size=6, sel_texts=lab)
    frame(ax, cx - h, cy - h, cx + h, cy + h)
    if note: ax.text(0.02, 0.02, note, transform=ax.transAxes, fontsize=5.5, color="#0050ff")
    fig.savefig(out, facecolor="white"); plt.close(fig)
    return out, f"{sheet} @ {r['x']:.0f},{r['y']:.0f}"

def area_png(key, devs):
    by_sheet = defaultdict(list)
    for r in devs:
        if r["x"] is not None and geom(r["dwg"]) is not None: by_sheet[r["dwg"]].append(r)
    if not by_sheet: return None, ""
    sheets = sorted(by_sheet, key=lambda k: -len(by_sheet[k]))
    n = len(sheets)
    fig, axes = plt.subplots(1, n, figsize=(5.6 * n if n > 1 else 5.6, 3.4), dpi=110, squeeze=False)
    for ax, sh in zip(axes[0], sheets):
        ds = by_sheet[sh]
        xs = np.array([r["x"] for r in ds]); ys = np.array([r["y"] for r in ds])
        w, h = xs.max() - xs.min(), ys.max() - ys.min()
        pad = max(0.12 * max(w, h), MIN_PAD)
        x0, x1, y0, y1 = xs.min() - pad, xs.max() + pad, ys.min() - pad, ys.max() + pad
        # keep the 5.6 x 3.4 aspect
        cw, ch = x1 - x0, y1 - y0; tgt = 5.6 / 3.2
        if cw / ch < tgt: e = (ch * tgt - cw) / 2; x0 -= e; x1 += e
        else: e = (cw / tgt - ch) / 2; y0 -= e; y1 += e
        g = geom(sh); sel = np.zeros(len(g["s"]), bool)
        for r in ds: sel |= symbol_sel(g, r)[0]
        draw(ax, g, x0, y0, x1, y1, sel=sel, lw_bg=.22, lw_dev=.6, text_size=0)
        rad = 0.018 * (x1 - x0)
        if len(ds) > 1:                                   # keep circles apart on dense rows
            P_ = np.c_[xs, ys]; dd = np.hypot(*(P_[:, None, :] - P_[None, :, :]).transpose(2, 0, 1))
            np.fill_diagonal(dd, np.inf); nn = np.median(dd.min(1))
            rad = max(min(rad, 0.42 * nn), 0.004 * (x1 - x0))
        for i, r in enumerate(ds, 1):
            q = int(r.get("qty") or 1)
            ax.add_patch(plt.Circle((r["x"], r["y"]), rad, fill=False, ec="#0050ff", lw=1.1))
        ax.set_title(f"{sh}  —  {len(ds)} vị trí khoanh xanh", fontsize=6.5)
        frame(ax, x0, y0, x1, y1)
    fig.tight_layout(pad=0.3)
    out = f"{OUT_AREA}/{safe('|'.join(key))}.png"
    fig.savefig(out, facecolor="white"); plt.close(fig)
    return out, ", ".join(sheets)

# ------------------------------------------------------------------ workbook
def px_to_pt(px): return px * 0.75
def width_to_px(w): return int(w * 7 + 5)

def main():
    wb = openpyxl.load_workbook(XLSX)
    thin = Side(style="thin", color="999999"); box = Border(left=thin, right=thin, top=thin, bottom=thin)

    # ---- Tổng hợp: insert a symbol row (row 6) under the description row 5
    ws = wb["Tổng hợp"]
    merges = [str(m) for m in ws.merged_cells.ranges]
    low = [m for m in merges if openpyxl.utils.cell.range_boundaries(m)[1] >= 4]
    for m in low: ws.unmerge_cells(m)
    ws.insert_rows(6)
    for m in low:
        c0, r0, c1, r1 = openpyxl.utils.cell.range_boundaries(m)
        if r1 == 5 and r0 == 4 and c0 > 2: r1 = 6   # the TỔNG header spans the symbol row too
        ws.merge_cells(start_row=r0, start_column=c0, end_row=r1, end_column=c1)
    SYM_PX = 96
    ws.row_dimensions[6].height = px_to_pt(SYM_PX + 8)
    fill = PatternFill("solid", fgColor="FFFFFF")
    n_ok = 0
    for c in range(3, ws.max_column + 1):
        d = ws.cell(5, c).value
        if not d or d == "TỔNG": continue
        ws.column_dimensions[get_column_letter(c)].width = 15
        cell = ws.cell(6, c); cell.fill = fill; cell.border = box
        png, src = symbol_png(d)
        if not png: cell.value = "(không có hình)"; cell.alignment = Alignment(wrap_text=True, horizontal="center", vertical="center"); cell.font = Font(size=7, italic=True); continue
        img = XLImage(png); img.width = img.height = SYM_PX
        img.anchor = f"{get_column_letter(c)}6"; ws.add_image(img); n_ok += 1
    ws.merge_cells("A6:B6")
    ws.cell(6, 1).value = "Ký hiệu trên bản vẽ (cắt từ mặt bằng CAD quanh 1 thiết bị đã đếm)"
    ws.cell(6, 1).alignment = Alignment(wrap_text=True, vertical="center"); ws.cell(6, 1).font = Font(size=8, italic=True)
    ws.freeze_panes = "C7"
    print("symbols:", n_ok)

    # ---- Theo khu vực: picture in column C
    wa = wb["Theo khu vực"]
    wa.cell(4, 3).value = "Khu vực trên bản vẽ (thiết bị đã đếm khoanh xanh)"
    groups = defaultdict(list)
    for r in rows:
        k = (r["zone_name"], r["lvl_name"], r["gridzone"] or "(không xác định)", r["system"], r["group"], r["device_vi"])
        groups[k].append(r)
    AREA_W_PX, AREA_H_PX = 420, 255
    wa.column_dimensions["C"].width = (AREA_W_PX - 5) / 7
    n_ok = 0
    for rr in range(5, wa.max_row + 1):
        k = tuple(str(wa.cell(rr, c).value or "") for c in range(1, 7))
        if not k[0]: continue
        devs = groups.get(k)
        if not devs: print("  no devices for row", rr, k[:2], k[5][:40]); continue
        png, src = area_png(k, devs)
        cell = wa.cell(rr, 3)
        if not png: cell.value = "(không có hình)"; continue
        cell.value = None
        img = XLImage(png)
        sc = min(AREA_W_PX / img.width, AREA_H_PX / img.height)
        img.width, img.height = int(img.width * sc), int(img.height * sc)
        img.anchor = f"C{rr}"; wa.add_image(img)
        wa.row_dimensions[rr].height = px_to_pt(img.height + 6)
        for c in (1, 2, 4, 5, 6, 7):
            wa.cell(rr, c).alignment = Alignment(wrap_text=True, vertical="center", horizontal="center" if c == 7 else "left")
        n_ok += 1
    print("area pictures:", n_ok, "of", wa.max_row - 4)
    wb.save(XLSX)
    print("->", XLSX)

if __name__ == "__main__":
    main()
