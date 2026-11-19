"""Write the quantity take-off workbook from the counted devices.

    python qto_workbook.py --config qto_config.json [--workdir <work folder>] [--out <xlsx>]

Reads <workdir>/out/{devices.csv, qa.csv, catalogue.csv, count_report.json} and
writes one workbook:

  Tổng hợp            building x floor against every device type, grouped
  Chi tiết loại       one line per zone / floor / device / block / source drawing
  Theo khu vực        per structural-grid bay
  Khu vực x nhóm      grid bay against device group
  Danh mục block      every block family | type seen, counted or not, and why
  Kiểm tra            per drawing: read / counted / excluded / de-duplicated / warnings
  Ghi chú phương pháp numbered method notes, generated from what the run actually did

If --out names an existing workbook it is replaced in place (the user asked for one
file to keep control of, not a new file per run). Close it in Excel first.
"""
import argparse
import csv
import json
import os
import sys
from collections import Counter, OrderedDict, defaultdict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from qto_common import load_config, workdir_of, sort_key, stamp  # noqa: E402

import openpyxl  # noqa: E402
from openpyxl.styles import Font, Alignment, PatternFill, Border, Side  # noqa: E402
from openpyxl.utils import get_column_letter  # noqa: E402

F_TITLE = Font(name="Calibri", size=14, bold=True, color="1F3864")
F_SUB = Font(name="Calibri", size=9, italic=True, color="595959")
F_HDR = Font(name="Calibri", size=10, bold=True, color="FFFFFF")
F_GRP = Font(name="Calibri", size=10, bold=True, color="1F3864")
F_BODY = Font(name="Calibri", size=10)
F_TOT = Font(name="Calibri", size=10, bold=True)
FILL_HDR = PatternFill("solid", fgColor="2F5597")
FILL_HDR2 = PatternFill("solid", fgColor="8EAADB")
FILL_GRP = PatternFill("solid", fgColor="D9E2F3")
FILL_TOT = PatternFill("solid", fgColor="FFE699")
FILL_SUB = PatternFill("solid", fgColor="F2F2F2")
FILL_WARN = PatternFill("solid", fgColor="FCE4D6")
THIN = Side(style="thin", color="BFBFBF")
BORDER = Border(left=THIN, right=THIN, top=THIN, bottom=THIN)
C = Alignment(horizontal="center", vertical="center", wrap_text=True)
CV = Alignment(horizontal="center", vertical="bottom", wrap_text=True, textRotation=90)
L = Alignment(horizontal="left", vertical="center", wrap_text=True)
LT = Alignment(horizontal="left", vertical="top", wrap_text=True)


def put(ws, r, c, v, font=F_BODY, align=L, fill=None, border=True):
    cell = ws.cell(row=r, column=c, value=v)
    cell.font, cell.alignment = font, align
    if fill:
        cell.fill = fill
    if border:
        cell.border = BORDER
    return cell


def widths(ws, spec):
    for col, w in spec.items():
        ws.column_dimensions[col].width = w


def title_block(ws, title, subtitle, ncols):
    n = max(ncols, 6)
    ws.cell(row=1, column=1, value=title).font = F_TITLE
    ws.merge_cells(start_row=1, start_column=1, end_row=1, end_column=n)
    ws.cell(row=2, column=1, value=subtitle).font = F_SUB
    ws.merge_cells(start_row=2, start_column=1, end_row=2, end_column=n)
    ws.cell(row=2, column=1).alignment = LT
    ws.row_dimensions[2].height = 28


def header_row(ws, row, labels, fill=FILL_HDR, height=32):
    ws.row_dimensions[row].height = height
    for j, lab in enumerate(labels, start=1):
        put(ws, row, j, lab, F_HDR, C, fill)


def autofilter(ws, first_row, ncols, last_row):
    if last_row > first_row:
        ws.auto_filter.ref = f"A{first_row}:{get_column_letter(ncols)}{last_row}"


def read_csv(path):
    with open(path, encoding="utf-8-sig") as fh:
        return list(csv.DictReader(fh))


