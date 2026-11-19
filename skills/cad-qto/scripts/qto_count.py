"""Count devices from the converted drawings, driven by the project's qto_config.json.

    python qto_count.py --config qto_config.json [--workdir <work folder>]

Reads <workdir>/extract/*.json (from qto_convert.py) and writes to <workdir>/out/:
  devices.csv        one row per counted device, with the source it came from
  qa.csv             per drawing: inserts read, counted, excluded, de-duplicated, ...
  catalogue.csv      every block family | type seen, the rule that claimed it, its count
  count_report.json  totals, de-duplication hits, note corrections, warnings

Order of work - it matters, each step assumes the previous one:
  1. blocks   classify every block reference on LAYOUT sheets by the config's rules
  2. tags     devices that are only a text tag (raw CIRCLE+LINE symbols, no block)
  3. dedup    four passes - same place / redrawn detail / key plan / overall-vs-part
  4. notes    group notes "11x ISW": the designer drew 2 and wrote the real number
  5. extra    device CSVs from project-specific detectors (exploded geometry etc.)
  6. suffix   variant markers such as "WP" written beside a device (S2 -> S2-wp)
  7. checks   positions that fall outside the structural grid are flagged
"""
import argparse
import csv
import glob
import json
import math
import os
import re
import sys
from collections import Counter, defaultdict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from qto_common import (load_config, workdir_of, load_extracts, parse_block,  # noqa: E402
                        effective_pos, norm_level, build_grid, zone_of, grid_box,
                        sheet_meta, exclusion_reason, device_names)

FIELDS = ["zone", "zone_name", "lvl", "lvl_name", "lvl_key", "system", "series", "dwg",
          "group", "code", "device_vi", "device_en", "fam", "typ", "block_key", "attrs",
          "x", "y", "gridzone", "layer", "source", "qty"]

RX_RANGE = re.compile(r"S[\d.]*?(\d+)\s*~\s*[\w.-]*?S[\d.]*?(\d+)\s*$")


def _re(rx, s, flags=0):
    return rx is None or re.search(rx, s or "", flags) is not None


def rule_applies(rule, m, fname):
    if rule.get("sheets") and not re.search(rule["sheets"], fname):
        return False
    if rule.get("zones") and m["zone"] not in rule["zones"]:
        return False
    roles = rule.get("roles", ["layout"])
    return m["role"] in roles


def match_block_rule(cfg, p, layer, m, fname):
    for i, r in enumerate(cfg["blocks"]):
        if not re.search(r.get("family", ".*"), p["fam"] or ""):
            continue
        if r.get("type") is not None and not re.search(r["type"], p["typ"] or "", re.I):
            continue
        if r.get("layer") and not re.search(r["layer"], layer or "", re.I):
            continue
        if r.get("sheets") and not re.search(r["sheets"], fname):
            continue
        if r.get("zones") and m["zone"] not in r["zones"]:
            continue
        return i, r
    return None, None


def base_record(m, fname, grid, pos, **kw):
    rec = {"zone": m["zone"], "zone_name": m["zone_name"], "lvl": m["lvl"],
           "lvl_name": m["lvl_name"], "lvl_key": m["lvl"], "system": m["system"],
           "series": m["series"], "dwg": fname, "attrs": "", "layer": "",
           "x": pos[0] if pos else None, "y": pos[1] if pos else None,
           "gridzone": zone_of(pos, grid) if pos else "", "qty": 1}
    rec.update(kw)
    return rec


