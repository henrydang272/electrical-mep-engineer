"""Read a tender BOQ into structured lines, and fill the bidder quantity into a COPY.

  python qto_boq.py read --boq <file.xlsx> --sheet ELECTRICAL [--out boq_lines.json]
  python qto_boq.py fill --boq <file.xlsx> --sheet ELECTRICAL --fill fill.json --out <copy.xlsx>

read
  Finds the header row by its words (ITEM / DESCRIPTION / QTY / BIDDER QTY / UNIT /
  REMARKS, English or Vietnamese) and walks the rows keeping the hierarchy:
    roman numeral in the item column  -> a SYSTEM            (VII SWITCH, SOCKET...)
    dotted number                     -> a SUB-SECTION       (1, 2.3)
    short text line without quantity  -> a BUILDING / area   (01-WORKSHOP)
    line with a numeric quantity      -> a priced item
  Quantities are often formulas ("=47+13+12+9+14+13*4"): the workbook is opened twice
  so both the value and the formula are kept - the formula shows what the consultant
  added up, which is exactly what you need when your count disagrees.
  Items with the same description inside the same building are flagged: the BOQ is
  splitting one device by scope (e.g. two batten lines, one remarked "workshop area"),
  which is where double counting happens.

fill
  fill.json = {"rows": {"1103": {"qty": 465, "basis": "...", "confidence": "cao"},
                        "1104": {"qty": null, "basis": "why it is left blank"}}}
  Copies the BOQ, writes the bidder quantity (yellow), and adds three columns after
  the last used one: difference, basis, confidence. qty null leaves the cell EMPTY on
  purpose - an empty cell says "needs a human", a guessed number hides that.
  The original file is never opened for writing; its SHA-256 is checked before and after.
"""
import argparse
import hashlib
import json
import os
import re
import shutil
import sys
import time
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import qto_common  # noqa: E402,F401

import openpyxl  # noqa: E402
from openpyxl.styles import Font, PatternFill, Alignment  # noqa: E402

COUNTABLE = {"set", "sets", "pcs", "pc", "nr", "no", "nos", "each", "ea", "item",
             "bộ", "cái", "chiếc"}
RX_ROMAN = re.compile(r"^[IVXLC]+$")
RX_NUM = re.compile(r"^\d+(\.\d+)*\.?$")


