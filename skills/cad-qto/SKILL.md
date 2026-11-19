---
name: cad-qto
description: Take off device quantities (lights, switches, sockets, isolators, fire alarm, CCTV, data, PA, panels, earthing...) from electrical and ELV CAD drawings (.dwg) and produce the Excel quantity summary workbook, and optionally fill the bidder-quantity column of a copy of the tender BOQ. Use this whenever the user wants to bóc khối lượng / bóc tách khối lượng thiết bị, đếm thiết bị trên bản vẽ CAD, lập bảng tổng hợp khối lượng thiết bị điện - điện nhẹ, đối chiếu khối lượng với BOQ của tư vấn, or points at a folder of .dwg drawings plus a legend sheet or a BOQ - even if they never say "take-off" or name this skill. Handles Revit-exported DWGs, symbols that are raw geometry instead of blocks, group notes such as "11x ISW", suffix markers such as WP, devices drawn as raw lines inside Revit link blocks or named by a single letter, legend tables drawn in model space, and duplicates between overall and part sheets; can add symbol and area pictures to the workbook.
---

# CAD device take-off → Excel summary (and BOQ)

The scripts in `scripts/` do everything that is the same on every project: convert DWG,
read blocks and texts, recover real positions, de-duplicate across sheets, write the
workbook, fill a BOQ copy, draw check pictures. Your job is what differs per project:
reading the legend, deciding which block or label is which device, spotting how this
designer draws things, choosing between sources, and telling the user what the
drawings do not support. That split is deliberate - the counting must be reproducible,
the judgement must be yours and must be written down.

A take-off is only worth what can be traced back to a drawing. A number nobody can
trace is worse than an empty cell, because the empty cell at least tells the estimator
to look.

## Ground rules

These come from a real tender and the user who ran it. Hold to them unless the user
says otherwise.

- **Count from the CAD files, never from PDF.** PDFs may be looked at, not counted.
- **The legend sheet names things.** Device names are copied from the project's legend
  (e.g. `…-XX-XX-DR-E-0001`) verbatim, with the legend code. Do not invent names.
- **One take-off workbook, updated in place.** Do not leave a trail of new Excel files;
  the user needs one file to control. Back up before overwriting.
- **Never modify the client's files.** DWGs are only read; the BOQ is filled in a copy.
- **No basis, no number.** Leave the bidder cell empty and write why. Never copy the
  consultant's quantity into the bidder column.
- **Respect the user's CAD program** (e.g. "use progeCAD, not BricsCAD") and never kill a
  CAD program they have open - the convert script refuses to unless told `--attach`.
- **On an update, start from the user's review.** Diff the delivered workbook against your
  last output: his comments may be added columns, renamed cells or inserted rows, not Excel
  comments. Apply them, then carry his columns into the new file
  (`assets/projectA_tools/carry_checks.py`) - traps §20.
- **Show a picture when the user has to decide** (`qto_render.py`), before asking.
- Answer in the user's language; the workbook is in Vietnamese.
- **Keep this skill current.** At the end of every session that used it, write what was
  learned back into this skill: new traps into `references/traps.md`, new config keys into
  `references/config.md`, generic fixes into `scripts/` (back the file up first as
  `<name>.bak-<date>`), project-specific helpers into `assets/<project>_tools/`. The user
  asked for this explicitly.
- **Keep project work recoverable.** The work folder `C:\qto\<project>` can disappear
  (cleanup, restore): keep the project helpers in `<workdir>/tools/` and the config in the
  work folder, and copy deliverables into the project folder with a `_backup/` of the
  previous version.

## Setup

Python 3.10+ with `ezdxf openpyxl matplotlib` (and `pywin32` for CAD-over-COM). Install
what is missing with pip. Use a short work folder such as `C:\qto\<project>` -
OneDrive paths hit the Windows path-length limit. Put `qto_config.json` there too.

`S` below stands for this skill's `scripts` folder.

## Workflow

### 1. Convert the drawings

```bash
python "S/qto_convert.py" --list-backends
python "S/qto_convert.py" --src "<drawings folder>" --workdir "C:/qto/<project>" --backend auto
```
`auto` prefers ODA File Converter (no CAD licence), else a CAD program over COM. If the
user named a CAD program, pass it: `--backend com:Icad.Application` (progeCAD),
`com:BricscadApp.AcadApplication`, `com:AutoCAD.Application` (check `--list-backends`:
on some machines that ProgID is really BricsCAD). Re-run after a crash; finished sheets
are skipped. Read the end of the log for entity-count warnings (objects lost in
conversion).

### 2. Inventory