# ================================================================ 1. blocks
def collect_blocks(recs, metas, grids, cfg, qa, catalogue):
    inst = []
    for rec in recs:
        f = rec["file"]
        m, grid = metas[f], grids[f]
        ext = rec.get("blockdef_ext", {})
        q = qa[f]
        tags_here = None
        for i in rec["inserts"]:
            if i.get("sp") != "M":
                continue
            q["model_inserts"] += 1
            p = parse_block(i["n"])
            key = (p["fam"], p["typ"])
            cat = catalogue.setdefault(key, {"rule": "", "code": "", "include": False,
                                             "reason": "", "seen": 0, "sheets": set(),
                                             "layers": Counter()})
            cat["seen"] += 1
            cat["layers"][i.get("l", "")] += 1
            why = exclusion_reason(p, i.get("l"), cfg)
            idx, rule = (None, None) if why else match_block_rule(cfg, p, i.get("l"), m, f)
            if rule is not None and rule.get("exclude"):
                why = rule["exclude"]
            if why:
                cat["reason"] = cat["reason"] or why
                cat["rule"] = cat["rule"] or (f"#{idx}" if idx is not None else "cấu trúc")
                bucket = {"link/xref": "excl_link", "anonymous": "excl_anon"}.get(why, "excl_annotation")
                q[bucket] += 1
                continue
            if m["role"] != "layout":
                continue
            if rule is None:
                q["unclassified"] += 1
                cat["reason"] = cat["reason"] or "CHƯA PHÂN LOẠI"
                continue
            sc = (i.get("s") or [1.0])[0]
            if rule.get("drop_scale_below") and abs(sc) < rule["drop_scale_below"]:
                q["excl_annotation"] += 1          # a legend symbol drawn in model space
                continue
            code = rule.get("code", "")
            pos = effective_pos(i, ext)
            if rule.get("code_from_tags") and pos:
                if tags_here is None:
                    tags_here = [((t.get("t") or "").strip().upper(), t["p"][0], t["p"][1])
                                 for t in rec["texts"] if t.get("sp") == "M" and t.get("p")]
                want = {c.upper() for c in rule["code_from_tags"]}
                cand = [t for t in tags_here if t[0] in want]
                if cand:
                    code = min(cand, key=lambda t: math.dist(pos, (t[1], t[2])))[0]
            vi, en = device_names(cfg, code, rule if code == rule.get("code") else None,
                                  p["typ"], p["fam"])
            cat.update(rule=f"#{idx}", code=cat["code"] or code, include=True)
            cat["sheets"].add(f)
            inst.append(base_record(
                m, f, grid, pos,
                lvl_key=norm_level(p["lvl"], m["lvl"]),
                group=rule.get("group", "Thiết bị điện khác"), code=code,
                device_vi=vi, device_en=en, fam=p["fam"], typ=p["typ"],
                block_key=p["fam"] + (" | " + p["typ"] if p["typ"] else ""),
                attrs=";".join(f"{k}={v}" for k, v in (i.get("a") or {}).items()),
                layer=i.get("l", ""), source="block"))
    return inst


# ================================================================== 2. tags
def collect_tags(recs, metas, grids, cfg, qa):
    out = []
    rules = cfg["tags"]
    if not rules:
        return out
    for rec in recs:
        f = rec["file"]
        m, grid = metas[f], grids[f]
        for t in rec["texts"]:
            if t.get("sp") != "M" or not t.get("p"):
                continue
            s = " ".join((t.get("t") or "").split())
            lay = t.get("l") or ""
            for r in rules:
                if not rule_applies(r, m, f):
                    continue
                if not re.search(r.get("layer", "IDEN"), lay, re.I):
                    continue
                if not re.search(r["text"], s, re.I):
                    continue
                pos = (round(t["p"][0], 1), round(t["p"][1], 1))
                vi, en = device_names(cfg, r["code"], r)
                out.append(base_record(m, f, grid, pos, group=r.get("group", "Thiết bị điện khác"),
                                       code=r["code"], device_vi=vi, device_en=en,
                                       fam="(nhãn CAD)", typ=r["code"],
                                       block_key="(nhãn CAD) | " + r["code"],
                                       attrs=s, layer=lay, source="tag"))
                qa[f]["text_devices"] += 1
                break
    return out


# ================================================================= 3. dedup
def snap(v, tol):
    return round(v / tol) * tol


