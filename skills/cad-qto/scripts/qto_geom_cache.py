"""Cache the drawable geometry of kept DXFs as compact JSON, for shape detectors and pictures.

    python qto_geom_cache.py --workdir C:/qto/<project> [--dxf <folder>] [--only <regex>]

Reads every DXF in <workdir>/dxf (written by qto_convert.py --keep-dxf, or the folder given)
and writes <workdir>/geom/<name>.json: a list of
    ["L", layer, src, x1, y1, x2, y2]            LINE
    ["C", layer, src, cx, cy, r]                 CIRCLE
    ["A", layer, src, cx, cy, r, a0, a1]         ARC (degrees)
    ["P", layer, src, [[x, y], ...], closed]     LWPOLYLINE / POLYLINE
    ["H", layer, src, x0, y0, x1, y1]            HATCH (bounding box only)
    ["T", layer, src, x, y, text]                TEXT / MTEXT (decoded)
src = "M" for model space, else "I:" + the top-level insert name (first 40 chars).

Inserts are exploded recursively (depth 4) - INCLUDING Revit link blocks (*_rvt): on Revit
exports the device strokes of a whole discipline can live inside the architecture link block
(Project A: every FA / exit / PA symbol was inside ...-A-0001_rvt on layer A-ANNO-NOTE).
Title blocks are skipped. Finished sheets are skipped; delete a JSON to redo it.
Coordinates: ezdxf Vec3 cannot be sliced ([:2] raises) - index [0], [1].
"""
import ezdxf, json, glob, os, re, sys, argparse
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from qto_common import decode_text

ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
ap.add_argument("--workdir", required=True)
ap.add_argument("--dxf", help="folder of DXF (default <workdir>/dxf)")
ap.add_argument("--only", help="regex on the DXF file name")
a = ap.parse_args()
W = a.workdir
os.makedirs(W + "/geom", exist_ok=True)
for f in sorted(glob.glob((a.dxf or W + "/dxf") + "/*.dxf")):
    if a.only and not re.search(a.only, os.path.basename(f)): continue
    out = W + "/geom/" + os.path.basename(f)[:-4] + ".json"
    if os.path.exists(out): continue
    d = ezdxf.readfile(f); m = d.modelspace(); ents = []
    def add(e, src):
        t = e.dxftype(); L = e.dxf.layer
        try:
            if t == "LINE": ents.append(["L", L, src, e.dxf.start[0], e.dxf.start[1], e.dxf.end[0], e.dxf.end[1]])
            elif t == "CIRCLE": ents.append(["C", L, src, e.dxf.center[0], e.dxf.center[1], e.dxf.radius])
            elif t == "ARC": ents.append(["A", L, src, e.dxf.center[0], e.dxf.center[1], e.dxf.radius, e.dxf.start_angle, e.dxf.end_angle])
            elif t in ("LWPOLYLINE", "POLYLINE"):
                pts = ([[p[0], p[1]] for p in e.get_points("xy")] if t == "LWPOLYLINE" else [[v.dxf.location[0], v.dxf.location[1]] for v in e.vertices])
                ents.append(["P", L, src, pts, bool(e.closed if t == "LWPOLYLINE" else e.is_closed)])
            elif t == "HATCH":
                bb = ezdxf.bbox.extents([e]); 
                if bb.has_data: ents.append(["H", L, src, bb.extmin[0], bb.extmin[1], bb.extmax[0], bb.extmax[1]])
            elif t in ("TEXT", "MTEXT"):
                s = e.plain_text() if t == "MTEXT" else e.dxf.text
                p = e.dxf.insert
                ents.append(["T", L, src, p[0], p[1], decode_text(s)])
        except Exception: pass
    def walk(ents_iter, src, depth):
        for e in ents_iter:
            if e.dxftype() == "INSERT":
                n = e.dxf.name
                if "Title Block" in n or depth > 4: continue
                try: walk(e.virtual_entities(), src if src != "M" else "I:" + n[:40], depth + 1)
                except Exception: pass
            else: add(e, src)
    walk(m, "M", 0)
    json.dump(ents, open(out, "w", encoding="utf-8"))
    print(os.path.basename(f), len(ents), flush=True)