```bash
python "S/qto_inventory.py" --workdir "C:/qto/<project>" [--config qto_config.json]
```
Open `inventory.xlsx`. It answers the questions the config needs:
**Sheets** (how file names code zone / level / series), **Blocks** (every family | type on
layout sheets, with count, layers, insert scales), **Tags** (short labels, IDEN layers),
**Notes** (`Nx something` group notes), **Legend** (the legend sheet in reading order).

### 3. Write `qto_config.json`

Start from `assets/example_config.json`; the format is in `references/config.md`.
- `sheet_name_regex`, `zones`, `levels`, `sheet_roles` from the Sheets tab. Only
  `layout` sheets are counted; SLDs, schedules, details and the legend are not.
- `legend`: every code with its Vietnamese/English wording from the Legend tab, including
  the ABBREVIATIONS table (WP, ODT, EX are suffixes, not devices).
- `blocks`: one rule per device family | type from the Blocks tab, and an `exclude` rule
  with a written reason for anything that is not a device. Re-run the inventory until
  no family on layout sheets is left unclaimed that could be a device.
- `tags`: labels that stand for a device drawn as raw lines (`SW1` on an IDEN layer).
- `group_notes`: every `Nx CODE` pattern the Notes tab shows. Turn on `circuit_range`.
- `suffix_markers`: the legend abbreviations that mark variants (WP → S2-wp).
- Scope splits: when the BOQ lists one device twice for the same building with a remark
  (e.g. "workshop area"), ask the user how that scope shows on the drawings (on MASCOT:
  "every sheet 2307.n is the workshop") and express it with a `sheets` filter and a
  separate code. Do not split what the BOQ does not.

Before you trust a rule, look at it:
```bash
python "S/qto_render.py" sample --config qto_config.json --src "<drawings>" --code <CODE> --n 3
```
The legend symbol is not always the plan symbol, and two devices can share one shape
and differ only by the label beside them. Read `references/traps.md` §3-§7 once per
project; each item there cost real time to find.

### 4. Devices that are neither blocks nor labels

First check how many sheets have devices at all: on Revit exports a layout sheet can hold
only the architecture link (`…-A-0001_rvt`) and still carry the whole fire-alarm / exit /
PA design - drawn as lines **inside that link block** with a letter beside each symbol
(traps §15). Keep the DXF of those sheets and cache their geometry:
```bash
python "S/qto_convert.py" --src "<drawings>" --workdir "C:/qto/<project>/probe" --backend ... --keep-dxf --only "DR-E-20(41|42|21|61)"
python "S/qto_geom_cache.py" --workdir "C:/qto/<project>" --dxf "C:/qto/<project>/probe/dxf"
```
Then, in order of preference:
1. **Letter labels** next to the symbol (`S`, `H`, `M`, `R`, `EXIT`, `IP` on `A-ANNO-NOTE`)
   → `tags` rules with that `layer` and a `sheets` filter. Render one of each letter and
   read the shape before naming it; list **every** single-letter text on the device layer
   per sheet - one stray `H` (a heat detector) was missed on Project A.
2. **`xN` quantity notes** beside a symbol (`MM` box with `x6`) and `xN CODE` lists
   (`x5 GV`) → `group_notes` for the coded form, a small helper for the bare form
   (example: `assets/projectA_tools/fa_modules.py`).
3. **Shape only** (sounders, emergency lights, speakers): write a detector on the geometry
   cache - angles and radius ratios only, legend block skipped, de-duplicated by centre -
   and cross-check it against an independent count (example:
   `assets/projectA_tools/geo_devices.py`, traps §16). Its CSV goes in `extra_devices`.
`assets/projectA_tools/plotg.py` plots any cached sheet around a point in a second.

### 5. Count

```bash
python "S/qto_count.py" --config qto_config.json
```
Read the whole printout, not just the total:
- de-duplication per pass - a pass removing nothing where overall and part sheets exist
  is suspicious, one removing half of everything is too;
- block types that matched no rule (listed, and in `out/catalogue.csv`);
- `NOTE` lines: a group note whose circuit range disagrees with its number - RFI;
- `WARNING` lines: sheets whose positions fell outside the grid - counts stand, positions
  do not; don't use them to split by area.
- `exclude_boxes` line: devices dropped from a symbol table drawn in model space. Look for
  such tables on every layout sheet (texts SYMBOL / DESCRIPTION / KÝ HIỆU / DIỄN GIẢI) and
  fence them off (traps §17) - the user caught 3 legend symbols counted as devices.
- Extra CSVs bypass de-duplication: a block inserted twice at one point under two names
  is counted twice unless the helper de-duplicates by position.

### 6. Cross-check before believing a number

- Two independent methods on the same devices where possible: tags vs geometric symbol
  count, `Nx` notes vs drawn blocks, plan notes vs single-line diagram ways.