def dedup(inst, cfg, qa, report):
    d = cfg["dedup"]
    tol = float(d.get("tol_mm", 50.0))

    # pass 1 - the same device drawn at the same place on several sheets
    seen, kept = set(), []
    for r in sorted(inst, key=lambda a: (a["series"], a["dwg"])):
        if r["x"] is None:
            kept.append(r)
            continue
        k = (r["zone"], r["lvl_key"], r["fam"], r["typ"], snap(r["x"], tol), snap(r["y"], tol))
        if k in seen:
            qa[r["dwg"]]["dup_removed"] += 1
            continue
        seen.add(k)
        kept.append(r)
    report["dedup_pass1"] = len(inst) - len(kept)

    # pass 2 - an enlarged detail redrawn at another model-space offset on each sheet:
    # identical relative pattern, different absolute coordinates
    mt, mf = float(d.get("offset_match_tol", 600.0)), float(d.get("offset_match_frac", 0.8))
    by_key = defaultdict(lambda: defaultdict(list))
    for r in kept:
        if r["x"] is not None:
            by_key[(r["zone"], r["lvl_key"], r["fam"], r["typ"])][r["dwg"]].append(r)

    def same_pattern(a, b):
        if len(a) < 3 or len(b) < 3:
            return False
        if abs(len(a) - len(b)) > max(1, 0.15 * max(len(a), len(b))):
            return False
        g = {(round(x / mt), round(y / mt)) for x, y in b}
        hit = sum(1 for x, y in a
                  if any((round(x / mt) + i, round(y / mt) + j) in g
                         for i in (-1, 0, 1) for j in (-1, 0, 1)))
        return hit >= mf * len(a)

    drop, hits2 = set(), []
    for key, bydwg in by_key.items():
        if len(bydwg) < 2:
            continue
        pts = {}
        for dwg, items in bydwg.items():
            cx = sum(i["x"] for i in items) / len(items)
            cy = sum(i["y"] for i in items) / len(items)
            pts[dwg] = [(i["x"] - cx, i["y"] - cy) for i in items]
        keepers = []
        for dwg in sorted(bydwg, key=lambda x: (-len(bydwg[x]), x)):
            if len(bydwg[dwg]) < 3:
                continue
            dup_of = next((k for k in keepers if same_pattern(pts[dwg], pts[k])), None)
            if dup_of:
                for i in bydwg[dwg]:
                    drop.add(id(i))
                    qa[dwg]["dup_removed"] += 1
                hits2.append(f"{key[2][:40]} | {key[3][:20]}: {dwg} lặp lại {dup_of} ({len(bydwg[dwg])})")
            else:
                keepers.append(dwg)
    k2 = [r for r in kept if id(r) not in drop]
    report["dedup_pass2"] = len(kept) - len(k2)
    report["dedup_pass2_hits"] = hits2[:200]
    kept = k2

    # key plans - a sheet whose devices sit in a tiny box AT THE ORIGIN repeats devices
    # detailed elsewhere. Both conditions are needed: "tight cluster" alone once
    # deleted three real guard-house devices that simply stood close together.
    box = float(d.get("keyplan_box_mm", 2000.0))
    origin = float(d.get("keyplan_origin_mm", 5000.0))
    bysheet = defaultdict(list)
    for r in kept:
        if r["x"] is not None:
            bysheet[r["dwg"]].append(r)
    dropk, keyhits = set(), []
    for dwg, items in bysheet.items():
        if len(items) < 2:
            continue
        xs = [r["x"] for r in items]
        ys = [r["y"] for r in items]
        if (max(xs) - min(xs) <= box and max(ys) - min(ys) <= box
                and max(abs(v) for v in xs + ys) <= origin):
            for r in items:
                dropk.add(id(r))
                qa[r["dwg"]]["dup_removed"] += 1
            keyhits.append(f"{dwg}: {len(items)}")
    kept = [r for r in kept if id(r) not in dropk]
    report["keyplan_dropped"] = keyhits

    # pass 3 - overall sheet and its part sheets drawn at DIFFERENT scales: same count,
    # same family/type mix, but almost no device of one near any device of the other
    ct, ov = float(d.get("sheet_count_tol", 0.10)), float(d.get("sheet_overlap_max", 0.20))
    grp = defaultdict(list)
    for r in kept:
        if r["x"] is not None:
            grp[(r["zone"], r["lvl_name"], r["system"])].append(r)
    drop3, hits3 = set(), []
    for key, items in grp.items():
        series = sorted({r["series"] for r in items})
        if len(series) < 2:
            continue
        A = [r for r in items if r["series"] == series[0]]
        B = [r for r in items if r["series"] != series[0]]
        if not A or not B or abs(len(A) - len(B)) > ct * max(len(A), len(B)):
            continue
        if Counter((r["fam"], r["typ"]) for r in A) != Counter((r["fam"], r["typ"]) for r in B):
            continue
        near = sum(1 for x in A if any(math.dist((x["x"], x["y"]), (y["x"], y["y"])) <= 500
                                       for y in B))
        if near > ov * len(A):
            continue
        loser = B if len(B) <= len(A) else A
        for r in loser:
            drop3.add(id(r))
            qa[r["dwg"]]["dup_removed"] += 1
        hits3.append(f"{key[0]} {key[1]} {key[2]}: bỏ {len(loser)}")
    kept = [r for r in kept if id(r) not in drop3]
    report["dedup_pass3"] = sum(1 for _ in drop3)
    report["dedup_pass3_hits"] = hits3
    return kept


