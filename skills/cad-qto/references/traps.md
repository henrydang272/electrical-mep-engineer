# Traps met on a real take-off, and what to do about them

Every item here happened on the MASCOT GIA LAI tender (178 DWG sheets, 24 051 devices).
The numbers are real; use them to recognise the same pattern on a new project.

## Contents
1. Conversion DWG → DXF
2. Revit exports: where a device really is
3. Devices that are not blocks
4. Quantities that are not drawn one by one
5. Same shape, different device
6. The legend symbol is not the plan symbol
7. Variant suffixes (WP, ODT, EX)
8. Duplicates across sheets
9. Things that look like devices but are not
10. Scope splits the BOQ asks for
11. Two sources, two numbers
12. The BOQ itself
13. What the drawings do not show
14. Working safely on the user's machine
15. Project A: devices inside the architecture link, named by one letter
16. Project A: shape detectors that held up
17. Project A: a symbol table inside model space
18. Project A: system column, extra CSV duplicates, tooling
19. Project A: no BOQ in the tender package

---

## 1. Conversion DWG → DXF

- **COM ProgIDs lie.** On a machine with BricsCAD, `AutoCAD.Application` resolves to
  `bricscad.exe`. `qto_convert.py` reads the real exe from the registry and writes it
  into every JSON (`converter`). Report the real program, never the ProgID name.
- **`doc.Close(False)`.** progeCAD saves on close by default; forgetting `False` writes
  into the client's drawing.