def sha(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def norm(v):
    return " ".join(str(v).split()) if v is not None else ""


def find_columns(ws, override):
    """-> (header_row, {role: column})"""
    best = None
    for r in range(1, 20):
        cols = {}
        for c in range(1, min(ws.max_column, 40) + 1):
            h = norm(ws.cell(r, c).value).upper()
            if not h:
                continue
            if "BIDDER" in h or "NHÀ THẦU" in h or "CONTRACTOR" in h:
                cols.setdefault("bidder", c)
            elif ("DESCRIPTION" in h or "MÔ TẢ" in h or "DIỄN GIẢI" in h or "HẠNG MỤC" in h
                  or "NỘI DUNG" in h):
                cols.setdefault("desc", c)
            elif h in ("QTY", "QUANTITY", "KHỐI LƯỢNG", "KL", "SỐ LƯỢNG") or h.startswith("QTY") or h.endswith(" QUANTITY"):
                cols.setdefault("qty", c)
            elif ((h in ("UNIT", "ĐƠN VỊ", "ĐVT", "UOM") or h.startswith("UNIT") or h.startswith("ĐƠN VỊ"))
                  and "RATE" not in h):
                cols.setdefault("unit", c)
            elif "REMARK" in h or "GHI CHÚ" in h:
                cols.setdefault("remark", c)
            elif h in ("ITEM", "STT", "NO", "NO.", "TT") or h.startswith("ITEM"):
                cols.setdefault("item", c)
            elif "AMOUNT" in h or "THÀNH TIỀN" in h:
                cols.setdefault("amount", c)
        # roles given by --cols count as found, so a header the keywords miss (e.g. "Tender Quantity") still works
        score = sum(k in cols or k in (override or {}) for k in ("desc", "qty", "unit"))
        if score >= 3 and (best is None or len(cols) > len(best[1])):
            best = (r, cols)
    if not best:
        raise SystemExit("Header row not found - pass the columns with --cols "
                         "item=B,desc=C,qty=E,bidder=F,unit=G,remark=L")
    r, cols = best
    for k, v in (override or {}).items():
        cols[k] = openpyxl.utils.column_index_from_string(v) if isinstance(v, str) else v
    return r, cols


def parse_cols(s):
    if not s:
        return {}
    return dict(kv.split("=", 1) for kv in s.split(","))


def cmd_read(a):
    wbv = openpyxl.load_workbook(a.boq, data_only=True, read_only=False)
    wbf = openpyxl.load_workbook(a.boq, data_only=False, read_only=False)
    sheets = [a.sheet] if a.sheet else wbv.sheetnames
    out = []
    for sh in sheets:
        ws, wf = wbv[sh], wbf[sh]
        try:
            hr, cols = find_columns(ws, parse_cols(a.cols))
        except SystemExit as ex:
            print(f"   [{sh}] {ex}")
            continue
        system = subsec = bldg = ""
        for r in range(hr + 1, ws.max_row + 1):
            item = norm(ws.cell(r, cols["item"]).value) if "item" in cols else ""
            desc = norm(ws.cell(r, cols["desc"]).value)
            qty = ws.cell(r, cols["qty"]).value
            if not desc and not item:
                continue
            if not isinstance(qty, (int, float)) or isinstance(qty, bool):
                if RX_ROMAN.match(item):
                    system, subsec, bldg = desc, "", ""
                elif RX_NUM.match(item):
                    subsec, bldg = f"{item} {desc}".strip(), ""
                elif desc and len(desc) < 70:
                    bldg = desc
                continue
            f = wf.cell(r, cols["qty"]).value
            unit = norm(ws.cell(r, cols["unit"]).value) if "unit" in cols else ""
            out.append({
                "sheet": sh, "row": r, "item": item, "desc": desc, "qty": qty, "unit": unit,
                "formula": f if isinstance(f, str) and f.startswith("=") else "",
                "remark": norm(ws.cell(r, cols["remark"]).value) if "remark" in cols else "",
                "bidder": ws.cell(r, cols["bidder"]).value if "bidder" in cols else None,
                "system": system, "subsection": subsec, "building": bldg,
                "countable": unit.lower().strip(".") in COUNTABLE,
            })
        print(f"[{sh}] header row {hr}, columns "
              + ", ".join(f"{k}={openpyxl.utils.get_column_letter(v)}" for k, v in cols.items()))
    groups = defaultdict(list)
    for x in out:
        groups[(x["sheet"], x["system"], x["building"], x["desc"])].append(x)
    for k, xs in groups.items():
        if len(xs) > 1:
            for x in xs:
                x["same_desc_rows"] = [y["row"] for y in xs if y is not x]
    outp = a.out or os.path.splitext(a.boq)[0] + "_lines.json"
    json.dump(out, open(outp, "w", encoding="utf-8"), ensure_ascii=False, indent=1)

    n_c = sum(1 for x in out if x["countable"])
    print(f"\n{len(out)} priced lines, {n_c} countable (set/pcs/nr/each/item) -> {outp}")
    by_sys = defaultdict(lambda: [0, 0])
    for x in out:
        by_sys[x["system"]][0] += 1
        by_sys[x["system"]][1] += x["countable"]
    for s, (n, c) in by_sys.items():
        print(f"   {s[:48]:<48} {n:>5} lines, {c:>4} countable")
    dup = [x for x in out if x.get("same_desc_rows") and x["countable"]]
    if dup:
        print(f"\n{len(dup)} countable lines share their description with another line in the "
              f"same building - the BOQ splits them by scope; read the REMARKS:")
        seen = set()
        for x in dup:
            key = tuple(sorted([x["row"]] + x["same_desc_rows"]))
            if key in seen:
                continue
            seen.add(key)
            rows = " / ".join(f"row {y['row']}={y['qty']}{(' [' + y['remark'] + ']') if y['remark'] else ''}"
                              for y in groups[(x['sheet'], x['system'], x['building'], x['desc'])])
            print(f"   {x['building'][:18]:<18} {x['desc'][:50]:<50} {rows}")
    return 0


def cmd_fill(a):
    if os.path.abspath(a.out) == os.path.abspath(a.boq):
        raise SystemExit("--out must be a new file; the tender BOQ itself is never written.")
    before = sha(a.boq)
    spec = json.load(open(a.fill, encoding="utf-8"))
    rows = spec.get("rows", spec)
    shutil.copy2(a.boq, a.out)
    wb = openpyxl.load_workbook(a.out)
    ws = wb[a.sheet]
    hr, cols = find_columns(ws, parse_cols(a.cols))
    if "bidder" not in cols:
        raise SystemExit("No bidder-quantity column found; pass --cols bidder=<letter>")
    # last column used ANYWHERE on the sheet: forms keep formulas / sub-headers in columns
    # whose header row is empty (e.g. cost columns N..R headed on the row below), and the
    # added columns must never overwrite them
    last = max(c for c in range(1, ws.max_column + 1)
               if any(ws.cell(r, c).value is not None for r in range(1, ws.max_row + 1)))
    c_diff, c_basis, c_conf = last + 1, last + 2, last + 3
    hfont = Font(bold=True, size=10)
    hfill = PatternFill("solid", fgColor="D9E1F2")
    wrap = Alignment(wrap_text=True, vertical="top")
    for c, lab in ((c_diff, "Chênh lệch (nhà thầu - tư vấn)"),
                   (c_basis, "Cơ sở bóc khối lượng"), (c_conf, "Độ tin cậy")):
        cell = ws.cell(hr, c, lab)
        cell.font, cell.fill, cell.alignment = hfont, hfill, wrap
    ws.column_dimensions[openpyxl.utils.get_column_letter(c_diff)].width = 14
    ws.column_dimensions[openpyxl.utils.get_column_letter(c_basis)].width = 70
    ws.column_dimensions[openpyxl.utils.get_column_letter(c_conf)].width = 12

    wbv = openpyxl.load_workbook(a.boq, data_only=True)
    wsv = wbv[a.sheet]
    yellow = PatternFill("solid", fgColor="FFF2CC")
    n_fill = n_blank = 0
    for key, v in rows.items():
        r = int(key)
        qty = v.get("qty")
        if isinstance(qty, (int, float)) and not isinstance(qty, bool):
            ws.cell(r, cols["bidder"], qty).fill = yellow
            tv = wsv.cell(r, cols["qty"]).value
            if isinstance(tv, (int, float)):
                ws.cell(r, c_diff, qty - tv)
            n_fill += 1
        else:
            n_blank += 1
        if v.get("basis"):
            ws.cell(r, c_basis, str(v["basis"])[:1500]).alignment = wrap
        if v.get("confidence"):
            ws.cell(r, c_conf, v["confidence"])
    note = ws.cell(max(1, hr - 3), c_basis,
                   "Cột khối lượng nhà thầu bóc từ file CAD. Ô tô vàng = đã điền; ô trống = không "
                   "đủ căn cứ, cần rà tay. Lập ngày " + time.strftime("%d/%m/%Y"))
    note.font = Font(italic=True, size=9)
    note.alignment = wrap
    try:
        wb.save(a.out)
    except PermissionError:
        raise SystemExit(f"Cannot write {a.out} - it is open in Excel. Close it and re-run.")
    after = sha(a.boq)
    print(f"-> {a.out}: {n_fill} lines filled, {n_blank} left blank on purpose")
    print(f"   original untouched: {'YES' if before == after else 'NO - CHECK!'} (sha256 {before[:12]}…)")
    return 0


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("read")
    r.add_argument("--boq", required=True)
    r.add_argument("--sheet")
    r.add_argument("--cols", help="override columns, e.g. item=B,desc=C,qty=E,bidder=F,unit=G")
    r.add_argument("--out")
    f = sub.add_parser("fill")
    f.add_argument("--boq", required=True)
    f.add_argument("--sheet", required=True)
    f.add_argument("--fill", required=True)
    f.add_argument("--out", required=True)
    f.add_argument("--cols")
    a = ap.parse_args()
    return cmd_read(a) if a.cmd == "read" else cmd_fill(a)


if __name__ == "__main__":
    sys.exit(main())
