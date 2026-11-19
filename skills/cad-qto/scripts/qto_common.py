"""Shared helpers for the cad-qto scripts.

Everything here is project-independent. Project knowledge (how drawing numbers are
coded, which block family is which device, what the legend calls it) lives in the
project's qto_config.json, never in code.
"""
import bisect
import glob
import json
import math
import os
import re
import sys
from collections import defaultdict

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")


# ------------------------------------------------------------------ config / io
def load_config(path):
    with open(path, encoding="utf-8") as fh:
        cfg = json.load(fh)
    cfg.setdefault("zones", {})
    cfg.setdefault("levels", {})
    cfg.setdefault("systems_by_folder", {})
    cfg.setdefault("systems_by_series", {})
    cfg.setdefault("systems_by_file", [])
    cfg.setdefault("exclude_boxes", [])
    cfg.setdefault("sheet_roles", [])
    cfg.setdefault("legend", {})
    cfg.setdefault("code_order", [])
    cfg.setdefault("group_order", [])
    cfg.setdefault("exclude", {})
    cfg.setdefault("blocks", [])
    cfg.setdefault("tags", [])
    cfg.setdefault("group_notes", [])
    cfg.setdefault("suffix_markers", [])
    cfg.setdefault("extra_devices", [])
    cfg.setdefault("dedup", {})
    cfg["_dir"] = os.path.dirname(os.path.abspath(path))
    return cfg


def workdir_of(cfg, override=None):
    wd = override or cfg.get("workdir") or cfg["_dir"]
    os.makedirs(wd, exist_ok=True)
    return wd


def load_extracts(extract_dir):
    recs, failed = [], []
    for f in sorted(glob.glob(os.path.join(extract_dir, "*.json"))):
        try:
            with open(f, encoding="utf-8") as fh:
                r = json.load(fh)
        except Exception:
            continue
        (failed if "EXTRACT_FAILED" in r else recs).append(r)
    return recs, failed


RX_UESC = re.compile(r"\\U\+([0-9A-Fa-f]{4})")


def decode_text(s):
    r"""DXF TEXT keeps non-ASCII as \U+XXXX escapes ("R\U+00C1C" for "RÁC");
    MTEXT plain_text() already decodes them. Apply to every text read from a DXF."""
    return RX_UESC.sub(lambda m: chr(int(m.group(1), 16)), s or "")


# ------------------------------------------------------------- block naming
RX_ID = re.compile(r"^V?\d+$")
RX_CONDUIT_BUFFER = re.compile(r"^(Conduit Buffer)\s*\d+$", re.I)


def parse_block(name):
    """Split a block name into family / type / id / level / view.

    Revit writes "<Family> - <Type>-<ElementId|Vnn>-<Level>-<View>". Several shorter
    shapes occur too, so anchor on the LAST segment that is a pure numeric / Vnn id.
    Library (non-Revit) blocks come back with the whole name as the family.
    """
    out = {"raw": name, "fam": name, "typ": "", "id": "", "lvl": "", "view": "",
           "kind": "plain"}
    if not name:
        return out
    if name.startswith("*"):
        out["kind"] = "anonymous"
        return out
    segs = name.split("-")
    idx = -1
    for i in range(len(segs) - 1, -1, -1):
        if RX_ID.match(segs[i].strip()):
            idx = i
            break
    if idx <= 0:
        if " - " in name:
            f, t = name.rsplit(" - ", 1)
            out["fam"], out["typ"] = f.strip(), t.strip()
        return out
    head = "-".join(segs[:idx]).strip()
    tail = [s.strip() for s in segs[idx + 1:]]
    out["kind"] = "revit"
    out["id"] = segs[idx].strip()
    if len(tail) >= 2:
        out["lvl"] = tail[0]
        out["view"] = "-".join(tail[1:])
    elif len(tail) == 1:
        out["view"] = tail[0]
    if " - " in head:
        f, t = head.rsplit(" - ", 1)
        out["fam"], out["typ"] = f.strip(), t.strip()
    else:
        out["fam"], out["typ"] = head, ""
    # Revit emits one family per conduit run ("Conduit Buffer1…680"); fold only that
    # known artefact - stripping digits in general destroys specs like "L1200".
    m = RX_CONDUIT_BUFFER.match(out["fam"])
    if m:
        out["fam"] = "Conduit Buffer"
    return out


def is_link_block(name):
    n = (name or "").lower()
    return "_rvt" in n or "_dwg" in n or n.endswith("_dwg") or "-link" in n