# ============================================================ 4. group notes
def _circuits(texts, pos, reach):
    best = None
    for t in texts:
        q = t.get("p")
        if not q:
            continue
        dd = abs(q[0] - pos[0]) + abs(q[1] - pos[1])
        if dd > reach:
            continue
        mm = RX_RANGE.search((t.get("t") or "").strip())
        if mm:
            a, b = int(mm.group(1)), int(mm.group(2))
            if b >= a and b - a < 60 and (best is None or dd < best[0]):
                best = (dd, b - a + 1)
    return best[1] if best else None


def collect_notes(recs, metas, grids, cfg, qa, report):
    rules = cfg["group_notes"]
    if not rules:
        return []
    tol = float(cfg["dedup"].get("note_dedup_mm", 2500.0))
    reach = float(cfg["dedup"].get("note_range_reach_mm", 3000.0))
    found = defaultdict(list)
    fixes = []
    for rec in recs:
        f = rec["file"]
        m = metas[f]
        for t in rec["texts"]:
            if t.get("sp") != "M" or not t.get("p"):
                continue
            s = " ".join((t.get("t") or "").split())
            for r in rules:
                if not rule_applies(r, m, f):
                    continue
                if r.get("layer") and not re.search(r["layer"], t.get("l") or "", re.I):
                    continue
                mm = re.search(r["pattern"], s, re.I)
                if not mm:
                    continue
                n = int(mm.group(1))
                label = s
                pos = (round(t["p"][0], 1), round(t["p"][1], 1))
                if r.get("circuit_range"):
                    c = _circuits(rec["texts"], pos, reach)
                    if c is not None and c != n:
                        label = f"{s} (dải mạch ghi {c} tuyến -> lấy {c})"
                        fixes.append(f"{f}: '{s}' nhưng dải mạch cạnh đó có {c} tuyến -> lấy {c}")
                        n = c
                found[(m["zone"], m["lvl"])].append((r, n, pos, label, t.get("l", ""), f))
                break
    out, dropped = [], []
    for _k, ms in found.items():
        kept = []
        for it in ms:
            r, n, pos, label, lay, f = it
            dup = next((k for k in kept if k[0]["code"] == r["code"] and k[1] == n and k[5] != f
                        and abs(k[2][0] - pos[0]) < tol and abs(k[2][1] - pos[1]) < tol), None)
            if dup:
                dropped.append(f"'{label}' trên {f} trùng với {dup[5]}")
                continue
            kept.append(it)
        for r, n, pos, label, lay, f in kept:
            m, grid = metas[f], grids[f]
            vi, en = device_names(cfg, r["code"], r)
            qa[f]["note_devices"] += n
            for _ in range(n):
                out.append(base_record(m, f, grid, pos, group=r.get("group", "Thiết bị điện khác"),
                                       code=r["code"], device_vi=vi, device_en=en,
                                       fam="(chú thích CAD)", typ=r["code"],
                                       block_key="(chú thích CAD) | " + r["code"],
                                       attrs=label, layer=lay, source="note"))
    report["note_fixes"] = fixes
    report["note_duplicates_dropped"] = dropped
    return out


