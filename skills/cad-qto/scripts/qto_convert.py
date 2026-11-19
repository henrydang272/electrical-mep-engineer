"""Convert every .dwg under a folder to a compact JSON per drawing.

    python qto_convert.py --src <drawings folder> --workdir <work folder>
                          [--backend auto|oda|com:<ProgID>] [--keep-dxf] [--only <regex>]

ezdxf cannot read .dwg, so each drawing is first turned into DXF by a converter,
parsed, and reduced to what the take-off needs (block references with rotation /
scale / attributes, texts, extents of every placed block definition). The DXF is
deleted afterwards unless --keep-dxf (it is 20-50 MB per sheet).

Backends, tried in this order by --backend auto:
  oda   ODA File Converter - no CAD licence, headless, the preferred default
  com   a CAD program driven over COM: BricsCAD, AutoCAD, progeCAD, ZWCAD, GstarCAD

A COM ProgID does not reliably say which program answers it: on a machine with
BricsCAD installed, "AutoCAD.Application" resolves to bricscad.exe. The real
executable is therefore read from the registry (ProgID -> CLSID -> LocalServer32)
and written into every JSON, because a tender quantity has to be reproducible.

Crash-resilient: finished drawings are skipped, so the script can simply be re-run.
A drawing that fails 3 times gets a failure stub and is skipped afterwards.
"""
import argparse
import gc
import glob
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import traceback

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from qto_common import decode_text  # noqa: E402

import ezdxf  # noqa: E402

SCHEMA = 4
MAX_ATTEMPTS = 3
RESTART_EVERY = 40            # CAD programs leak memory; recycle the process
MAX_ENTS_PER_BLOCK = 400      # enough to locate a symbol, keeps huge libraries fast

COM_PROGIDS = [
    "BricscadApp.AcadApplication",
    "AutoCAD.Application",
    "Icad.Application",           # progeCAD
    "ZWCAD.Application",
    "GstarCAD.Application",
]
ODA_GLOBS = [
    r"C:\Program Files\ODA\ODAFileConverter*\ODAFileConverter.exe",
    r"C:\Program Files (x86)\ODA\ODAFileConverter*\ODAFileConverter.exe",
    r"C:\Program Files\ODA\*\ODAFileConverter.exe",
]


def log(msg, fh=None):
    line = f"[{time.strftime('%H:%M:%S')}] {msg}"
    print(line, flush=True)
    if fh:
        fh.write(line + "\n")
        fh.flush()


# =========================================================== backends
def resolve_progid(progid):
    """-> (clsid, exe path) for a COM ProgID, or None. Reads HKCR, which merges the
    machine-wide and per-user registrations (progeCAD registers per-user only)."""
    try:
        import winreg
    except ImportError:
        return None
    root = winreg.HKEY_CLASSES_ROOT
    clsid = None
    for key in (progid + r"\CLSID",):
        try:
            clsid = winreg.QueryValue(root, key)
        except OSError:
            clsid = None
    if not clsid:
        try:
            cur = winreg.QueryValue(root, progid + r"\CurVer")
            clsid = winreg.QueryValue(root, cur + r"\CLSID")
        except OSError:
            return None
    for sub in ("LocalServer32", "InprocServer32"):
        for base in (rf"CLSID\{clsid}\{sub}", rf"WOW6432Node\CLSID\{clsid}\{sub}"):
            try:
                v = winreg.QueryValue(root, base)
            except OSError:
                continue
            m = re.match(r'^\s*"([^"]+)"', v) or re.match(r"^\s*(.+?\.exe)", v, re.I)
            return clsid, (m.group(1) if m else v.strip())
    return None


def find_oda(explicit=None):
    if explicit and os.path.exists(explicit):
        return explicit
    for g in ODA_GLOBS:
        hits = sorted(glob.glob(g))
        if hits:
            return hits[-1]
    return None