# ------------------------------------------------------------------ sheets
def sheet_summary(wb, cfg, rows, st):
    ws = wb.create_sheet("Tổng hợp")
    groups = list(cfg.get("group_order") or [])
    for r in rows:
        if r["group"] not in groups:
            groups.append(r["group"])
    code_of = {}
    for r in rows:
        code_of.setdefault(r["device_vi"], r.get("code", ""))
    by_group = OrderedDict()
    for g in groups:
        devs = sorted({r["device_vi"] for r in rows if r["group"] == g},
                      key=lambda d: sort_key(cfg, code_of.get(d, ""), d))
        if devs:
            by_group[g] = devs
    cols = [(g, d) for g, devs in by_group.items() for d in devs]
    ncols = 2 + len(cols) + 1
    title_block(ws, cfg.get("title", "BẢNG BÓC KHỐI LƯỢNG THIẾT BỊ ĐIỆN & ĐIỆN NHẸ — "
                              + cfg.get("project", "")),
                "Đếm trực tiếp từ bản vẽ CAD (.dwg), không dùng PDF. Tên thiết bị theo bảng "
                "ký hiệu của hồ sơ. " + st, ncols)
    r0 = 4
    put(ws, r0, 1, "Tòa nhà / Khu", F_HDR, C, FILL_HDR)
    put(ws, r0, 2, "Tầng", F_HDR, C, FILL_HDR)
    ws.merge_cells(start_row=r0, start_column=1, end_row=r0 + 1, end_column=1)
    ws.merge_cells(start_row=r0, start_column=2, end_row=r0 + 1, end_column=2)
    c = 3
    for g, devs in by_group.items():
        put(ws, r0, c, g, F_HDR, C, FILL_HDR)
        if len(devs) > 1:
            ws.merge_cells(start_row=r0, start_column=c, end_row=r0, end_column=c + len(devs) - 1)
        for d in devs:
            put(ws, r0 + 1, c, d, F_HDR, CV, FILL_HDR2)
            ws.column_dimensions[get_column_letter(c)].width = 7
            c += 1
    put(ws, r0, c, "TỔNG", F_HDR, C, FILL_HDR)
    ws.merge_cells(start_row=r0, start_column=c, end_row=r0 + 1, end_column=c)
    ws.column_dimensions[get_column_letter(c)].width = 9
    ws.row_dimensions[r0 + 1].height = 160

    agg = defaultdict(Counter)
    zones = OrderedDict()
    for r in rows:
        key = (r["zone"], r["zone_name"], r["lvl"], r["lvl_name"])
        agg[key][(r["group"], r["device_vi"])] += int(r["qty"])
        zones.setdefault((r["zone"], r["zone_name"]), None)
    rr = r0 + 2
    grand = Counter()
    for (z, zn) in sorted(zones):
        zt = Counter()
        for k in sorted({k for k in agg if k[0] == z}, key=lambda k: k[2]):
            put(ws, rr, 1, zn)
            put(ws, rr, 2, k[3])
            tot = 0
            for j, col in enumerate(cols, start=3):
                v = agg[k].get(col, 0)
                put(ws, rr, j, v or None, F_BODY, C)
                tot += v
                zt[col] += v
                grand[col] += v
            put(ws, rr, ncols, tot, F_TOT, C, FILL_SUB)
            rr += 1
        put(ws, rr, 1, zn, F_TOT, L, FILL_GRP)
        put(ws, rr, 2, "Cộng " + z, F_TOT, C, FILL_GRP)
        for j, col in enumerate(cols, start=3):
            put(ws, rr, j, zt.get(col, 0) or None, F_TOT, C, FILL_GRP)
        put(ws, rr, ncols, sum(zt.values()), F_TOT, C, FILL_GRP)
        rr += 1
    put(ws, rr, 1, "TỔNG CỘNG TOÀN DỰ ÁN", F_TOT, L, FILL_TOT)
    put(ws, rr, 2, "", F_TOT, C, FILL_TOT)
    for j, col in enumerate(cols, start=3):
        put(ws, rr, j, grand.get(col, 0), F_TOT, C, FILL_TOT)
    put(ws, rr, ncols, sum(grand.values()), F_TOT, C, FILL_TOT)
    widths(ws, {"A": 34, "B": 22})
    ws.freeze_panes = "C6"


