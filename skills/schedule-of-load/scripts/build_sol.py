"""Build a Schedule-of-Load workbook from sol_data.json using the house template.

usage: python build_sol.py sol_data.json OUT.xlsx [--template path]
The JSON format is described in references/data-format.md.
"""
import argparse, copy, json, os, re, sys
import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment

sys.stdout.reconfigure(encoding='utf8')
HERE = os.path.dirname(os.path.abspath(__file__))
ap = argparse.ArgumentParser()
ap.add_argument('data'); ap.add_argument('out')
ap.add_argument('--template', default=os.path.join(HERE, '..', 'assets', 'template.xlsx'))
a = ap.parse_args()
D = json.load(open(a.data, encoding='utf-8'))
S = D['panels']
wb = openpyxl.load_workbook(a.template)


def roman(n):
    s = ''
    for v, r in [(1000, 'M'), (900, 'CM'), (500, 'D'), (400, 'CD'), (100, 'C'), (90, 'XC'), (50, 'L'),
                 (40, 'XL'), (10, 'X'), (9, 'IX'), (5, 'V'), (4, 'IV'), (1, 'I')]:
        while n >= v: s += r; n -= v
    return s


def ins(t):
    t = t.replace(' ', '').upper()
    if 'XLPE/FR-PVC' in t: return 'CXV-FR'
    if 'XLPE' in t: return 'CXV'
    if 'FR/PVC' in t: return 'CVV-FR'
    return 'CVV'


def parse(c):
    """cable as written on SLD -> (S live, T qty, U neutral, V qty, W PE, X qty).
    Text starting with '(' (e.g. '(chung cáp 5C với L1)') or blank = no cable counted on this row."""
    if not c or c.startswith('('): return (None,) * 6
    s = c.replace('²', '2').replace('MM2', 'mm2').replace('_', '-').replace(' mm2', 'mm2')
    m = re.match(r'\s*(\d+)x\((\d+)C-([\d.]+)mm2\s*(Cu/[A-Z/\-]+)\s*\+\s*E-([\d.]+)mm2\)', s)
    if m:  # 2x(3C-25 Cu/PVC/PVC + E-16)
        n, core, sz, i, e = m.groups()
        return (f'{core}C-{sz}mm2 {ins(i)}', int(n), None, None, f'PE 1C-{e}mm2 CV', int(n))
    parts = re.split(r'\+|\s{2,}(?=1C)', s)
    main = parts[0].strip()
    m = re.match(r'(\d+)x(\d+)C-([\d.]+)mm2\s*(\S+)', main) or re.match(r'(\d*)x?(\d+)C-([\d.]+)mm2\s*(\S+)?', main)
    if not m: raise ValueError(f'cannot parse cable: {c!r}')
    n, core, sz, i = m.groups(); n = int(n or 1); core = int(core); i = i or 'Cu/PVC/PVC'
    live = f'{core}C-{sz}mm2 {ins(i)}'; T = n; neu = V = pe = X = None
    if core == 1 and n in (4, 8):  # 4x1C / 8x1C = phases + neutral
        T = n * 3 // 4; neu = live; V = n // 4
    if len(parts) > 1:
        e = parts[1]
        m2 = re.search(r'1C-?([\d.]+)mm2\s*(\S*)', e, re.I)
        pe = f'PE 1C-{m2.group(1)}mm2 CV' + ('-FR' if 'FR' in e.upper() else ''); X = 1
    return (live, T, neu, V, pe, X)


# self-check of the cable parser (shapes seen on real SLDs)
assert parse('8x1C_185 mm2 Cu/XLPE/PVC + 1C_185 mm2 Cu/PVC (E)') == ('1C-185mm2 CXV', 6, '1C-185mm2 CXV', 2, 'PE 1C-185mm2 CV', 1)
assert parse('1x4C_70 mm2 Cu/XLPE/PVC + 1C_35 mm2 Cu/PVC (E)')[:2] == ('4C-70mm2 CXV', 1)
assert parse('2x(3C-25mm² Cu/PVC/PVC + E-16mm²)') == ('3C-25mm2 CVV', 2, None, None, 'PE 1C-16mm2 CV', 2)
assert parse('1x3C-2.5mm² Cu/FR/PVC')[0] == '3C-2.5mm2 CVV-FR'
assert parse('(chung cáp 5C với L1)') == (None,) * 6

# ---------------- SOL
ws = wb['SOL']
grab = lambda r: [copy.copy(ws.cell(r, c)._style) for c in range(1, 39)]
ST_SEC, ST_INC, ST_WAY = grab(6), grab(7), grab(8)
H_INC, H_WAY = ws.row_dimensions[7].height, ws.row_dimensions[8].height
for m in list(ws.merged_cells.ranges):
    if m.min_row >= 5: ws.unmerge_cells(str(m))