# ----------------------------------------------------------------- geometry
def effective_pos(ins, ext):
    """True plan position of a block reference.

    Revit bakes the symbol geometry at its real plan coordinates inside the block
    DEFINITION and inserts it near the origin, so the insert point alone is useless.
    Position = insert point + centre of the definition's extents, SCALED AND ROTATED
    by the insert. Leaving the rotation out once moved 3787 devices past the 50 mm
    de-duplication tolerance (72% of inserts were rotated) and double-counted them.
    """
    p = ins.get("p")
    if not p:
        return None
    e = ext.get(ins["n"])
    if not e:
        return (round(p[0], 1), round(p[1], 1))
    cx = (e[0] + e[2]) / 2.0
    cy = (e[1] + e[3]) / 2.0
    s = ins.get("s") or [1.0, 1.0]
    dx, dy = cx * s[0], cy * s[1]
    rot = ins.get("r") or 0.0
    if rot:
        t = math.radians(rot)
        co, si = math.cos(t), math.sin(t)
        dx, dy = dx * co - dy * si, dx * si + dy * co
    return (round(p[0] + dx, 1), round(p[1] + dy, 1))


# ------------------------------------------------------------------- levels
_RX_LEVEL_N = re.compile(r"LEVEL\s*0*(\d+)")
_RX_ORD = re.compile(r"\b0*(\d+)\s*(?:ST|ND|RD|TH)\b")
_RX_BARE = re.compile(r"^0*(\d+)$")


def norm_level(rev_lvl, dwg_lvl):
    """Normalise a Revit level tag ('LEVEL 01', 'Level 1', '1ST FLOOR', 'Lever 1')
    to a two-character key. Part of the de-duplication key, so it must be strict.
    Anything unrecognisable falls back to the level coded in the drawing number."""
    s = (rev_lvl or "").strip()
    if not s:
        return dwg_lvl
    up = s.upper().replace("LEVER", "LEVEL").replace("TẦNG", "").replace("_", " ").strip()
    if "GROUND" in up or up in ("GF", "G"):
        return "00"
    if "ROOF" in up or "MÁI" in up or re.search(r"\bMAI\b", up):
        return "RF"
    if "MEZZ" in up:
        return "MZ"
    if "BASEMENT" in up or up.startswith("B1"):
        return "B1"
    for rx in (_RX_LEVEL_N, _RX_ORD):
        m = rx.search(up)
        if m:
            return f"{int(m.group(1)):02d}"
    m = _RX_BARE.match(up)
    if m:
        return f"{int(m.group(1)):02d}"
    return dwg_lvl


# --------------------------------------------------------------------- grid
RX_GX = re.compile(r"^X[-_ ]?(\d+[A-Za-z]?)'?$", re.I)
RX_GY = re.compile(r"^Y[-_ ]?(\d+[A-Za-z]?)'?$", re.I)


def build_grid(rec):
    """Structural grid lines from grid-bubble text on any layer containing GRID."""
    xs, ys = defaultdict(list), defaultdict(list)
    for t in rec.get("texts", []):
        if t.get("sp") != "M" or not t.get("p"):
            continue
        if "GRID" not in (t.get("l") or "").upper():
            continue
        s = (t.get("t") or "").strip()
        if RX_GX.match(s):
            xs[s.upper()].append(t["p"][0])
        elif RX_GY.match(s):
            ys[s.upper()].append(t["p"][1])
    gx = sorted(((sum(v) / len(v), k) for k, v in xs.items()), key=lambda a: a[0])
    gy = sorted(((sum(v) / len(v), k) for k, v in ys.items()), key=lambda a: a[0])
    return {"x": gx, "y": gy}


def _bay(coord, lines):
    if not lines:
        return ""
    cs = [c for c, _ in lines]
    i = bisect.bisect_right(cs, coord)
    if i == 0:
        return f"<{lines[0][1]}"
    if i >= len(lines):
        return f">{lines[-1][1]}"
    return f"{lines[i - 1][1]}~{lines[i][1]}"


def zone_of(pos, grid):
    if not pos or not grid or (not grid["x"] and not grid["y"]):
        return ""
    bx, by = _bay(pos[0], grid["x"]), _bay(pos[1], grid["y"])
    return f"{bx} / {by}" if bx and by else (bx or by)


def grid_box(grid, frac=0.5, min_mm=20000.0):
    """Generous box around the structural grid, used only to tell whether a computed
    device position is plausible at all. Grid bubbles often cover only part of a plan
    (part sheets, two plans side by side, rooms beyond the last grid line), so the box
    is widened by half its size and at least 20 m, and needs 3+ lines each way."""
    if not grid or len(grid["x"]) < 3 or len(grid["y"]) < 3:
        return None
    x0, x1 = grid["x"][0][0], grid["x"][-1][0]
    y0, y1 = grid["y"][0][0], grid["y"][-1][0]
    mx = max((x1 - x0) * frac, min_mm)
    my = max((y1 - y0) * frac, min_mm)
    return (x0 - mx, y0 - my, x1 + mx, y1 + my)


# ---------------------------------------------------------------- sheet meta
def _match(rx, s):
    return bool(rx) and re.search(rx, s or "") is not None