class OdaBackend:
    """ODA File Converter, one file at a time through its folder-based CLI:
    ODAFileConverter <in dir> <out dir> <version> <DXF|DWG> <recurse> <audit> [filter]."""
    name = "ODA File Converter"

    def __init__(self, exe):
        self.exe = exe
        self.label = f"{self.name} ({exe})"

    def start(self):
        pass

    def convert(self, src, dst):
        tin = tempfile.mkdtemp(prefix="qto_in_")
        tout = tempfile.mkdtemp(prefix="qto_out_")
        try:
            shutil.copy2(src, os.path.join(tin, "x.dwg"))
            subprocess.run([self.exe, tin, tout, "ACAD2018", "DXF", "0", "1", "x.dwg"],
                           capture_output=True, timeout=900)
            out = os.path.join(tout, "x.dxf")
            if not os.path.exists(out):
                raise RuntimeError("ODA File Converter produced no DXF")
            shutil.move(out, dst)
        finally:
            shutil.rmtree(tin, ignore_errors=True)
            shutil.rmtree(tout, ignore_errors=True)
        return {"com_model_count": None}

    def recycle(self):
        pass

    def stop(self):
        pass


class ComBackend:
    """A CAD program driven over COM (AutoCAD ActiveX API and its clones).

    Four things learned the hard way:
      * doc.Close(False) - False means DO NOT SAVE. progeCAD saves on close by
        default, so forgetting it writes into the client's drawing.
      * never app.Quit(): the COM proxy dying under us kills the Python process;
        taskkill the executable instead.
      * some programs cannot be cold-started by CoCreateInstance from a detached
        process ("Server execution failed"), so launch the exe with /Automation first.
      * recycle every ~40 drawings - memory leaks until the program hangs.
    """

    def __init__(self, progid, exe, attach=False):
        self.progid = progid
        self.exe = exe
        self.image = os.path.basename(exe)
        self.label = f"{progid} -> {exe}"
        self.app = None
        # attach = use a copy of the program the user already has open. Then it is
        # never killed or recycled, because that would throw away their unsaved work.
        self.attach = attach

    def _running(self):
        try:
            r = subprocess.run(["tasklist", "/FI", f"IMAGENAME eq {self.image}"],
                               capture_output=True, text=True, timeout=30)
            return self.image.lower() in (r.stdout or "").lower()
        except Exception:
            return False

    def stop(self):
        if self.attach:
            self.app = None
            return
        try:
            subprocess.run(["taskkill", "/F", "/IM", self.image],
                           capture_output=True, timeout=30)
        except Exception:
            pass
        self.app = None
        time.sleep(2.5)

    def start(self):
        import win32com.client as w32
        if self._running() and not self.attach and self.app is None:
            raise SystemExit(
                f"{self.image} is already running. Converting needs to restart it, which "
                f"would lose unsaved work. Save and close it first, or pass --attach to "
                f"use the open copy (it will then not be recycled).")
        for attempt in range(5):
            if not self._running():
                try:
                    subprocess.Popen([self.exe, "/Automation"])
                except Exception:
                    pass
                for _ in range(40):
                    time.sleep(2)
                    if self._running():
                        time.sleep(6)
                        break
            try:
                app = w32.Dispatch(self.progid)
                try:
                    app.Visible = False
                except Exception:
                    pass
                _ = app.Documents.Count           # force a real round-trip
                self.app = app
                return
            except Exception as ex:
                print(f"   start retry {attempt}: {str(ex)[:100]}", flush=True)
                self.stop()
                time.sleep(3)
        raise RuntimeError(f"cannot start {self.exe} over COM")

    def convert(self, src, dst):
        doc = self.app.Documents.Open(src)
        n = None
        try:
            try:
                n = int(doc.ModelSpace.Count)
            except Exception:
                n = None
            doc.SaveAs(dst)
        finally:
            try:
                doc.Close(False)
            except Exception:
                pass
        return {"com_model_count": n}

    def recycle(self):
        if self.attach:
            return
        self.stop()
        self.start()