def sheet_detail(wb, rows, st):
    ws = wb.create_sheet("Chi tiết loại")
    cols = ["Tòa nhà / Khu", "Tầng", "Hệ thống", "Nhóm", "Mã ký hiệu", "Loại thiết bị (VI)",
            "Device type (EN)", "Tên block (Family | Type)", "Thuộc tính / chú thích gốc",
            "Bản vẽ nguồn", "Nguồn đếm", "Số lượng"]
    title_block(ws, "CHI TIẾT THEO LOẠI THIẾT BỊ",
                "Mỗi dòng = một loại thiết bị trên một bản vẽ, đã trừ trùng giữa bản tổng và "
                "bản chia phần. Cột 'Thuộc tính / chú thích gốc' chép nguyên văn chữ trên bản vẽ. "
                + st, len(cols))
    header_row(ws, 4, cols)
    agg = Counter()
    for r in rows:
        agg[(r["zone_name"], r["lvl_name"], r["system"], r["group"], r.get("code", ""),
             r["device_vi"], r["device_en"], r["block_key"], r["attrs"], r["dwg"],
             r.get("source", ""))] += int(r["qty"])
    rr = 5
    for k in sorted(agg):
        for j, v in enumerate(k, start=1):
            put(ws, rr, j, v)
        put(ws, rr, len(cols), agg[k], F_BODY, C)
        rr += 1
    widths(ws, {"A": 30, "B": 20, "C": 28, "D": 24, "E": 11, "F": 46, "G": 38, "H": 48,
                "I": 30, "J": 32, "K": 12, "L": 10})
    ws.freeze_panes = "A5"
    autofilter(ws, 4, len(cols), rr - 1)


def sheet_area(wb, rows, st):
    ws = wb.create_sheet("Theo khu vực")
    cols = ["Tòa nhà / Khu", "Tầng", "Khu vực (ô lưới trục)", "Hệ thống", "Nhóm",
            "Loại thiết bị", "Số lượng"]
    title_block(ws, "KHỐI LƯỢNG THEO KHU VỰC (Ô LƯỚI TRỤC)",
                "Khu vực xác định theo ô lưới trục X/Y đọc từ chính bản vẽ. " + st, len(cols))
    header_row(ws, 4, cols)
    agg = Counter()
    for r in rows:
        agg[(r["zone_name"], r["lvl_name"], r["gridzone"] or "(không xác định)",
             r["system"], r["group"], r["device_vi"])] += int(r["qty"])
    rr = 5
    for k in sorted(agg):
        for j, v in enumerate(k, start=1):
            put(ws, rr, j, v)
        put(ws, rr, 7, agg[k], F_BODY, C)
        rr += 1
    widths(ws, {"A": 30, "B": 20, "C": 26, "D": 28, "E": 24, "F": 44, "G": 10})
    ws.freeze_panes = "A5"
    autofilter(ws, 4, len(cols), rr - 1)