def sheet_meta(rec, cfg):
    """zone / level / series / role / system for one drawing, from the config."""
    f = rec["file"]
    zone = lvl = series = ""
    rx = cfg.get("sheet_name_regex")
    if rx:
        m = re.match(rx, f)
        if m:
            gd = m.groupdict()
            zone = gd.get("zone") or ""
            lvl = gd.get("level") or gd.get("lvl") or ""
            series = gd.get("series") or ""
    folder = rec.get("folder", "")
    dwg = rec.get("dwg", "")
    sub = dwg.rsplit("\\", 1)[0] if "\\" in dwg else folder

    role = "layout"
    for rule in cfg.get("sheet_roles", []):
        ok = True
        if "file" in rule and not _match(rule["file"], f):
            ok = False
        if "series" in rule and not _match(rule["series"], series):
            ok = False
        if "zone" in rule and rule["zone"] != zone:
            ok = False
        if "level" in rule and rule["level"] != lvl:
            ok = False
        if "folder" in rule and not _match(rule["folder"], sub):
            ok = False
        if ok:
            role = rule["role"]
            break

    # system: per-file rule first, then folder, then the LONGEST series prefix in
    # systems_by_series ("2041" beats "20"). Projects whose whole plan set is series 20xx
    # (Project A: 2000 lighting, 2041 FA, 2061 PA...) need the 4-digit keys.
    system = None
    for rule in cfg.get("systems_by_file", []):
        if _match(rule["file"], f):
            system = rule["system"]
            break
    if not system:
        system = cfg["systems_by_folder"].get(sub)
    if not system and series:
        keys = [k for k in cfg["systems_by_series"] if series.startswith(k)]
        if keys:
            system = cfg["systems_by_series"][max(keys, key=len)]
    return {
        "zone": zone, "zone_name": cfg["zones"].get(zone, zone or "?"),
        "lvl": lvl, "lvl_name": cfg["levels"].get(lvl, lvl or "?"),
        "series": series, "role": role, "folder": sub,
        "system": system or sub or "?",
    }


# ------------------------------------------------------------- exclusion
DEFAULT_EXCLUDE = {
    "family_exact": [
        "Grid", "Section Head - Filled", "Level Head - Circle", "Level Head",
        "North Arrow", "Scale Bar", "Detail Item Dash Dot", "DETAIL ITEM DASH DOT",
        "Break Line", "Match Line", "Revision Cloud", "Spot Elevation",
    ],
    "family_contains": [
        "title block", "titleblock", "grid -", "grid head", "north arrow", "scale bar",
        "section head", "level head", "elevation mark", "revision", "match line",
        "break line", "callout", "view title", "detail item dash dot",
        "annotation_", "arrow head", "text note", "spot elevation", "keyplan",
        "key plan", "legend", "symbol",
    ],
    "layer_contains": ["S-GRID", "TTLB", "-NPLT", "DEFPOINTS", "G-ANNO", "REVC"],
    "family_keep": [],
}


def exclusion_reason(p, layer, cfg):
    """Why a block is structurally not a device (annotation, link, anonymous), or None.
    `family_keep` rescues real devices that a substring rule would catch - e.g. a
    'Symbol Sampling Smoke Detector' family is a real device despite the word symbol."""
    ex = cfg.get("_exclude_merged")
    if ex is None:
        ex = {k: list(DEFAULT_EXCLUDE[k]) + list(cfg.get("exclude", {}).get(k, []))
              for k in DEFAULT_EXCLUDE}
        cfg["_exclude_merged"] = ex
    fam = p["fam"]
    if p["kind"] == "anonymous":
        return "anonymous"
    if is_link_block(p["raw"]):
        return "link/xref"
    if fam in ex["family_keep"]:
        return None
    if fam in ex["family_exact"]:
        return "annotation"
    low = fam.lower()
    for s in ex["family_contains"]:
        if s.lower() in low:
            return "annotation"
    up = (layer or "").upper()
    for s in ex["layer_contains"]:
        if s.upper() in up:
            return "annotation-layer"
    return None


# --------------------------------------------------------------- naming
def device_names(cfg, code, rule=None, typ="", fam=""):
    """Vietnamese / English device name. The legend sheet is the naming authority, so
    the default is the legend wording plus the code; a rule may override it."""
    rule = rule or {}
    leg = cfg["legend"].get(code, {}) if code else {}
    vi = rule.get("vi") or (f"{leg['vi']} ({code})" if leg.get("vi") else (code or fam))
    en = rule.get("en") or leg.get("en", "")
    vi = vi.replace("{type}", typ or "").replace("{family}", fam or "")
    en = en.replace("{type}", typ or "").replace("{family}", fam or "")
    return vi, en


def sort_key(cfg, code, name):
    order = cfg.get("_code_index")
    if order is None:
        order = {c: i for i, c in enumerate(cfg.get("code_order", []))}
        cfg["_code_index"] = order
    if code and code in order:
        return (0, order[code], name)
    if code:
        return (1, 0, code + " " + name)
    return (2, 0, name)


def stamp():
    import time
    return "Lập ngày " + time.strftime("%d/%m/%Y")