- **Never `app.Quit()`** - the COM proxy dies under Python. Kill the exe instead.
- **Cold start**: some programs refuse `Dispatch` from a detached process ("Server
  execution failed"). Launch `<exe> /Automation` first.
- **Recycle every ~40 drawings**; one sheet (an SLD with thousands of blocks) hung the
  program and the run had to self-heal.
- **A modal dialog blocks COM.** If the user has an "Open" dialog up, `--attach` hangs.
  Ask them to close dialogs, or close the program and let the script start its own.
- **Proxy / AEC objects can vanish in conversion.** With a COM backend the script
  compares model-space entity counts before and after and warns on a mismatch.
- **Unicode escapes.** TEXT entities keep Vietnamese as `\U+1EA0`; the scripts decode
  them. If you read DXF yourself, decode with `qto_common.decode_text`.
- DXF from progeCAD was AC1021, 20-52 MB per sheet, 2.5-5 s each.

## 2. Revit exports: where a device really is

- Revit bakes the symbol geometry at its real plan coordinates **inside the block
  definition** and inserts it at (0,0). Position = insert point + centre of the
  definition's extents, **scaled and rotated** by the insert (`effective_pos`).
- The first version forgot the rotation: 72 % of inserts were rotated, 3 787 devices
  moved past the 50 mm de-duplication tolerance and were counted twice. With the fix,
  agreement between overall and part sheets rose from 71 % to 96 %.
- **It still fails for some families.** Socket blocks on guard house 04C landed 70 m
  outside the plan. The COUNT was right (8), the POSITION was not. `qto_count.py` warns
  when most devices of a sheet fall outside the structural grid. Never use positions
  from such a sheet to split by room or to match notes to devices.
- Revit level tags are inconsistent (`LEVEL 01`, `Level 1`, `1ST FLOOR`, `Lever 1`) and
  are part of the de-duplication key - `norm_level` folds them.
- Link blocks (`…_rvt-…`, `…_dwg-…`) and anonymous `*U…` blocks are never devices.
- One Revit family per conduit run (`Conduit Buffer1…680`) is folded to one name; do not
  strip digits in general, it destroys specs such as `L1200`.

## 3. Devices that are not blocks

- **Text tags.** Light switches were drawn as a raw CIRCLE + LINE; the only readable
  marker is the tag `SW1` on an `…-IDEN` layer. Counting blocks gave 8, tags gave 215.
  → `tags` rules. Cross-check once: tags vs nearby circles on one sheet (28 vs 29).
- **Exploded geometry.** Exit and emergency lights were lines and arcs, no block, no
  tag. They needed a shape signature:
  - scale-free: legend at insert scale 0.5, plans at 3/4/350/400 - store **ratios** of
    stroke lengths and angles, never absolute sizes;
  - the same sheet can draw two symbol families at **different scales** - detect each
    scale separately;
  - there can be two versions of the same symbol with different proportions - match a
    structural signature (e.g. 1 socket : 2 lamp heads : 3 petals) not fixed radii;
  - circles get **trimmed into arcs** - de-duplicate by centre, not by entity count;
  - loose tolerances match neighbours: ±8 mm on a 3 087 mm stroke also matched the
    3 080 mm box side. Tighten until the three independent letter strokes agree.
  Write such a detector per project and hand its result to `qto_count.py` as an
  `extra_devices` CSV.
- **Families with the word "symbol"** are excluded by default (legend symbols) - but a
  real device family can carry it: 839 ASD sampling holes were lost until the family
  was added to `exclude.family_keep`. The discriminator was insert scale and spread:
  legend symbols sit at scale 1 in a 5 m column; the real ones at 350/400 over 310 m.

## 4. Quantities that are not drawn one by one

- **Group notes.** A green box holds two representative switches and "…", with the real
  number beside it: `11x ISW` over `4-S16 ~ 4-S26`. Counting symbols gives 2, not 11.
  Before the user pointed this out, the take-off had **17 isolators; the true figure was
  482**. → `group_notes` rules, and check the `Notes` sheet of the inventory for any
  `Nx <something>` on every project.
- **Cross-check the circuit range.** `4x ISW` sat over `4-S1~4-S7` (7 circuits) while the
  three identical bays all said `7x`. `circuit_range: true` takes the range and records
  the correction in the method notes - raise it as an RFI.
- **The same note repeated** at the same spot on two part sheets (`2x ISW` on both 2305
  and 2308, same reference text) is one group, not two - handled automatically.
- Notes like `41x LN1` next to fully drawn battens are a free cross-check:
  106×41 + 84×34 + 16×17 = 7 474 = the block count.
- Notes may carry a wrong **bay prefix** (`4-S16` written in bay 3). Quantity unaffected;
  report it to the user with a picture before treating it as an RFI.

## 5. Same shape, different device

SW (switch) and ISW (isolator switch) are geometrically identical; only the tag beside
them differs. Count by the tag, not the shape. When shapes must be matched to tags,
nearest tag wins within a radius that scales with the drawing scale.

## 6. The legend symbol is not the plan symbol

The legend drew ISW as circle + lever. On the workshop sheets the isolator was a
350×500 box holding two poles, tagged `IS`. Learning only from the legend would have
missed all of them. Always confirm each symbol on a real plan (`qto_render.py sample`)
before trusting a rule, and look for codes that exist on plans but not in the legend
(the legend had no `IS` at all).
Two independent methods agreeing is the best evidence: on four workshop sheets the `IS`
tags (50/51/54/51) equalled the geometric count of box symbols exactly.

## 7. Variant suffixes (WP, ODT, EX)

The legend's ABBREVIATIONS table defines `(WP)` = waterproof, `(ODT)` = outdoor,
`(EX)` = explosion proof. They have no symbol; the designer writes `WP` beside the
device. Treat them as variants of the base device (`suffix_markers`), never as new
devices. The split is exact only where the sockets are drawn: guard house 04C had 8
sockets, 3 with `WP`, and the BOQ asked for 5 + 3.
If a building with toilets, kitchens and laundries has **no** marker at all, the
designer forgot - say so; do not invent a split (MASCOT zone 01: BOQ 76, drawings 0).

## 8. Duplicates across sheets

A device appears on the overall plan, its part plans, enlarged details and key plans.
`qto_count.py` runs four passes; read their counts every time.
1. same place (50 mm) - removed 12 463 of 31 884 on MASCOT
2. an enlarged detail redrawn at another offset (e.g. the MSB room on every sheet) -
   matched by translation-free pattern
3. key plan: a tight cluster **and** at the origin. With only "tight cluster" the first
   version deleted three real guard-house devices standing close together.
4. overall vs part sheets at **different scales** (fire alarm): same count, same mix,
   no positional overlap → one set is dropped. Beacons had been counted 361 vs BOQ 269;
   after this pass 267.
If a device family is still far above the BOQ, suspect a missing pass, not the BOQ.

## 9. Things that look like devices but are not

- **Legend symbols drawn in model space** of a plan (external lighting sheet): tell them
  apart by insert scale (legend 0.5, plan 3.0-4.0) → `drop_scale_below`.
- **One block, two devices**: `FL2` served both 60 W and 150 W floodlights; the tag
  beside each (`LF1`/`LF2`) decides → `code_from_tags`.
- **Overlay families**: a detail-layer outline drawn on top of every floodlight
  (13/15 within 114 mm of the real block, and only 15 `LF` tags for 15 fixtures) - an
  exclude rule, with the reason written down.
- **Your own over-broad rule**: a rule meant for legend artefacts once blanked the whole
  external lighting plan (81 street lights). After adding any exclude rule, re-run and
  compare totals.

## 10. Scope splits the BOQ asks for

The BOQ may list one device twice in the same building with a remark
(`29W LED batten … 2007` and `… 7474 [workshop area]`; `ISW 147` and
`ISW 240 [lighting in workshop]`). `qto_boq.py read` lists these pairs. Ask the user
how the scope is identified on the drawings - on MASCOT: "every sheet numbered 2307.n
is the workshop". Express it with `sheets` filters on rules and a distinct code.
Do not split where the BOQ does not.

## 11. Two sources, two numbers

Isolators were declared both by plan notes and by single-line diagrams (one `IS` tag
per circuit on layer `EE-SO-EQUI`; `IS3` for three-phase busway feeders). The user's
rule: count both, show both, and carry the one closest to the consultant's figure,
recording why. Plan 123 / SLD 155 / BOQ 147 → SLD. Plan 58 / SLD 57 / BOQ 62 → plan.
Put the reasoning in `method_notes`. A second source also found a line the BOQ had
priced but the plans never drew (249 busway isolators = BOQ 240).

## 12. The BOQ itself

- Quantities are formulas (`=47+13+12+9+14+13*4`); `qto_boq.py read` keeps the formula
  - it shows what the consultant added up.
- Two lines with the same description, each with its own AMOUNT formula, are
  **additive**, not a breakdown of each other.
- Header columns differ between projects; the reader finds them by their words - check
  its printout (`item=B, desc=C, qty=E, bidder=F, unit=G, remark=L`).
- **Never copy the consultant's number into the bidder column** without a drawing basis.
  A review pass on MASCOT caught 39 real errors; the common ones: the same devices
  counted for two BOQ lines, devices taken from another building, a number that simply
  equalled the consultant's, a basis naming a drawing that does not exist, and a note
  saying "must check by hand" next to a filled number.

## 13. What the drawings do not show

A tender set at an early stage is incomplete: warehouse sockets 141 in the BOQ, 2 drawn;
ceiling speakers in the schematic but on no plan. Leave the cell empty, say why in the
basis column, and list it as an RFI. An empty cell tells the estimator the truth.

## 14. Working safely on the user's machine

- The user may have the CAD program open with unsaved work: `qto_convert.py` refuses to
  restart a running program unless told `--attach` (then it never kills it).
- Excel keeps a lock on an open workbook; the scripts stop with a clear message.
- Never write to the client's DWG or BOQ; every output is a new file or the one
  take-off workbook the user agreed to keep updating.
- Keep the work folder out of long OneDrive paths when possible (Windows MAX_PATH);
  a short path like `C:\qto\<project>` avoids failures.


---

The sections below come from the PROJECT A tender (the consultant design, 70 DWG sheets
in `03 ELE`, Nov 2026, 1 541 devices). Config and helpers: `assets/projectA_config.json`,
`assets/projectA_tools/`.

## 15. Project A: devices inside the architecture link, named by one letter

- Fire-alarm, exit, IT and PA sheets of the small buildings showed **2-3 model inserts**
  (the `…-A-0001_rvt` and `…-S-0001_rvt` links and the title block). The design was not
  missing: every symbol was drawn as LINE/ARC/CIRCLE on layer `A-ANNO-NOTE` **inside the
  architecture link block**, and the scripts skip link blocks as non-devices. Only the
  letter beside each symbol sat in model space. Look at the PDF of one such sheet before
  concluding a sheet is empty, then cache its geometry with `qto_geom_cache.py`.
- The letters, read off rendered symbols (the FA legend 0003 did not print them):
  `S` circle = addressable smoke detector, `H` circle = addressable heat detector
  (1, in the dry transformer room - **missed at first**, the user found it),
  `M` square = manual call point, `MM` / `CM` box = monitor / control module, `R` / `T` =
  beam receiver / transmitter, `AD` = "addressable" marker on any device (not a device),
  `FIRE` = outdoor fire indicator light, `EXIT`, `IP` = IP camera, `ASD` = aspirating unit,
  `OD` = outdoor-type marker (legend: LOẠI NGOÀI TRỜI), not a device.
  Before writing tag rules, list every short text on the device layer of every FA/exit/IT
  sheet and account for each one.
- Group quantities were written as `xN`: `x5 GV`, `x2 FS`, `x1 ACV` (monitored points at the
  panel) and a bare `x6` beside an `MM` box = 6 modules. On 17B `x8` = 5 GV + 2 FS + 1 ACV -
  a free check. All 7 bare notes paired with a module box within 2.5 m.

## 16. Project A: shape detectors that held up

Scale-free signatures on `A-ANNO-NOTE`, legend block (`LEGEND EXIT_dwg`) skipped:
- **Sounder** (horn beside the call point): ARC with 60-76° sweep whose two ends are
  joined by a LINE (the mouth). 27 found = 27 `M` labels, sheet by sheet (13/11/2/1) -
  every station is call point + sounder.
- **Emergency light**: a coil of one 270° arc and two 225° arcs of the same radius (the
  legend symbol). 06B: 51 x 270° and 102 x 225° = exactly 1:2; 17B: 11 = count on the PDF.
- **Horn loudspeaker**: a 140° arc paired with a 40° arc of ~12.6x the radius. The pair's
  centres are ~1.26 x the big radius apart - a 1.2x search radius found nothing.
  17B: 4 = 4 `WP` labels.
- **Ceiling speaker**: a circle with three lines inside (triangle).
- Exit signs carried the text `EXIT`; buildings without that text had none (PDF checked).

## 17. Project A: a symbol table inside model space

The site plan `000-00-DR-E-2000` had its SYMBOL / DESCRIPTION table drawn in model space,
holding real blocks at plan scale (camera autodome, camera pole, rack cabinet, manhole).
Insert-scale filtering and de-duplication do not catch that; 3 legend symbols were
counted as devices until the user pointed at one. Now: `exclude_boxes` in the config
(drops every counted device inside the box, whatever its source). Take the box from the
table's own lines (layer `ME-Table Line` there), check no plan device falls inside, and
scan every layout sheet for SYMBOL / DESCRIPTION / KÝ HIỆU / DIỄN GIẢI headers.

## 18. Project A: system column, extra CSV duplicates, tooling

- Every plan was series `20xx` (2000 lighting, 2001 power, 2003 earthing, 2021 exit,
  2041 FA, 2051 IT, 2061 PA). `systems_by_series` keyed on the first 2 digits put
  "lighting" on cameras and detectors. `systems_by_series` now uses the longest matching
  key, and `systems_by_file` handles one-off sheets.
- A rack was inserted twice at one point under two block names; a project helper CSV
  (extra_devices) bypasses de-duplication, so it counted 2. De-duplicate by position
  inside every helper.
- Several block families shared one parsed family name (`HVT2-RHD-ZZ-ZZ-DR-E` for both
  manholes and racks, inserted from another drawing): split them by the full block name
  in a helper.
- ezdxf `Vec3` cannot be sliced: `e.dxf.start[:2]` raises, and a bare `except` silently
  dropped every LINE/ARC/CIRCLE from the first geometry cache. Index `[0], [1]`.
- `qto_render.py point --at -197410,112933` fails (argparse reads `-1…` as an option):
  write `--at=-197410,112933`. It also re-reads a 50 MB DXF per picture - for many
  pictures use the geometry cache instead.
- The headless ONLYOFFICE converter (`x2t.exe`) crashed on the workbook; verify picture
  placement from the anchors (`img.anchor.ext`) instead - openpyxl reports the image
  file size in `img.width` after reloading.
- The work folder `C:\qto\<project>` was deleted mid-session once; everything was rebuilt
  from the config and helpers kept in this conversation. Keep helpers in `<workdir>/tools/`
  and copy them into `assets/<project>_tools/` of this skill at the end.

## 19. Project A: no BOQ in the tender package

`Appendix 2/2. Bill of quantity` was empty. Deliver the take-off workbook only, say so in
the first line of the report and in the method notes, and do not invent consultant
figures to compare against.

## 20. Project A, second round (15/11/2026): what the user's own check found

The user re-counted area by area in `Theo khu vực` (added columns "Số lượng của tôi /
Check / Remark"). Read those columns first on any update - they are his comments, not
Excel cell comments (there were none). What he caught, and the fix:
- **Existing items drawn in colour 8** (grey) on the overall routing sheet - all 8
  manholes sat on existing duct → out of scope. On overall/site sheets ask or check the
  colour before counting.
- **Overall routing sheet carries other buildings' panels.** 10 `RHD_Ee_Panel_Electrical`
  on 000-00-DR-E-2000 belonged to 02A/03A/15B and T-31 (ONHOLD). Label each panel by the
  nearest text before counting it; exclude with a `sheets` rule.
- **One device inserted twice from two xrefs** at the same point is de-duplicated, but a
  second real insert of the same rack beside an existing board (DB-08A) was not new.
- **The label beside a block beats the block name** ("ISO. 3P-20A" next to a block
  named 2P-25A). List texts within ~1 m of every isolator/panel block.
- **A heat detector `H`** on 057 - see §15; check every single-letter text again.
- **One plan sheet drawing two buildings** (06B-2000/2010/2012 = 6B + 7B): split by the
  grid line between them (x of grid 6-A1). The split was confirmed by the BOQ: highbays
  200 east / 81 west = consultant 187+13 / 81 exactly.
- Scope change "power + ELV, no earthing/lightning": turn the earthing rules into
  `exclude` rules with the reason, drop the codes from `code_order`; keep lighting (the
  BOQ files lighting under "Lighting fixtures and small power").

## 21. BOQ with "Tender Quantity / Contractor's Quantity" headers

the consultant BOQ (sheets `9. Electrical`, `10. ELV`): header row 11, item=B, description in C
(group) and D (spec), unit=E, `Tender Quantity`=F, `Contractor's Quantity`=G. The header
finder missed "Tender Quantity"; `--cols` used to be ignored when no header scored 3 -
fixed 15/11/2026 (override keys count as found, "… QUANTITY" matches qty). `fill` writes
one sheet per call: chain two calls (second `--boq` = first `--out`).
Pass `--cols item=B,desc=D,unit=E,qty=F,bidder=G,remark=M`.

## 22. Project A, the user's final verification of the BOQ copy (16/11/2026)

Read by diffing our filled copy against his saved one (cell by cell, all sheets). What he
changed - follow it on the next BOQ fill:
- **Format.** He deleted our helper columns N/O/P (gap / basis / confidence) and kept
  only column M "Remark", short, in Vietnamese, written only where a number needs a
  reason. Keep the basis in our own notes/workbook, not as extra BOQ columns.
- **No blanks where the drawing shows nothing.** Line not on the plan → `0` + remark
  "Mặt bằng không có / không vẽ / Không tìm thấy"; on SLD only → `0` + "mặt bằng không
  vẽ, SDNL thì có". Building with no drawings (04B) → `0` + "Không có bản vẽ điện/ELV".
- **Packaged / lot lines get a number**: cabinets (IT/PCD, PA rack, panel lots) = 1 each.
- **Notes on the typical-detail / block-diagram sheets count** (ZZZ-ZZ-DR-E-7003/7004).
  Accessories (surge arrestors, face plates, outlets) are never filled from a default
  rule ("outdoor = no face plate") - only from what this project's design documents say,
  cited in the remark. On Project A that was: 7004 draws 2 signal S.A per outdoor
  camera (cabinet + camera end); the note on 7003 gives a 2-port face plate per indoor
  camera and per AP, and none for outdoor cameras (cabled direct). Another project may
  differ - read its details first, and if nothing is drawn, leave the line for an RFI.
- **Camera split by symbol**: legend 0002 - fixed-body symbol *with hood* = outdoor IP66,
  without hood = indoor, dome = indoor. He wrote it as a per-location formula
  (`=1+1+1+1+2+1` outdoor / `=1+1+1+1` indoor) - 11 = our 11 IP labels on 06B-2051.
- **Label/spec beats BOQ wording**: BOQ asks a 400V 4P+E socket, plan has a 16A-250V
  2P+E S5 → fill 1 and say so in the remark. Where the plan total matches the consultant
  total but the split is not drawn (17B emergency 11 = 2+9), he fills the consultant split.
- **He overrode several of our counts toward the consultant without a remark**: batten
  M01 22→8, M02 10→2; S5 6B/7B 3/9→6/6; 07B ASD 8→4; 07B monitor modules 9→5; 07B
  emergency 25→26; 06B monitor 46 split 24 + 22 (outdoor). Reasons not given - do not
  re-assert our numbers on these lines; if they come up again, ask.
- In the take-off workbook he replaced short device names with the **full legend text**
  (PB box with its whole MCB/RCBO/socket list; S5 = "16A-250V, 2P+E, IP65").

### 22b. Recount of every line where the user's final differed from ours (16/11/2026)
He was right on all of them. Causes, each worth a check on the next project:
- **Model-space leftovers outside the sheet's viewport.** M01-00-DR-E-2000 model space also
  held a copy of 057's 14 battens; M02-2000 held M01's 8 (same coordinates). PDF: M01 = 8,
  M02 = 2. Before trusting a small building's count, compare with the PDF, or clip devices
  to the paper-space VIEWPORT window (code 12/22 centre, 45 view height, 40/41 aspect;
  `assets/projectA_tools/vp_check.py` scans only those groups - ezdxf.readfile is too slow).
  Clip on raw model coordinates only: sheets whose positions were moved onto the site grid
  give false hits.
- **One sheet, two plans of the same building** (07B-2041 = RFL + GFL): the 4 ASD units and
  their 4 MM are drawn at the same grid spot on both plans. Count once per grid position
  (ASD 4, MM 4+1 = 5, not 8 / 9).
- **Splitting two buildings by grid: the wall devices.** 3 S5 on the west wall of 6B fed
  from DP06B1-002/P1 fell on the 7B side of grid 6-A1. Assign by the feeding panel label
  (DP06B… / DP07B…), not by x alone. Correct: 6B 6, 7B 6.
- **Shape detector vs symbols drawn into another symbol.** 07B emergency lights: the
  detector double-hit one wall light and missed 2 drawn joined to an EXIT box → 25, real 26.
  Hand-count a zoomed PDF strip by strip when a detector total is within a few of the BOQ.
- **Labels with no config rule are silent zeros.** 17B "ISW" (6 isolator labels on
  G-ANNO-TEXT) had no `tags` rule. List every short label on each plan against the rules.
- Camera split (06B): ground 7 hooded + 3 dome, mezzanine 1 dome → 7 outdoor / 4 indoor.
