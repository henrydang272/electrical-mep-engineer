"""Catalogue everything in the converted drawings, so the project config can be written.

    python qto_inventory.py --workdir <work folder> [--config qto_config.json]
                            [--legend <regex on sheet name>]

Writes <workdir>/inventory.xlsx (and inventory.json) with one sheet per question the
config has to answer:

  Sheets   every drawing with the zone / level / series / role the config gives it
  Blocks   every block family | type on LAYOUT sheets: count, sheets, layers, insert
           scales, and which config rule (if any) currently claims it
  Tags     short texts: device tags on *IDEN* layers, abbreviations, suffix markers
  Notes    multiplier notes such as "11x ISW" - the designer drew 2 and wrote 11
  Legend   the legend sheet's texts and blocks in reading order (top-down, left-right)

Run it before writing the config and again after, until the Blocks sheet has no
unclaimed family that could be a device.
"""
import argparse
import json
import os
import re
import sys
from collections import Counter, defaultdict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from qto_common import (load_config, load_extracts, parse_block, sheet_meta,  # noqa: E402
                        exclusion_reason, decode_text)

import openpyxl  # noqa: E402
from openpyxl.styles import Font, PatternFill, Alignment  # noqa: E402

RX_NOTE = re.compile(r"^\s*(\d+)\s*[xX×]\s*(.{1,24}?)\s*$")
RX_GRIDLABEL = re.compile(r"^[XY][-_ ]?\d+[A-Za-z]?'?$", re.I)
F_HDR = Font(bold=True, color="FFFFFF")
FILL = PatternFill("solid", fgColor="2F5597")


def first_rule(cfg, fam, typ):
    for i, r in enumerate(cfg.get("blocks", [])):
        if not re.search(r.get("family", ".*"), fam or ""):
            continue
        if r.get("type") and not re.search(r["type"], typ or "", re.I):
            continue
        return i, r
    return None, None