- Per building against the BOQ if there is one. A large gap is a lead, not a verdict:
  check duplicates, group notes, legend-vs-plan symbols, other sheets (SLD, schedules),
  and devices only in the BOQ. When two sources disagree, keep both, show both, and
  record which one you carry and why (`method_notes`).

### 7. Write the workbook

```bash
python "S/qto_workbook.py" --config qto_config.json
```
Sheets: Tổng hợp, Chi tiết loại (with the original note text and the source of every
count), Theo khu vực, Khu vực x nhóm, Danh mục block (every family, counted or not, and
why), Kiểm tra (per drawing), Ghi chú phương pháp (generated from what the run did, plus
your `method_notes`). If the output workbook is open in Excel the script stops - ask the
user to close it. The Hệ thống column comes from `systems_by_file`, `systems_by_folder`,
then the longest key of `systems_by_series` - check it: with 2-digit keys every plan of a
`20xx`-numbered set got the same system.

Pictures (the user wants them): after the workbook,
```bash
python "S/qto_geom_cache.py" --workdir "C:/qto/<project>" --dxf <folder with the DXF of every sheet holding devices>
python "S/qto_pictures.py" --config qto_config.json
```
adds the drawn symbol of each device type under the descriptions of Tổng hợp, and in
Theo khu vực column C a plan picture per row with the counted devices red in blue circles.
Look at a contact sheet of the symbols before handing over; weak ones (dots, hatches)
fall back to the legend sheet. ~8 min for 1 500 devices; the file grows to ~5 MB.
If the user has the workbook open in ONLYOFFICE / Excel, tell them to close it without
saving and reopen, or their open copy overwrites the new one.

### 8. BOQ (when the user gives one)

```bash
python "S/qto_boq.py" read --boq "<BOQ.xlsx>" --sheet ELECTRICAL --out boq_lines.json
```
It prints the column mapping it found (check it), the countable lines per system, and
the lines that share a description within one building - the scope splits.

Map each countable line to device codes and zones yourself, then write `fill.json`:
```json
{"rows": {"1103": {"qty": 465, "basis": "S2 blocks: 01-00=74, 01-01=118, ... Tư vấn 435 + 76 (dòng 1104) = 511, thiếu 46.", "confidence": "trung_binh"},
          "1104": {"qty": null, "basis": "Không có chữ WP nào trên 6 bản vẽ ổ cắm khu 01 - cần RFI."}}}
```
The basis must let someone else trace the number without asking you: which drawings,
which sum, what was excluded, the gap to the consultant. Before filling, review your own
mapping for the errors a review found 39 times on MASCOT (traps §12): same devices on two
lines, devices from another building, numbers equal to the consultant's without a
drawing basis, a basis citing a drawing that does not exist, "must check by hand" next
to a filled number. Then:
```bash
python "S/qto_boq.py" fill --boq "<BOQ.xlsx>" --sheet ELECTRICAL --fill fill.json --out "<BOQ copy>.xlsx"
```
It confirms the original is unchanged (SHA-256).

### 9. Hand-over checks

- `qto_render.py highlight --sheet <drawing>` writes `<drawing>_HIGHLIGHT.dxf` with every
  counted device circled - offer it for the sheets the user will check by hand.
- Pictures for every open question, sent with the report.

## Reporting to the user

Lead with the answer, in the user's language:
- where the file(s) are and what changed since last time;
- totals, and the lines that match the BOQ exactly (these validate the method);
- the largest gaps to the BOQ, each with its cause as far as the drawings show it;
- what was left blank and why; the RFIs, each with a picture;
- choices you made between sources and the reason.
Keep tables short; the workbook holds the detail.

## Files

- `scripts/qto_convert.py` - DWG → compact JSON (ODA or CAD over COM)
- `scripts/qto_inventory.py` - catalogue for writing the config
- `scripts/qto_count.py` - rules, labels, notes, suffixes, 4-pass de-duplication
- `scripts/qto_workbook.py` - the Excel summary
- `scripts/qto_boq.py` - read a BOQ / fill a BOQ copy
- `scripts/qto_render.py` - zoom pictures, samples per code, highlight DXF
  (negative coordinates: write `--at=-197410,112933`, a leading minus breaks argparse)
- `scripts/qto_geom_cache.py` - drawable geometry of kept DXFs (incl. inside Revit links)
- `scripts/qto_pictures.py` - symbol row and area pictures in the workbook
- `references/config.md` - the config format
- `references/traps.md` - what went wrong on a real project and how it was caught
- `assets/example_config.json` - a worked config (MASCOT GIA LAI, trimmed)
- `assets/projectA_config.json`, `assets/projectA_tools/` - Project A (Nov 2026):
  label-only FA/exit/IT sheets, shape detectors, xN module notes, legend-table box,
  4-digit system keys, pictures