# ================================================================ 5. extra
def load_extra(cfg, metas, grids):
    out = []
    for pat in cfg["extra_devices"]:
        path = pat if os.path.isabs(pat) else os.path.join(cfg["_dir"], pat)
        for fp in sorted(glob.glob(path)):
            with open(fp, encoding="utf-8-sig") as fh:
                for row in csv.DictReader(fh):
                    f = row.get("dwg", "")
                    m = metas.get(f)
                    qty = int(float(row.get("qty") or 1))
                    x = float(row["x"]) if row.get("x") not in (None, "") else None
                    y = float(row["y"]) if row.get("y") not in (None, "") else None
                    pos = (x, y) if x is not None and y is not None else None
                    base = base_record(m, f, grids.get(f), pos) if m else {
                        "zone": row.get("zone", ""), "zone_name": row.get("zone_name", ""),
                        "lvl": row.get("lvl", ""), "lvl_name": row.get("lvl_name", ""),
                        "lvl_key": row.get("lvl", ""), "system": row.get("system", ""),
                        "series": "", "dwg": f, "x": x, "y": y, "gridzone": "", "qty": 1}
                    for k in FIELDS:
                        if row.get(k) not in (None, "") and k not in ("x", "y", "qty"):
                            base[k] = row[k]
                    base.setdefault("fam", "(bóc riêng)")
                    base.setdefault("typ", base.get("code", ""))
                    base.setdefault("block_key", base["fam"] + " | " + base["typ"])
                    base["source"] = "extra:" + os.path.basename(fp)
                    for _ in range(max(qty, 1)):
                        out.append(dict(base, qty=1))
    return out


# =============================================================== 6. suffix
def apply_suffixes(recs, metas, grids, cfg, kept, report):
    added, changed = [], 0
    for sm in cfg["suffix_markers"]:
        rx = sm["marker"]
        for rec in recs:
            f = rec["file"]
            m = metas[f]
            if m["role"] not in sm.get("roles", ["layout"]):
                continue
            marks = [t for t in rec["texts"] if t.get("sp") == "M" and t.get("p")
                     and re.search(rx, " ".join((t.get("t") or "").split()), re.I)]
            if not marks:
                continue
            pool = [r for r in kept if r["dwg"] == f and r.get("code") == sm["base_code"]]
            vi, en = device_names(cfg, sm["code"], sm)
            for k, t in enumerate(marks):
                if k < len(pool):
                    r = pool[k]
                    r.update(code=sm["code"], device_vi=vi, device_en=en, typ=sm["code"],
                             block_key=r["fam"] + " | " + sm["code"],
                             attrs=(r.get("attrs") + ";" if r.get("attrs") else "") + "marker="
                             + (t.get("t") or "").strip())
                    changed += 1
                else:
                    pos = (round(t["p"][0], 1), round(t["p"][1], 1))
                    added.append(base_record(m, f, grids[f], pos,
                                             group=sm.get("group", "Thiết bị điện khác"),
                                             code=sm["code"], device_vi=vi, device_en=en,
                                             fam="(chú thích CAD)", typ=sm["code"],
                                             block_key="(chú thích CAD) | " + sm["code"],
                                             attrs=(t.get("t") or "").strip(),
                                             layer=t.get("l", ""), source="suffix"))
    report["suffix_changed"] = changed
    report["suffix_added"] = len(added)
    return added


