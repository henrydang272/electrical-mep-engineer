---
name: cable-estimate
description: Estimate cable lengths (tiên lượng / bóc khối lượng cáp, chiều dài dây) for every circuit of a Schedule of Load by routing each cable on the CAD drawings - from the panel along the cable tray / trunking centre-line to each load - then fill the SOL columns AA (conduit type), AB (conduit m), AC (Hor.), AD (Ver.) and the BOQ cable lines, and draw every route as 2D polylines on per-panel layer groups in progeCAD. Use whenever the user wants to bóc dây / bóc cáp, tính chiều dài cáp ngang - đứng, điền cột Hor. Ver. Conduit trong SOL, vẽ tuyến cáp từ tủ tới tải, "làm như cad-qto nhưng cho cáp", or gives a drawing folder + SOL + BOQ and asks for cable quantities - even if they never name this skill. Not for counting devices (cad-qto) or building the SOL from SLDs (schedule-of-load).
---

# Cable estimate

Inputs: the project drawing folder (.dwg + PDFs: SLDs, plans, typical installation, specs, standards), the SOL
workbook (from the `schedule-of-load` skill) and the BOQ. Output: SOL columns AA/AB/AC/AD/AL filled, every route
drawn in the DWGs, BOQ cable lines filled, TQ list.

**Every project is bóc differently.** Tray systems, mounting details, conduit rules, which cable runs in which
containment, what counts as vertical - all of it comes from *this* project's documents. The scripts here are a
toolbox, not a procedure. Most of the effort - and most of the user's corrections in the first project - belongs
in step 1. A route drawn fast on a wrong assumption (wrong containment, wrong end point, wrong drop height) is
worse than no route, because the user has to find it and redo it.

## 1. Read and understand the tender documents (spend the most time here)

Read before routing anything, and write what you learn into a project notes file
(`<project>/QTO Dien/cable_notes.md`, same style as `references/example_projectA/notes_projectA.md`).
Show the user the key decisions before computing.

- **Technical specification (electrical)** - conduit material per area (stainless / HDG / PVC / embedded),
  conduit fill and minimum sizes, containment type per system (lighting on trunking vs power on ladder),
  segregation of FR / ELV cables, spare / wastage rules. Search the text for "conduit", "trunking", "tray",
  "stainless", "PVC", "flexible", "embedded", "exposed".
- **Electrical standards / employer's standards** (often a separate BE-/ES- document) - prohibited items
  (e.g. no flexible conduit, no fixed elbows), materials per environment (wet / food / packaging areas).
- **Typical installation details** (E-4000 series or similar) - for each device type: mounting height, how it is
  fixed (wall, steel column, hung under trunking, floor-standing, recessed), where the cable enters (top/bottom),
  conduit size. These decide the route end point and the vertical terms. Open the actual detail (crop at high
  dpi and look); don't assume from the legend.
- **SLDs** - which cable each circuit uses, shared cables (three single-phase ways on one 5C = 3 phases + N +
  PE, one route), FR cables, the incoming feeder of each panel, the containment notes printed on the SLD.
- **Plans** - tray/trunking layouts with BOT/TOL levels, lighting/power/exit plans with circuit labels
  (`PANEL/L1,L2,L3`), panel positions (QPM tags), risers and floor openings.
- **Architectural sections / elevations** - FFL of each floor, mezzanine / platform levels, ceiling and roof
  heights, wall vs steel column positions. Needed for every vertical term and floor crossing.

Before routing, be able to answer, per building: which containment each cable type uses; tray levels; how each
device type is mounted and fed; floor-standing vs wall-hung panel heights; conduit material by area; where
cables cross floors. If a document is missing or contradicts another, write a TQ rather than guess.

## 2. Rules the user fixed (keep unless this project's documents say otherwise)

**Routing - strictly driven by the typical installation method.** The end point and vertical terms of every
route come from the device's installation detail, e.g. power box bolted to a steel column -> end on the column
face (`cable_route.column_face`), not on the symbol; high-bay lamp hung under trunking -> U at the lamp and
2 x 0.35 m drop; wall DB bottom +1.2; floor-standing panel base +0.1.

- Draw **2D polylines** only (never 3D), along the **tray centre-line** (average middle of the tray), on the
  correct containment from the SLD. Maximise length on tray, minimise conduit.
- Panel end: from the panel centre, along the panel edge, up to the tray.
- At each load: draw a **U** (two legs down to near the symbol bottom, inset ~70 mm) - small cables lose the
  most to wastage on site and the U carries that.
- End at the **device centre** (symbol extents), not at its tag text; wall/column devices end at the wall/column
  face.
- Floor-crossing lines: find the floor opening / shaft on the architectural/structural plans or a riser tray,
  route through it; vertical = FFL difference + tray level each floor.
- **Layers**: layer group = panel name; one layer per cable type, named `1x5C-2.5mm2 (DP06B-001)` (suffix keeps
  each layer in one group); FR cables carry ` FR`. Draw each discipline in its own drawing (lighting -> lighting
  plan, power -> power plan, exit -> exit plan, feeders -> tray plan), copying the tray + panel (QPM) layers in at
  the same coordinates first.