def sheet_area_group(wb, cfg, rows, st):
    ws = wb.create_sheet("Khu vực x nhóm")
    groups = [g for g in (cfg.get("group_order") or []) if any(r["group"] == g for r in rows)]
    groups += sorted({r["group"] for r in rows} - set(groups))
    cols = ["Tòa nhà / Khu", "Tầng", "Khu vực (ô lưới)"] + groups + ["Tổng"]
    title_block(ws, "KHU VỰC × NHÓM THIẾT BỊ", "Số lượng thiết bị theo ô lưới trục và nhóm. " + st,
                len(cols))
    header_row(ws, 4, cols, height=44)
    agg = defaultdict(Counter)
    for r in rows:
        agg[(r["zone_name"], r["lvl_name"], r["gridzone"] or "(không xác định)")][r["group"]] += int(r["qty"])
    rr = 5
    for k in sorted(agg):
        put(ws, rr, 1, k[0]); put(ws, rr, 2, k[1]); put(ws, rr, 3, k[2])
        tot = 0
        for j, g in enumerate(groups, start=4):
            v = agg[k].get(g, 0)
            put(ws, rr, j, v or None, F_BODY, C)
            tot += v
        put(ws, rr, len(cols), tot, F_TOT, C, FILL_SUB)
        rr += 1
    spec = {"A": 30, "B": 20, "C": 26}
    for j in range(4, len(cols) + 1):
        spec[get_column_letter(j)] = 14
    widths(ws, spec)
    ws.freeze_panes = "D5"
    autofilter(ws, 4, len(cols), rr - 1)


def sheet_catalogue(wb, cat, st):
    ws = wb.create_sheet("Danh mục block")
    cols = ["Family", "Type", "Quy tắc", "Mã ký hiệu", "Tính khối lượng?", "Lý do loại / ghi chú",
            "Số lần xuất hiện", "SL đã tính (sau trừ trùng)", "Số bản vẽ", "Layer chính"]
    title_block(ws, "DANH MỤC BLOCK VÀ CÁCH PHÂN LOẠI",
                "Mọi block gặp trong bản vẽ đều có một dòng, kể cả block bị loại — không block nào "
                "vô hình. " + st, len(cols))
    header_row(ws, 4, cols)
    rr = 5
    for c in sorted(cat, key=lambda c: (c["include"] != "True", c["family"], c["type"])):
        inc = c["include"] == "True"
        vals = [c["family"], c["type"], c["rule"], c["code"], "Có" if inc else "Không",
                c["reason"], int(c["seen"]), int(c["counted_after_dedup"]), int(c["sheets"]),
                c["main_layer"]]
        for j, v in enumerate(vals, start=1):
            fill = FILL_WARN if (c["reason"] == "CHƯA PHÂN LOẠI") else None
            put(ws, rr, j, v, F_BODY, C if j in (3, 4, 5, 7, 8, 9) else L, fill)
        rr += 1
    widths(ws, {"A": 48, "B": 28, "C": 9, "D": 13, "E": 11, "F": 26, "G": 12, "H": 14,
                "I": 10, "J": 28})
    ws.freeze_panes = "A5"
    autofilter(ws, 4, len(cols), rr - 1)


def sheet_qa(wb, qa, st):
    ws = wb.create_sheet("Kiểm tra")
    cols = ["Bản vẽ", "Thư mục", "Vai trò", "Tòa nhà / Khu", "Tầng", "Hệ thống",
            "Block trong model", "Đã tính", "Loại: chú thích/lưới/khung tên",
            "Loại: liên kết & xref", "Loại: block ẩn danh", "Trùng đã bỏ",
            "Block chưa phân loại", "Thiết bị theo NHÃN", "Thiết bị theo CHÚ THÍCH NHÓM",
            "Vị trí ngoài lưới trục", "Bộ chuyển đổi", "Ghi chú"]
    title_block(ws, "KIỂM TRA THEO TỪNG BẢN VẼ",
                "Đối chiếu số block đọc được với số thực tính, và lý do của phần chênh lệch. " + st,
                len(cols))
    header_row(ws, 4, cols, height=58)
    rr = 5
    keys = ["dwg", "folder", "role", "zone_name", "lvl_name", "system", "model_inserts",
            "counted", "excl_annotation", "excl_link", "excl_anon", "dup_removed",
            "unclassified", "text_devices", "note_devices", "pos_outside", "converter", "note"]
    for q in qa:
        for j, k in enumerate(keys, start=1):
            v = q.get(k, "")
            if j >= 7 and j <= 16:
                v = int(v or 0)
            warn = (k == "unclassified" and v) or (k == "note" and v)
            put(ws, rr, j, v, F_BODY, C if 7 <= j <= 16 else L, FILL_WARN if warn else None)
        rr += 1
    widths(ws, {"A": 34, "B": 16, "C": 10, "D": 26, "E": 18, "F": 28, "Q": 40, "R": 36})
    ws.freeze_panes = "A5"
    autofilter(ws, 4, len(cols), rr - 1)