ws.delete_rows(6, ws.max_row)
ws['A1'] = f'SCHEDULE OF LOAD & CABLE TAKE-OFF - {D["project"]} / BẢNG THỐNG KÊ PHỤ TẢI & TIÊN LƯỢNG CÁP'
ws['A2'] = 'Fill only the YELLOW cells (AC Hor., AD Ver.). Grey = not applicable. Discrepancies: see QA_LOG. / Chỉ nhập ô màu VÀNG (chiều dài ngang/đứng).'
ws['A3'] = D.get('source_note', '')


def put(r, vals, style, h=None):
    for c in range(1, 39): ws.cell(r, c)._style = copy.copy(style[c - 1])
    for k, v in vals.items():
        if v is not None and v != '': ws[f'{k}{r}'] = v
    if h: ws.row_dimensions[r].height = h


def formulas(r):  # AE stays "" while both lengths are blank, so totals are not inflated by 2*AF
    return {'AE': f'=IF(AND(AC{r}="",AD{r}=""),"",N(AC{r})+N(AD{r}))', 'AF': '=PARAM!$B$7', 'AG': '=PARAM!$B$8',
            'AH': f'=IF(AE{r}="",0,(AE{r}+2*AF{r})*(1+AG{r}))',
            'AI': f'=IF(OR(S{r}="",T{r}=""),0,AH{r}*T{r})',
            'AJ': f'=IF(OR(U{r}="",V{r}=""),0,AH{r}*V{r})',
            'AK': f'=IF(OR(W{r}="",X{r}=""),0,AH{r}*X{r})'}


WAY_KEYS = ('ckt', 'en', 'vn', 'kw', 'kva', 'ph', 'dev', 'poles', 'In', 'icu', 'prot', 'cable', 'cont', 'rem')
row = 6
for si, sec in enumerate(S, 1):
    put(row, {'A': f'{roman(si)}. {sec["name"]}' + (f'  —  {sec["title"]}' if sec.get('title') else '')}, ST_SEC)
    ws.merge_cells(start_row=row, start_column=1, end_row=row, end_column=38)
    row += 1
    for inc in sec['inc']:
        cab = inc.get('cable') or ''
        here = inc.get('here', False)
        p = parse(cab) if here else (None,) * 6
        R = cab if here or not cab or cab.startswith('(') else f'(tính tại lộ ra {inc["src"]}) tại tủ ghi: {cab}'
        v = {'A': 'INCOMING', 'B': sec.get('dwg'), 'C': sec.get('loc'), 'D': inc.get('src'), 'E': 'INCOMER',
             'F': inc.get('desc'), 'M': inc.get('dev'), 'N': inc.get('poles'), 'O': inc.get('In'), 'P': inc.get('icu'),
             'Q': inc.get('prot'), 'R': R, 'S': p[0], 'T': p[1], 'U': p[2], 'V': p[3], 'W': p[4], 'X': p[5],
             'Y': inc.get('cont') if here else None, 'AL': inc.get('remark')}
        v.update(formulas(row)); put(row, v, ST_INC, H_INC); row += 1
    for n, w in enumerate(sec['ways'], 1):
        if len(w) != 14: raise ValueError(f'{sec["name"]} way {n}: expected 14 fields {WAY_KEYS}, got {len(w)}')
        ckt, en, vn, kw, kva, ph, dev, poles, In, icu, prot, cab, cont, rem = w
        p = parse(cab)
        v = {'A': n, 'B': sec.get('dwg'), 'C': sec.get('loc'), 'D': sec['name'], 'E': ckt, 'F': en, 'G': vn,
             'H': kw, 'I': kva, 'L': ph, 'M': dev, 'N': poles, 'O': In, 'P': icu, 'Q': prot, 'R': cab,
             'S': p[0], 'T': p[1], 'U': p[2], 'V': p[3], 'W': p[4], 'X': p[5], 'Y': cont, 'AL': rem}
        if kw is not None or kva is not None:
            v['J'] = f'=IF(I{row}<>"",I{row},H{row}/PARAM!$B$6)'
            v['K'] = f'=IF(J{row}="","",IF(L{row}="RYB",J{row}*1000/(SQRT(3)*PARAM!$B$4),J{row}*1000/PARAM!$B$5))'
        v.update(formulas(row)); put(row, v, ST_WAY, H_WAY); row += 1
LAST = row - 1
ws.freeze_panes = 'F6'

# ---------------- PARAM
pm = wb['PARAM']
P = D.get('param', {})
if 'voltage_note' in P: pm['D4'] = P['voltage_note']
if 'cos_phi' in P: pm['B6'] = P['cos_phi']
if 'cos_note' in P: pm['D6'] = P['cos_note']