**SOL columns**
- **AC Hor.** = sum of the route polylines (number, 1 decimal).
- **AD Ver.** = formula with the concrete numbers, e.g. `=(8.8-0.1)+1.2+13*(0.35+0.35)`:
  panel term (tray level - panel bottom) **plus the loop back up inside the panel** (~1.2 to the breaker row;
  floor-standing bottom +0.1, wall-hung +1.2), plus each load's down+up.
- **AB Conduit (m)** = formula summing the off-tray segments (horizontal and vertical together).
- **AA Conduit type** from spec + standards + the area the line runs in (Project A: SUS304 in packaging /
  process / store / technical rooms and all exposed conduit; PVC only embedded / office / guardhouse).
- Write AA as `<material> Ø<size>` exactly as listed in the SOL's SUMMARY sheet section C (e.g. `GI Ø25`,
  `SUS304 Ø32`, `PVC Ø25`) - SUMMARY sums AB by that text; add a row there for any new type.
- A line with two conduit materials: insert a row directly below, merge A..Y over the two rows, the lower row
  holds the second conduit type + metres (AA/AB).
- **No estimates.** A circuit whose loads are not on the plans (label missing, device not located, coordinates
  can't be matched) stays blank in AA..AD with `TQ: chưa tính - <reason>` in the remark (AL). Only numbers
  measured from drawings go in.
- Never overwrite values the user entered; never edit the user's verified files - back up first
  (`fill_sol.ps1` does).

**BOQ**: fill only the bidder quantity column (G) + a short remark; 0 not blank; lots = 1.

## 3. Get the geometry

Drawings are DWG opened in progeCAD (not PDF) - see memory: `pcad.exe` path, close the "DWG/DXF association"
dialog (WM_CLOSE) before COM works, delete stale `.dwl/.dwl2` after a kill.

- If the `cad-qto` cache exists (`C:/qto/<project>/geom/*.json`, `extract/*.json`, `extra_geo_devices.csv`)
  reuse it - `cable_route.geom()/extract()` read it.
- Otherwise / additionally: `scripts/cad/export_all.ps1 -Root <dwg folder> -Out <tsv folder>` runs `CtExport3`
  on each drawing (layer, kind, points; blocks as extents box + name) - used for symbol centres.
- Drawings of one building are often in different coordinate frames: align by the grid bubbles
  (`cable_route.offset(stem, ref)`, translation only). Check the offset on two grids before trusting it.

## 4. Route and compute

Toolbox (`scripts/route/`, run with plain `python`, `PYTHONUTF8=1`):
- `cable_route.py` - `TrayGraph(segs, gap)`: shortest path on the tray centre-lines (gaps up to `gap` mm
  bridged), `snap/add_point/path`; `manhattan` for conduit runs; `column_face` for column-mounted devices;
  `offset` grid alignment.
- `runner.py` - `Circuit(net, level_fn, panel_pt, panel_kind)`: `goto`, `row` (lighting row + U per lamp),
  `chain` (daisy-chained wall/ceiling devices), `wall_chain` (exit lights: leave tray once, conduit at +3.0),
  `lamp_chain`; `result()` gives AC number, AD/AB formulas, polylines. Adapt the methods to this project's
  installation details rather than forcing the details to fit the methods.

Per building write a small zone module + jobs script (see `references/example_projectA/zone06b.py`,
`jobs_06b.py`, `jobs_small.py`): tray segments + levels, panel points (QPM leader tips), device positions,
then one job per SOL row. Then an assemble step (`example_projectA/assemble.py`) -> `fill_plan.json`
`{row: {AA, AB, AC, AD, note} | {TQ}}`, and a split step (`split_draw.py`) -> per-drawing TSVs + `draw_plan.json`.

**Do one circuit first and show it to the user** (picture via `scripts/cad/render_route.py` or a screenshot)
before running all - the first project's rules came out of that review.

## 5. Write and draw

- SOL: `powershell -File scripts/route/fill_sol.ps1 -Sol <SOL.xlsx> -Plan fill_plan.json` (backs up, uses the
  open Excel workbook if any, hidden Excel otherwise).
- DWG: back up the drawings, then `scripts/cad/draw_one_by_one.ps1 -Root <dwg folder> -Work <dir with
  draw_plan.json> [-TraySrc <tray dwg>]` - opens **one drawing at a time** (15 open at once froze progeCAD),
  copies tray + panels (`CTCOPYD`), draws (`CTDRAW2`), saves, closes; resumable via `draw_done.txt`.
  Plugins are prebuilt `.dll` + source in `scripts/cad/` - see `references/plugins.md`. NETLOAD needs the path.
- Verify: reopen one drawing, check the layer groups and a route; compare SOL totals before/after.

## 6. Report

Rows filled from drawings, TQ rows with reasons, totals change, drawings saved, backups' paths, and the
questions for the consultant (circuits on plans but not on SLD, duplicate labels, missing devices).