def write_sheet(wb, name, header, rows, widths):
    ws = wb.create_sheet(name)
    ws.append(header)
    for c in ws[1]:
        c.font, c.fill = F_HDR, FILL
        c.alignment = Alignment(wrap_text=True, vertical="center")
    for r in rows:
        ws.append(list(r))
    for i, w in enumerate(widths):
        ws.column_dimensions[openpyxl.utils.get_column_letter(i + 1)].width = w
    ws.freeze_panes = "A2"
    if rows:
        ws.auto_filter.ref = ws.dimensions


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--workdir", required=True)
    ap.add_argument("--config", help="qto_config.json (optional on the first run)")
    ap.add_argument("--legend", help="regex on sheet file name selecting the legend sheet(s)")
    ap.add_argument("--extract", help="folder of extracted JSON (default <workdir>/extract)")
    args = ap.parse_args()

    cfg = load_config(args.config) if args.config else {
        "zones": {}, "levels": {}, "systems_by_folder": {}, "systems_by_series": {},
        "sheet_roles": [], "blocks": [], "exclude": {}}
    recs, failed = load_extracts(args.extract or os.path.join(args.workdir, "extract"))
    print(f"{len(recs)} drawings read, {len(failed)} failed conversions")

    sheets, blocks, tags, notes, legend = [], {}, Counter(), defaultdict(Counter), []
    tag_sheets = defaultdict(set)
    for rec in recs:
        m = sheet_meta(rec, cfg)
        n_ins = sum(1 for i in rec["inserts"] if i.get("sp") == "M")
        sheets.append((rec["file"], m["folder"], m["zone"], m["lvl"], m["series"], m["role"],
                       m["system"], n_ins, len(rec["texts"]), rec.get("converter", "")))
        is_legend = m["role"] == "legend" or (args.legend and re.search(args.legend, rec["file"]))
        if is_legend:
            items = []
            for t in rec["texts"]:
                if t.get("p"):
                    items.append((round(-t["p"][1]), round(t["p"][0]), "TEXT", t.get("l", ""),
                                  decode_text(" ".join((t.get("t") or "").split()))[:200]))
            for i in rec["inserts"]:
                if i.get("p") and i.get("sp") == "M":
                    items.append((round(-i["p"][1]), round(i["p"][0]), "BLOCK", i.get("l", ""),
                                  i["n"][:200]))
            for y, x, k, lay, s in sorted(items):
                legend.append((rec["file"], -y, x, k, lay, s))
        for i in rec["inserts"]:
            if i.get("sp") != "M":
                continue
            p = parse_block(i["n"])
            key = (p["fam"], p["typ"])
            b = blocks.setdefault(key, {"layout": 0, "other": 0, "sheets": set(),
                                        "layers": Counter(), "scales": Counter(),
                                        "why": exclusion_reason(p, i.get("l"), cfg)})
            if m["role"] == "layout":
                b["layout"] += 1
                b["sheets"].add(rec["file"])
            else:
                b["other"] += 1
            b["layers"][i.get("l", "")] += 1
            b["scales"][(i.get("s") or [1])[0]] += 1
        if m["role"] != "layout":
            continue
        for t in rec["texts"]:
            if t.get("sp") != "M":
                continue
            s = decode_text(" ".join((t.get("t") or "").split()))
            if not s or len(s) > 16 or RX_GRIDLABEL.match(s):
                continue
            mm = RX_NOTE.match(s)
            if mm:
                notes[mm.group(2).strip().upper()][int(mm.group(1))] += 1
                continue
            k = (s, t.get("l", ""))
            tags[k] += 1
            tag_sheets[k].add(rec["file"])

    wb = openpyxl.Workbook()
    wb.remove(wb.active)
    write_sheet(wb, "Sheets",
                ["File", "Folder", "Zone", "Level", "Series", "Role", "System",
                 "Model inserts", "Texts", "Converter"], sorted(sheets),
                [44, 16, 8, 8, 12, 10, 28, 10, 8, 50])
    brow = []
    for (fam, typ), b in sorted(blocks.items(), key=lambda kv: -kv[1]["layout"]):
        idx, rule = first_rule(cfg, fam, typ)
        claim = ""
        if rule is not None:
            claim = f"#{idx} " + (rule.get("code") or ("exclude: " + str(rule.get("exclude", ""))))
        brow.append((fam, typ, b["layout"], b["other"], len(b["sheets"]),
                     ", ".join(f"{k}({v})" for k, v in b["layers"].most_common(3)),
                     ", ".join(f"{k}({v})" for k, v in b["scales"].most_common(4)),
                     ", ".join(sorted(b["sheets"])[:3]), b["why"] or "", claim))
    write_sheet(wb, "Blocks",
                ["Family", "Type", "On layout sheets", "On other sheets", "Layout sheets",
                 "Layers", "Insert scales (x)", "Example sheets", "Structural exclusion",
                 "Config rule"], brow, [48, 28, 10, 10, 8, 40, 26, 60, 18, 26])
    trow = [(s, lay, n, len(tag_sheets[(s, lay)]), "IDEN" in lay.upper(),
             ", ".join(sorted(tag_sheets[(s, lay)])[:3]))
            for (s, lay), n in tags.most_common() if n >= 2 or "IDEN" in lay.upper()]
    write_sheet(wb, "Tags", ["Text", "Layer", "Count", "Sheets", "On IDEN layer", "Example sheets"],
                trow, [18, 30, 8, 8, 10, 70])
    nrow = [(item, sum(c.values()), sum(k * v for k, v in c.items()),
             ", ".join(f"{k}x({v})" for k, v in sorted(c.items())))
            for item, c in sorted(notes.items(), key=lambda kv: -sum(kv[1].values()))]
    write_sheet(wb, "Notes", ["Item after 'Nx'", "Number of notes", "Sum of N", "Breakdown"],
                nrow, [22, 14, 12, 80])
    write_sheet(wb, "Legend", ["Sheet", "Y", "X", "Kind", "Layer", "Text / block name"],
                legend, [34, 10, 10, 8, 26, 110])
    out = os.path.join(args.workdir, "inventory.xlsx")
    wb.save(out)
    json.dump({"sheets": sheets, "blocks": brow, "tags": trow, "notes": nrow},
              open(os.path.join(args.workdir, "inventory.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=0)
    unclaimed = [r for r in brow if r[2] and not r[8] and not r[9]]
    print(f"-> {out}")
    print(f"   {len(brow)} block types, {len(unclaimed)} on layout sheets with no config rule "
          f"and no structural exclusion; {len(trow)} tags; {len(nrow)} multiplier-note items; "
          f"{len(legend)} legend items")
    for r in unclaimed[:25]:
        print(f"      {r[2]:>6}  {r[0][:56]} | {r[1][:26]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