# ---------------- SUMMARY: A/B cables (names actually used), C conduits (AA type, AB length)
cs = wb['SUMMARY']
cs.delete_rows(4, cs.max_row)
live, neu, pe = set(), set(), set()
for r in range(6, LAST + 1):
    if ws[f'S{r}'].value: live.add(ws[f'S{r}'].value)
    if ws[f'U{r}'].value: neu.add(ws[f'U{r}'].value)
    if ws[f'W{r}'].value: pe.add(ws[f'W{r}'].value)


def key(n):
    m = re.match(r'(?:PE )?(\d+)C-([\d.]+)mm2 (\S+)', n)
    return (-float(m.group(2)), int(m.group(1)), m.group(3))


cs['A1'] = 'SUMMARY - TỔNG HỢP KHỐI LƯỢNG CÁP & ỐNG CONDUIT (m)'
cs['A2'] = 'Tổng hợp từ sheet SOL (cáp: cột AI LIVE, AJ NEUTRAL, AK PE; ống: cột AA loại ống, AB chiều dài ống). Đơn vị: mét. Chỉ tính cáp lắp mới; cáp hiện hữu/tái sử dụng không tính.'
bold = Font(bold=True, size=10); hfill = PatternFill('solid', fgColor='1F3864'); hfont = Font(bold=True, color='FFFFFF', size=10)
sfill = PatternFill('solid', fgColor='D9E2F3')
cs['A4'], cs['B4'], cs['C4'], cs['D4'] = 'No.', 'Loại cáp / ống - Cable / Conduit type', 'Đơn vị\nUnit', 'Khối lượng\nQuantity (m)'
for c in 'ABCD':
    cs[f'{c}4'].font = hfont; cs[f'{c}4'].fill = hfill
    cs[f'{c}4'].alignment = Alignment(horizontal='center', vertical='center', wrap_text=True)
r, n, R0, R1 = 5, 1, 6, LAST


def block(title, names, kind):
    global r, n
    cs[f'A{r}'] = title; cs[f'A{r}'].font = bold
    for c in 'ABCD': cs[f'{c}{r}'].fill = sfill
    r += 1; first = r
    for nm in names:
        cs[f'A{r}'] = n; cs[f'B{r}'] = nm; cs[f'C{r}'] = 'm'
        if kind == 'A':
            cs[f'D{r}'] = (f'=ROUND(SUMIF(SOL!$S${R0}:$S${R1},$B{r},SOL!$AI${R0}:$AI${R1})'
                           f'+SUMIF(SOL!$U${R0}:$U${R1},$B{r},SOL!$AJ${R0}:$AJ${R1}),1)')
        elif kind == 'B':
            cs[f'D{r}'] = f'=ROUND(SUMIF(SOL!$W${R0}:$W${R1},$B{r},SOL!$AK${R0}:$AK${R1}),1)'
        else:
            cs[f'D{r}'] = f'=ROUND(SUMIF(SOL!$AA${R0}:$AA${R1},$B{r},SOL!$AB${R0}:$AB${R1}),1)'
        cs[f'D{r}'].number_format = '#,##0.0'
        r += 1; n += 1
    cs[f'B{r}'] = f'Tổng nhóm {kind}'; cs[f'C{r}'] = 'm'; cs[f'D{r}'] = f'=ROUND(SUM(D{first}:D{r - 1}),1)'
    cs[f'B{r}'].font = bold; cs[f'D{r}'].font = bold; cs[f'D{r}'].number_format = '#,##0.0'
    tot = r; r += 2
    return tot


ta = block('A. CÁP PHA + TRUNG TÍNH / LIVE + NEUTRAL (multicore tính theo sợi cáp)', sorted(live | neu, key=key), 'A')
tb = block('B. DÂY PE - VÀNG SỌC XANH / EARTH (PE)', sorted(pe, key=key), 'B')
cs[f'B{r}'] = 'TỔNG CỘNG / TOTAL (A + B)'; cs[f'C{r}'] = 'm'; cs[f'D{r}'] = f'=ROUND(D{ta}+D{tb},1)'
cs[f'B{r}'].font = bold; cs[f'D{r}'].font = bold; cs[f'D{r}'].number_format = '#,##0.0'; r += 1
cs[f'B{r}'] = 'Kiểm tra: tổng SOL (AI+AJ+AK)'; cs[f'D{r}'] = f'=ROUND(SUM(SOL!$AI${R0}:$AK${R1}),1)'; r += 1
cs[f'B{r}'] = 'Chênh lệch / Difference'; cs[f'D{r}'] = f'=ROUND(D{r - 2}-D{r - 1},1)'; r += 2
# C. conduit: AA/AB are filled later (cable-estimate skill); AA text must match column B exactly, e.g. "GI Ø25"
used = {ws[f'AA{i}'].value for i in range(6, LAST + 1)} - {None, ''}
CON = sorted(used) or D.get('conduit_types', ['GI Ø50', 'GI Ø32', 'GI Ø25', 'SUS304 Ø32', 'SUS304 Ø25', 'PVC Ø25'])
tc = block('C. ỐNG LUỒN DÂY / CONDUIT (tổng hợp theo cột AA, chiều dài cột AB)', CON, 'C')
r -= 1
cs[f'B{r}'] = 'Kiểm tra: tổng SOL (AB)'; cs[f'C{r}'] = 'm'; cs[f'D{r}'] = f'=ROUND(SUM(SOL!$AB${R0}:$AB${R1}),1)'; r += 1
cs[f'B{r}'] = 'Chênh lệch / Difference'; cs[f'C{r}'] = 'm'; cs[f'D{r}'] = f'=ROUND(D{tc}-D{r - 1},1)'
cs.freeze_panes = 'A5'