# ================================================================ main
def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--config", required=True)
    ap.add_argument("--workdir")
    ap.add_argument("--extract", help="folder of extracted JSON (default <workdir>/extract)")
    args = ap.parse_args()

    cfg = load_config(args.config)
    wd = workdir_of(cfg, args.workdir)
    out_dir = os.path.join(wd, "out")
    os.makedirs(out_dir, exist_ok=True)
    recs, failed = load_extracts(args.extract or os.path.join(wd, "extract"))
    print(f"drawings: {len(recs)} ok, {len(failed)} failed conversions")

    metas = {r["file"]: sheet_meta(r, cfg) for r in recs}
    grids = {r["file"]: build_grid(r) for r in recs}
    qa = {r["file"]: {"dwg": r["file"], "folder": metas[r["file"]]["folder"],
                      "role": metas[r["file"]]["role"],
                      "zone_name": metas[r["file"]]["zone_name"],
                      "lvl_name": metas[r["file"]]["lvl_name"],
                      "system": metas[r["file"]]["system"],
                      "model_inserts": 0, "counted": 0, "excl_annotation": 0,
                      "excl_link": 0, "excl_anon": 0, "dup_removed": 0, "unclassified": 0,
                      "text_devices": 0, "note_devices": 0, "pos_outside": 0,
                      "converter": r.get("converter", ""), "note": ""} for r in recs}
    report = {"drawings_ok": len(recs), "drawings_failed": [r.get("dwg") for r in failed]}
    catalogue = {}

    inst = collect_blocks(recs, metas, grids, cfg, qa, catalogue)
    n_blocks = len(inst)
    inst += collect_tags(recs, metas, grids, cfg, qa)
    report["instances_blocks"] = n_blocks
    report["instances_tags"] = len(inst) - n_blocks
    print(f"instances: {n_blocks} from blocks + {len(inst) - n_blocks} from tags")

    kept = dedup(inst, cfg, qa, report)
    print(f"dedup: pass1 -{report['dedup_pass1']}, pass2 -{report['dedup_pass2']}, "
          f"key plans -{sum(int(h.rsplit(':', 1)[1]) for h in report['keyplan_dropped'])}, "
          f"pass3 -{report['dedup_pass3']} -> {len(kept)}")

    notes = collect_notes(recs, metas, grids, cfg, qa, report)
    kept += notes
    extra = load_extra(cfg, metas, grids)
    kept += extra
    report["from_notes"], report["from_extra"] = len(notes), len(extra)
    kept += apply_suffixes(recs, metas, grids, cfg, kept, report)
    print(f"+{len(notes)} from group notes, +{len(extra)} from extra CSV, suffix markers: "
          f"{report['suffix_changed']} re-coded, {report['suffix_added']} added")

    # legend / symbol tables drawn in model space: devices inside a configured box are not
    # devices, whatever their source (block, tag, note, extra CSV)
    boxes_cfg = cfg.get("exclude_boxes") or []
    if boxes_cfg:
        dropped = Counter()
        keep2 = []
        for r in kept:
            hit = None
            if r.get("x") is not None:
                for b in boxes_cfg:
                    x0, y0, x1, y1 = b["box"]
                    if re.search(b.get("sheets", ".*"), r["dwg"]) and x0 <= r["x"] <= x1 and y0 <= r["y"] <= y1:
                        hit = b; break
            if hit:
                dropped[(r["dwg"], r.get("code", ""), hit.get("reason", ""))] += 1
            else:
                keep2.append(r)
        kept = keep2
        report["box_dropped"] = [f"{d}: {n} x {c} - {why}" for (d, c, why), n in dropped.items()]
        print(f"exclude_boxes: -{sum(dropped.values())} " +
              ", ".join(f"{n} {c}" for (d, c, w), n in dropped.items()))

    # positions outside the structural grid: the effective-position recovery failed for
    # that block family on that sheet - the count stands, the location does not
    warn_pos = []
    boxes = {f: grid_box(g) for f, g in grids.items()}
    bysheet = defaultdict(list)
    for r in kept:
        if r["x"] is not None and r.get("source") in ("block", "tag"):
            bysheet[r["dwg"]].append(r)
    for f, items in bysheet.items():
        b = boxes.get(f)
        if not b:
            continue
        out = [r for r in items if not (b[0] <= r["x"] <= b[2] and b[1] <= r["y"] <= b[3])]
        qa[f]["pos_outside"] = len(out)
        if len(out) >= max(10, 0.5 * len(items)):
            fams = Counter(r["block_key"] for r in out).most_common(2)
            warn_pos.append(f"{f}: {len(out)}/{len(items)} thiết bị nằm ngoài lưới trục "
                            f"({', '.join(k for k, _ in fams)}) - vị trí không tin được, "
                            f"số lượng vẫn đúng")
            qa[f]["note"] = "Vị trí không tin được (ngoài lưới trục)"
    report["warnings_position"] = warn_pos

    for r in kept:
        if r["dwg"] in qa:
            qa[r["dwg"]]["counted"] += 1
    unclassified = Counter()
    for (fam, typ), c in catalogue.items():
        if c["reason"] == "CHƯA PHÂN LOẠI":
            unclassified[(fam, typ)] = c["seen"]
    report["unclassified"] = [f"{v} x {k[0]} | {k[1]}" for k, v in unclassified.most_common(60)]
    report["total_devices"] = len(kept)
    report["by_code"] = dict(Counter(r["code"] or "(không mã)" for r in kept).most_common())
    report["by_source"] = dict(Counter((r.get("source") or "").split(":")[0] for r in kept))
    counted = Counter((r["fam"], r["typ"]) for r in kept)

    with open(os.path.join(out_dir, "devices.csv"), "w", newline="", encoding="utf-8-sig") as fh:
        w = csv.DictWriter(fh, fieldnames=FIELDS, extrasaction="ignore")
        w.writeheader()
        w.writerows(kept)
    qcols = list(next(iter(qa.values())).keys()) if qa else []
    with open(os.path.join(out_dir, "qa.csv"), "w", newline="", encoding="utf-8-sig") as fh:
        w = csv.DictWriter(fh, fieldnames=qcols)
        w.writeheader()
        w.writerows(qa[k] for k in sorted(qa))
    with open(os.path.join(out_dir, "catalogue.csv"), "w", newline="", encoding="utf-8-sig") as fh:
        w = csv.writer(fh)
        w.writerow(["family", "type", "rule", "code", "include", "reason", "seen",
                    "counted_after_dedup", "sheets", "main_layer"])
        for (fam, typ), c in sorted(catalogue.items()):
            w.writerow([fam, typ, c["rule"], c["code"], c["include"], c["reason"], c["seen"],
                        counted.get((fam, typ), 0), len(c["sheets"]),
                        c["layers"].most_common(1)[0][0] if c["layers"] else ""])
    json.dump(report, open(os.path.join(out_dir, "count_report.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)

    print(f"\nTOTAL {len(kept)} devices  -> {out_dir}")
    for code, n in list(report["by_code"].items())[:40]:
        print(f"   {code:<16} {n:>6}")
    if unclassified:
        print(f"\n{len(unclassified)} block types on layout sheets matched no rule "
              f"(see catalogue.csv): ")
        for k, v in unclassified.most_common(15):
            print(f"   {v:>6}  {k[0][:56]} | {k[1][:24]}")
    for w_ in warn_pos:
        print("WARNING " + w_)
    for fx in report["note_fixes"]:
        print("NOTE    " + fx)
    return 0


if __name__ == "__main__":
    sys.exit(main())