def method_notes(cfg, rep):
    n = []
    a = n.append
    a(("h", "1. NGUỒN SỐ LIỆU"))
    a(("1.1", f"Khối lượng đếm trực tiếp từ {rep.get('drawings_ok', 0)} file CAD (.dwg), không dùng "
              f"file PDF. Mỗi file được chuyển sang DXF rồi đọc toàn bộ block, chữ và định nghĩa "
              f"block trong model space."))
    if rep.get("drawings_failed"):
        a(("1.2", "Không đọc được: " + ", ".join(rep["drawings_failed"])))
    a(("h", "2. VỊ TRÍ THIẾT BỊ"))
    a(("2.1", "Bản vẽ xuất từ Revit đặt hình học ký hiệu theo toạ độ thật bên trong định nghĩa "
              "block và chèn block ở gốc toạ độ. Vị trí thật = điểm chèn + tâm bao hình của định "
              "nghĩa block, đã nhân tỷ lệ và XOAY theo góc chèn."))
    if rep.get("warnings_position"):
        a(("2.2", "Các bản vẽ sau có nhiều thiết bị rơi ra ngoài lưới trục — cách tính vị trí thất "
                  "bại với họ block đó. SỐ LƯỢNG vẫn đúng, VỊ TRÍ thì không dùng được: "
                  + " | ".join(rep["warnings_position"])))
    a(("h", "3. PHÂN LOẠI"))
    a(("3.1", f"Tên và mô tả thiết bị lấy nguyên văn từ bảng ký hiệu của hồ sơ "
              f"({cfg.get('legend_sheet', 'bản vẽ legend')}), không tự đặt tên. Mỗi họ block được "
              f"gán mã theo {len(cfg['blocks'])} quy tắc; sheet 'Danh mục block' liệt kê mọi họ "
              f"block kể cả loại bị loại và lý do."))
    if rep.get("instances_tags"):
        a(("3.2", f"{rep['instances_tags']} thiết bị không có block, ký hiệu chỉ là nét vẽ thô — "
                  f"đếm theo NHÃN chữ đặt cạnh ký hiệu."))
    if rep.get("unclassified"):
        a(("3.3", f"{len(rep['unclassified'])} loại block trên bản vẽ mặt bằng chưa khớp quy tắc "
                  f"nào và KHÔNG được tính: " + "; ".join(rep["unclassified"][:20])))
    a(("h", "4. TRỪ TRÙNG"))
    a(("4.1", f"Cùng vị trí trên nhiều bản vẽ (dung sai {cfg['dedup'].get('tol_mm', 50)} mm): "
              f"bỏ {rep.get('dedup_pass1', 0)}."))
    a(("4.2", f"Chi tiết phóng to vẽ lại ở vị trí khác (cùng hình mẫu, lệch toạ độ): "
              f"bỏ {rep.get('dedup_pass2', 0)}."))
    if rep.get("keyplan_dropped"):
        a(("4.3", "Sơ đồ định vị (cụm thiết bị rất khít VÀ nằm sát gốc toạ độ): "
                  + "; ".join(rep["keyplan_dropped"])))
    a(("4.4", f"Bản tổng và bản chia phần vẽ ở tỷ lệ khác nhau (cùng số lượng, cùng loại, không "
              f"chồng vị trí): bỏ {rep.get('dedup_pass3', 0)}. "
              + "; ".join(rep.get("dedup_pass3_hits", []))))
    if rep.get("from_notes"):
        a(("h", "5. CHÚ THÍCH NHÓM"))
        a(("5.1", f"{rep['from_notes']} thiết bị đếm theo chú thích dạng \"11x ISW\": người thiết "
                  f"kế chỉ vẽ vài ký hiệu đại diện trong hộp nhóm và ghi số lượng thật bên cạnh."))
        for i, fx in enumerate(rep.get("note_fixes", []), start=2):
            a((f"5.{i}", "Số ghi trong chú thích khác số tuyến trong dải mạch in kèm — lấy theo dải "
                         "mạch: " + fx))
        if rep.get("note_duplicates_dropped"):
            a(("5.9", "Chú thích lặp lại y hệt ở cùng vị trí trên hai bản vẽ chia phần chỉ tính một "
                      "lần: " + "; ".join(rep["note_duplicates_dropped"])))
    if rep.get("suffix_changed") or rep.get("suffix_added"):
        a(("h", "6. BIẾN THỂ THEO HẬU TỐ"))
        a(("6.1", f"Hậu tố viết cạnh thiết bị (vd. WP = vỏ chống nước) tách thành mã riêng: đổi mã "
                  f"{rep.get('suffix_changed', 0)}, thêm {rep.get('suffix_added', 0)} thiết bị "
                  f"chỉ có chú thích mà không có ký hiệu."))
    if rep.get("from_extra"):
        a(("h", "7. BÓC RIÊNG"))
        a(("7.1", f"{rep['from_extra']} thiết bị từ bước bóc riêng (ký hiệu phá khối, nhận dạng "
                  f"hình học...) — xem cột 'Nguồn đếm' trong sheet Chi tiết loại."))
    extra = cfg.get("method_notes") or []
    if extra:
        a(("h", "8. GHI CHÚ RIÊNG CỦA DỰ ÁN"))
        for i, t in enumerate(extra, start=1):
            a((f"8.{i}", t))
    return n