def pick_backend(spec, oda_path=None, attach=False):
    """-> backend instance. spec: auto | oda | com:<ProgID>"""
    if spec in ("auto", "oda"):
        exe = find_oda(oda_path)
        if exe:
            return OdaBackend(exe)
        if spec == "oda":
            raise SystemExit("ODA File Converter not found. Install it from the Open "
                             "Design Alliance site or pass --oda <path to exe>.")
    if spec.startswith("com:"):
        progid = spec[4:]
        r = resolve_progid(progid)
        if not r:
            raise SystemExit(f"COM ProgID {progid} is not registered on this machine.")
        return ComBackend(progid, r[1], attach)
    seen = set()
    for progid in COM_PROGIDS:
        r = resolve_progid(progid)
        if r and os.path.exists(r[1]) and r[1].lower() not in seen:
            seen.add(r[1].lower())
            return ComBackend(progid, r[1], attach)
    raise SystemExit("No DWG converter found: install ODA File Converter (free, no CAD "
                     "licence needed) or a CAD program with COM automation.")


def list_backends():
    rows = []
    exe = find_oda()
    rows.append(("oda", exe or "(not installed)"))
    for progid in COM_PROGIDS:
        r = resolve_progid(progid)
        rows.append((f"com:{progid}", r[1] if r else "(not registered)"))
    return rows


# ============================================================ DXF parse
def _pt(e, attr="insert"):
    try:
        v = getattr(e.dxf, attr)
        return [round(float(v[0]), 3), round(float(v[1]), 3)]
    except Exception:
        return None


def _pts_of(e):
    """Cheap representative points; ezdxf.bbox is exact but minutes per file here."""
    t = e.dxftype()
    d = e.dxf
    try:
        if t == "LINE":
            return [d.start, d.end]
        if t in ("CIRCLE", "ARC"):
            c, r = d.center, float(d.radius)
            return [(c[0] - r, c[1] - r), (c[0] + r, c[1] + r)]
        if t == "LWPOLYLINE":
            return list(e.get_points("xy"))[:80]
        if t == "POLYLINE":
            return [v.dxf.location for v in list(e.vertices)[:80]]
        if t in ("INSERT", "TEXT", "ATTRIB", "MTEXT"):
            return [d.insert]
        if t == "ELLIPSE":
            c, ma = d.center, d.major_axis
            r = max(abs(ma[0]), abs(ma[1]))
            return [(c[0] - r, c[1] - r), (c[0] + r, c[1] + r)]
        if t in ("SOLID", "TRACE", "3DFACE"):
            return [d.vtx0, d.vtx1, d.vtx2, d.vtx3]
        if t == "POINT":
            return [d.location]
        if t == "SPLINE":
            return list(e.control_points)[:40]
    except Exception:
        return []
    return []


def _block_extents(doc, name, cache):
    """Extents of a block DEFINITION. Revit bakes symbol geometry at real plan
    coordinates inside the definition and inserts it at (0,0), so without these the
    insert point cannot locate the device."""
    if name in cache:
        return cache[name]
    res = None
    try:
        blk = doc.blocks.get(name)
        if blk is not None:
            xs, ys = [], []
            for n, e in enumerate(blk):
                if n >= MAX_ENTS_PER_BLOCK:
                    break
                if e.dxftype() == "ATTDEF":
                    continue
                for p in _pts_of(e):
                    try:
                        xs.append(float(p[0]))
                        ys.append(float(p[1]))
                    except Exception:
                        pass
            if xs and ys:
                res = [round(min(xs), 2), round(min(ys), 2),
                       round(max(xs), 2), round(max(ys), 2)]
    except Exception:
        res = None
    cache[name] = res
    return res


