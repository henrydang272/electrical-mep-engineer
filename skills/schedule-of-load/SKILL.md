---
name: schedule-of-load
description: Build the user's "Schedule of Load" (SOL / bảng thống kê phụ tải & tiên lượng cáp) Excel workbook from electrical single-line diagrams (SLD / sơ đồ nguyên lý / SDNL PDFs) and a load list, in the fixed house template (sheets PARAM, SOL, PANEL_REG, SUMMARY, QA_LOG). Use whenever the user asks to làm / lập Schedule of Load, "làm SOL như mọi khi", thống kê phụ tải tủ điện, tiên lượng cáp từ sơ đồ nguyên lý, list every panel's incoming and outgoing ways with breaker and cable, or update an existing SOL after new SLD revisions - even if they don't name the template. Not for counting devices on floor plans (that is cad-qto) or filling a BOQ.
---

# Schedule of Load

Output is always the same workbook structure, because the user compares it across projects and pastes from it
into tenders. The work is: read every SLD precisely → write `sol_data.json` → run `scripts/build_sol.py` →
check in Excel → report discrepancies in QA_LOG.

Python: plain `python` (WindowsApps 3.13) has openpyxl + PyMuPDF in the *user* site-packages, so do **not**
pass `-I` when running these scripts. Use `sys.stdout.reconfigure(encoding='utf8')` in ad-hoc scripts
(Vietnamese text crashes cp1252 output).

## 1. Find the inputs
- SLD PDFs (usually under `03 ELE/<building>/…-DR-E-7000/7001…` or names with "SINGLE LINE", "SƠ ĐỒ NGUYÊN LÝ").
- Load list / load calculation (e.g. `…-CA-E-0001.pdf`): kW, kVA, selected breaker, which panel feeds which.
- Electrical spec for voltage / cos φ if the load list doesn't state it.
List the panels you expect (from load list + drawing titles) before reading, so missing SLDs are noticed.

## 2. Read the SLDs
SLD PDFs exported from CAD are vector — read text, not pixels:
- `page.get_text('dict')` with PyMuPDF; text rotated 90° (vertical lines) is usually the cable label of a way.
- Cable labels drawn once with a leader to several ways: trace the leader with `page.get_drawings()` — the tick
  marks on each way show which circuits share it. A rounded-rectangle bracket over three single-phase ways
  means **one 5C cable shared by the 3 circuits** (write it on the first, `(chung cáp 5C với L1)` on the others).
- Confirm anything doubtful with a zoomed crop (`page.get_pixmap(clip=rect, dpi=300)`) and look at it.
- Per panel record: tag on the panel box, Pi/Ks/Pr, incoming (source, breaker type/poles/In/Icu, protection
  devices, cable), then every outgoing way left-to-right with its real circuit tag, load, phase, breaker, cable.
- Cable at both ends of a feeder: compare the source panel's outgoing way with the receiving panel's incoming.
  Count it once at the source; a mismatch is a HIGH QA item.

Precision matters more than speed here — the user checks cable names, incomings and loads line by line.

## 3. Write sol_data.json
Format and the cable shapes the parser accepts: `references/data-format.md`. A complete real example:
`references/example_projectA.json`. Writing a small Python generator with helpers (as in the example's
repeated lighting ways) is fine; the build only needs the JSON.

Rules the user expects every time:
- One Roman-numbered section per panel; INCOMING row(s) then one row per outgoing way.
- Ckt column = the real tag (L1, L2, EX1…), never "3 lộ".
- Panels named on drawings / load list but with no SLD still get a section titled `không có SDNL - …`.
- Hor./Ver. lengths (AC/AD) are left blank for the user to fill.
- Every discrepancy (mismatched feeder cables, tag spelling differences, missing SLDs, ways with a breaker but no
  cable, non-FR cable on life-safety circuits, FUTURE loads, duplicated tags, unit mistakes) → a `qa` item,
  phrased as a TQ the user can send to the consultant.

## 4. Build and check
```bash
python ~/.claude/skills/schedule-of-load/scripts/build_sol.py sol_data.json "<project>/QTO Dien/<Project>_Schedule-of-Load.xlsx"
powershell -NoProfile -ExecutionPolicy Bypass -File ~/.claude/skills/schedule-of-load/scripts/check_sol.ps1 "<same xlsx>"
```
The check must show `formula errors = 0`, total = 0 with blank lengths, and both diffs = 0 after the test values.

SUMMARY sheet (user's layout, 18/11/2026): **A** live + neutral cables (SUMIF S/U -> AI/AJ), **B** PE (W -> AK),
total A+B with a check against SUM(AI:AK), then **C** conduits: one row per conduit type, `SUMIF(SOL!AA, type,
SOL!AB)`, group total, check against SUM(SOL!AB) and difference. AA/AB are filled later by the `cable-estimate`
skill, so at build time C lists the types already in AA, else `conduit_types` from sol_data.json, else the default
GI/SUS304/PVC Ø25-Ø50 set. AA text must match column B exactly (`GI Ø25`, `SUS304 Ø32`, `PVC Ø25`); add a row in C
for any new type typed into AA, or the difference cell will show it.
Build into a new file; if the target already exists and the user may have typed lengths into it, write next to
it (e.g. `_rev2.xlsx`) and say so — never overwrite their filled-in workbook.

Template: `assets/template.xlsx` (copy of house `EE/DWG/cad/Schedule-of-Load.xlsx`). Route length formula is
`AE = ""` while AC and AD are both blank, otherwise `(AE + 2×AF) × (1 + AG)` per cable; the original template's
`=AC+AD` inflated totals with empty rows, so keep the script's version.

## 5. Report
Short message in Vietnamese: file path, number of panels / ways, cable and conduit types in SUMMARY, the HIGH QA items
in one line each, and what still needs the user (lengths, TQ answers, panels without SLD).