def sheet_method(wb, notes):
    ws = wb.create_sheet("Ghi chú phương pháp")
    ws.column_dimensions["A"].width = 6
    ws.column_dimensions["B"].width = 140
    ws.cell(row=1, column=1, value="GHI CHÚ PHƯƠNG PHÁP BÓC KHỐI LƯỢNG").font = F_TITLE
    rr = 3
    for kind, text in notes:
        if kind == "h":
            put(ws, rr, 1, "", F_GRP, L, FILL_GRP)
            put(ws, rr, 2, text, F_GRP, L, FILL_GRP)
        else:
            put(ws, rr, 1, kind, F_BODY, C, None, False)
            put(ws, rr, 2, text, F_BODY, LT, None, False)
            ws.row_dimensions[rr].height = max(15, 14 * (1 + len(text) // 120))
        rr += 1


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--config", required=True)
    ap.add_argument("--workdir")
    ap.add_argument("--out", help="output .xlsx (default from config 'output_xlsx')")
    args = ap.parse_args()
    cfg = load_config(args.config)
    wd = workdir_of(cfg, args.workdir)
    od = os.path.join(wd, "out")
    rows = read_csv(os.path.join(od, "devices.csv"))
    qa = read_csv(os.path.join(od, "qa.csv"))
    cat = read_csv(os.path.join(od, "catalogue.csv"))
    rep = json.load(open(os.path.join(od, "count_report.json"), encoding="utf-8"))
    out = args.out or cfg.get("output_xlsx") or os.path.join(wd, "QTO_summary.xlsx")
    if not os.path.isabs(out):
        out = os.path.join(cfg["_dir"], out)

    st = stamp()
    wb = openpyxl.Workbook()
    wb.remove(wb.active)
    sheet_summary(wb, cfg, rows, st)
    sheet_detail(wb, rows, st)
    sheet_area(wb, rows, st)
    sheet_area_group(wb, cfg, rows, st)
    sheet_catalogue(wb, cat, st)
    sheet_qa(wb, qa, st)
    sheet_method(wb, method_notes(cfg, rep))
    try:
        wb.save(out)
    except PermissionError:
        raise SystemExit(f"Cannot write {out} - it is open in Excel. Close it and re-run.")
    print(f"-> {out}   ({len(rows)} devices, {len(wb.sheetnames)} sheets)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