def parse_dxf(path, rel):
    doc = ezdxf.readfile(path)
    rec = {
        "dwg": rel,
        "folder": rel.split("\\")[0] if "\\" in rel else ".",
        "file": os.path.splitext(os.path.basename(rel))[0],
        "dxfversion": doc.dxfversion,
        "layers": sorted(l.dxf.name for l in doc.layers),
        "layouts": {},
        "n_blockdefs": len(doc.blocks),
        "xrefs": [],
        "inserts": [],
        "texts": [],
        "blockdef_ext": {},
        "schema": SCHEMA,
    }
    for blk in doc.blocks:
        try:
            bl = blk.block
            if bl is not None and bl.dxf.hasattr("xref_path") and bl.dxf.xref_path:
                rec["xrefs"].append({"name": blk.name, "path": bl.dxf.xref_path})
        except Exception:
            pass

    def harvest(space, tag):
        n = 0
        for e in space:
            n += 1
            t = e.dxftype()
            if t == "INSERT":
                d = {"n": e.dxf.name, "l": e.dxf.layer, "p": _pt(e), "sp": tag}
                try:
                    r = float(e.dxf.rotation)
                    if abs(r) > 1e-9:
                        d["r"] = round(r, 2)
                except Exception:
                    pass
                try:
                    sx, sy = float(e.dxf.xscale), float(e.dxf.yscale)
                    if abs(sx - 1) > 1e-9 or abs(sy - 1) > 1e-9:
                        d["s"] = [round(sx, 4), round(sy, 4)]
                except Exception:
                    pass
                try:
                    if e.attribs:
                        d["a"] = {a.dxf.tag: a.dxf.text for a in e.attribs}
                except Exception:
                    pass
                rec["inserts"].append(d)
            elif t in ("TEXT", "MTEXT"):
                try:
                    txt = e.plain_text() if hasattr(e, "plain_text") else e.dxf.text
                except Exception:
                    txt = getattr(e.dxf, "text", "")
                txt = decode_text(txt).strip()
                if txt:
                    rec["texts"].append({"t": txt[:240], "l": e.dxf.layer,
                                         "p": _pt(e, "insert") or _pt(e, "align_point"),
                                         "sp": tag, "k": t})
        return n

    rec["layouts"]["Model"] = harvest(doc.modelspace(), "M")
    rec["dxf_model_count"] = rec["layouts"]["Model"]
    for name in doc.layouts.names():
        if name.lower() != "model":
            rec["layouts"][name] = harvest(doc.layouts.get(name), "P:" + name)
    cache = {}
    for nm in {i["n"] for i in rec["inserts"] if i["sp"] == "M"}:
        ext = _block_extents(doc, nm, cache)
        if ext:
            rec["blockdef_ext"][nm] = ext
    return rec