# ---------------- PANEL_REG
LL = D.get('load_list', {})  # name -> [kW, kVA, selected A, feed]
pr = wb['PANEL_REG']
pr.delete_rows(4, pr.max_row)
pr['A1'] = f'PANEL REGISTER / DANH MỤC TỦ ĐIỆN - {D["project"]}'
if LL: pr['N3'] = f'Status / note (so với {D.get("load_list_ref", "Load list")})'
r = 4
for i, sec in enumerate(S, 1):
    inc = sec['inc'][0] if sec['inc'] else {}
    m = re.search(r'Pr\s*([\d.]+)', sec.get('title', ''))
    pr_kw = float(m.group(1)) if m else None
    note = []
    if 'không có SDNL' in sec.get('title', ''): note.append('không có SDNL')
    if sec['name'] in LL:
        kw, kva, amp, feed = LL[sec['name']]
        note.append(f'Load list: {kw if kw is not None else "-"} kW / {kva} kVA / {amp}A, feed {feed}')
    pr[f'A{r}'] = i; pr[f'B{r}'] = sec['name']; pr[f'C{r}'] = sec.get('loc'); pr[f'D{r}'] = inc.get('src')
    if pr_kw is not None:
        pr[f'E{r}'] = f'=ROUND({pr_kw}/PARAM!$B$6,1)'
        pr[f'F{r}'] = f'=ROUND(E{r}*1000/(SQRT(3)*PARAM!$B$4),1)'
    elif sec['name'] in LL:
        pr[f'E{r}'] = LL[sec['name']][1]
        pr[f'F{r}'] = f'=ROUND(E{r}*1000/(SQRT(3)*PARAM!$B$4),1)'
    pr[f'G{r}'] = 1; pr[f'H{r}'] = inc.get('dev') or None; pr[f'I{r}'] = inc.get('poles') or None
    pr[f'J{r}'] = inc.get('In'); pr[f'K{r}'] = inc.get('icu')
    pr[f'L{r}'] = inc.get('cable') or None; pr[f'M{r}'] = sec.get('dwg'); pr[f'N{r}'] = '; '.join(note) or None
    for c in range(1, 15):
        pr.cell(r, c).alignment = Alignment(vertical='center', wrap_text=c in (3, 12, 14))
        pr.cell(r, c).font = Font(size=9)
    r += 1

# ---------------- QA_LOG
qa = wb['QA_LOG']
qa.delete_rows(6, qa.max_row)
qa['A2'] = D.get('qa_intro_vn', 'Ghi nhận khi bóc tách bản vẽ SLD. Nên gửi TQ cho tư vấn trước khi đặt cáp / báo giá.')
qa['A3'] = D.get('qa_intro_en', 'Found while transcribing the SLDs. Recommend raising as Technical Queries before ordering cable or pricing.')
for i, item in enumerate(D.get('qa', []), 1):
    pri = item[0]; rr = 5 + i
    for c, v in zip('ABCDEFGH', (i, *item, 'OPEN')):
        qa[f'{c}{rr}'] = v
        qa[f'{c}{rr}'].alignment = Alignment(wrap_text=True, vertical='top')
        qa[f'{c}{rr}'].font = Font(size=9, bold=(c == 'B'), color=('C00000' if pri == 'HIGH' and c == 'B' else None))
qa.freeze_panes = 'A6'

wb.active = wb.sheetnames.index('SOL')
wb.save(a.out)
print(f'saved {a.out}: {len(S)} panels, SOL rows 6-{LAST}, {len(live | neu)} live/neutral + {len(pe)} PE cable types, {len(CON)} conduit types, {len(D.get("qa", []))} QA items')