# ================================================================== main
def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--src", help="folder holding the .dwg files (searched recursively)")
    ap.add_argument("--workdir", help="work folder; JSON goes to <workdir>/extract")
    ap.add_argument("--backend", default="auto", help="auto | oda | com:<ProgID>")
    ap.add_argument("--oda", help="path to ODAFileConverter.exe if not in a standard place")
    ap.add_argument("--keep-dxf", action="store_true", help="keep DXF in <workdir>/dxf")
    ap.add_argument("--only", help="regex on the relative path; convert only matches")
    ap.add_argument("--attach", action="store_true",
                    help="COM only: use the CAD program already open, never restart it")
    ap.add_argument("--list-backends", action="store_true")
    args = ap.parse_args()

    if args.list_backends:
        for k, v in list_backends():
            print(f"  {k:<36} {v}")
        return 0
    if not args.src or not args.workdir:
        ap.error("--src and --workdir are required")

    out_dir = os.path.join(args.workdir, "extract")
    dxf_dir = os.path.join(args.workdir, "dxf")
    os.makedirs(out_dir, exist_ok=True)
    os.makedirs(dxf_dir, exist_ok=True)
    att_path = os.path.join(args.workdir, "convert_attempts.json")
    attempts = json.load(open(att_path, encoding="utf-8")) if os.path.exists(att_path) else {}
    logf = open(os.path.join(args.workdir, "convert_log.txt"), "a", encoding="utf-8")

    dwgs = []
    for root, _d, files in os.walk(args.src):
        for f in files:
            if f.lower().endswith(".dwg"):
                full = os.path.join(root, f)
                rel = os.path.relpath(full, args.src)
                if args.only and not re.search(args.only, rel):
                    continue
                dwgs.append((rel, full))
    dwgs.sort()

    def out_path(rel):
        return os.path.join(out_dir, rel.replace("\\", "__").replace("/", "__")[:-4] + ".json")

    todo = []
    for rel, full in dwgs:
        op = out_path(rel)
        if os.path.exists(op):
            try:
                head = json.load(open(op, encoding="utf-8"))
                if head.get("schema") == SCHEMA or "EXTRACT_FAILED" in head:
                    continue
            except Exception:
                pass
        if attempts.get(rel, 0) >= MAX_ATTEMPTS:
            continue
        todo.append((rel, full))

    log(f"=== {len(dwgs)} drawings, {len(todo)} to convert ===", logf)
    if not todo:
        return 0

    be = pick_backend(args.backend, args.oda, args.attach)
    log(f"backend: {be.label}", logf)
    be.start()
    done = fail = 0
    warn_count = []
    t_all = time.time()
    for i, (rel, full) in enumerate(todo, 1):
        attempts[rel] = attempts.get(rel, 0) + 1
        json.dump(attempts, open(att_path, "w", encoding="utf-8"))
        if done and done % RESTART_EVERY == 0:
            log("  ... recycling converter", logf)
            be.recycle()
        dxf = os.path.join(dxf_dir, os.path.basename(out_path(rel))[:-5] + ".dxf")
        t0 = time.time()
        try:
            info = be.convert(full, dxf)
            t1 = time.time()
            rec = parse_dxf(dxf, rel)
            rec["converter"] = be.label
            rec["src_dwg_mb"] = round(os.path.getsize(full) / 1e6, 2)
            rec["dxf_mb"] = round(os.path.getsize(dxf) / 1e6, 2)
            rec["com_model_count"] = info.get("com_model_count")
            if rec["com_model_count"] is not None and rec["com_model_count"] != rec["dxf_model_count"]:
                warn_count.append((rel, rec["com_model_count"], rec["dxf_model_count"]))
            with open(out_path(rel), "w", encoding="utf-8") as fh:
                json.dump(rec, fh, ensure_ascii=False)
            done += 1
            log(f"[{i}/{len(todo)}] OK {rel}  conv={t1 - t0:.1f}s parse={time.time() - t1:.1f}s "
                f"ins={len(rec['inserts'])} txt={len(rec['texts'])}", logf)
        except Exception as ex:
            fail += 1
            log(f"[{i}/{len(todo)}] FAIL (attempt {attempts[rel]}) {rel}: "
                f"{type(ex).__name__}: {str(ex)[:160]}", logf)
            logf.write(traceback.format_exc() + "\n")
            if attempts[rel] >= MAX_ATTEMPTS:
                json.dump({"dwg": rel, "file": os.path.splitext(os.path.basename(rel))[0],
                           "folder": rel.split("\\")[0], "EXTRACT_FAILED": str(ex)[:300],
                           "inserts": [], "texts": [], "schema": SCHEMA},
                          open(out_path(rel), "w", encoding="utf-8"), ensure_ascii=False)
            be.recycle()
        finally:
            if not args.keep_dxf and os.path.exists(dxf):
                try:
                    os.remove(dxf)
                except Exception:
                    pass
            gc.collect()
    be.stop()
    log(f"=== done ok={done} fail={fail} in {time.time() - t_all:.0f}s ===", logf)
    for rel, a, b in warn_count:
        log(f"  WARNING entity count differs {rel}: CAD model space {a} vs DXF {b} "
            f"- objects may have been lost in conversion (proxy / AEC objects)", logf)
    return 0


if __name__ == "__main__":
    sys.exit(main())
