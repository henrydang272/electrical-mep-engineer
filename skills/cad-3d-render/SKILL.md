---
name: cad-3d-render
description: Read a building's 2D MEP/architectural drawings (PDF + .dwg), build a 3D model of the building with its services (lighting fixtures, switches, DBs...) as solids in progeCAD through COM, and produce presentation renders (1080p / 4K PNG, day, dusk, night, cutaway with lux labels, interiors), a walkthrough MP4 video and an Enscape-style WASD walk viewer (HTML) for the Owner. Use whenever the user wants to dựng 3D / mô hình 3D từ bản vẽ, model 3D a lighting / electrical layout with the architecture around it, đọc bản vẽ PDF và dwg để lấy cao độ trần, tường, cầu thang, cửa, render phối cảnh / render 4K cho chủ đầu tư, or points at a project folder and asks for a 3D of one building - even if they never name this skill. Also for re-rendering or changing an existing package (more realistic trees, other camera angles, 4K).
---

# 2D drawings → 3D model (progeCAD) → presentation renders

Proven on Project A, building 17B (waste handling area, 72 x 10 m, 54 LED battens).
The worked example lives in `examples/17B/` - when unsure how something was done, read it.

Four stages, each with its own deliverable. Do them in order; ask before stages 3-4 if the user
only asked for the model.

| Stage | Tool | Deliverable |
|---|---|---|
| 1. Read drawings | `scripts/pdf_to_png.py`, `dwg_probe.ps1`, `dwg_extract.ps1`, `wall_lines.py` | a short data sheet (grids, walls, openings, heights, fixtures) - see `examples/17B/data_sheet.md` |
| 2. Build 3D | `scripts/progecad3d_lib.ps1` + `templates/build_template.ps1` | `<bldg>_3D.dwg` (3D solids, one layer per element type) |
| 3. Render | `templates/render_scene.html` + `scripts/render_server.py` | PNGs 1920x1080 and/or 3840x2160 |
| 4. Walkthrough | same `render_scene.html` (`recordTour`, `?mode=walk`) | `<bldg>_walkthrough.mp4` + `<bldg>_Viewer.html` |

`templates/render_scene.html` is the generic copy. Two finished examples - start from the closer one:

| Example | Building type | Shows how to model |
|---|---|---|
| `examples/17B/` | steel portal frame, mono-pitch sheet roof, open bays | lighting (54 battens), mesh fences, roller shutters, louvres, ramps, cage ladder |
| `examples/057_HVAC/` | RC/masonry box, flat concrete roof + parapet + canopy | **HVAC** (split AC IDU/CDU, refrigerant trunking, drain, PRDs, motorised dampers, wall exhaust fan), **stairs + handrails**, raised floors, firewalls, painted walls with colour bands |

For a new building, copy the template and **replace the whole building block** (from
`// road marking & kerbs` to `// ---------------- lights / sky`) - see `examples/057_HVAC/building_057.js`
for a self-contained block; keep the engine (materials, sky, trees, video, viewer) untouched.

progeCAD is driven **directly through COM (`Icad.Application`)** - no MCP needed. Revit is
NOT drivable this way (its API only runs in-process); for Revit, write a pyRevit script instead.

## Ground rules

- **Never save or modify a source drawing.** Open DWGs, read, close with `Close($false)`.
  The deliverable DWG is always a new file.
- **Every number traces to a sheet.** Write down where each height/position came from
  (sheet + view). If a value is inferred (roof fall direction, partition type), say so in the reply.
- Do not invent values for the Owner: lux labels only where the drawing gives lux.
- Put deliverables in a project folder the user names (default: `<project>\3D Models\`);
  scratch work goes in the scratchpad.
- Close progeCAD at the end if it was closed when you started (`$app.Quit()` after closing docs without saving).

## Stage 1 - Read the drawings

1. **Find the sheets.** List the discipline folders; get titles cheaply with
   `pdftotext <pdf> - | tr -s ' \n' | grep -i LAYOUT` (Git Bash has pdftotext). Pick:
   the service layout (e.g. `...-E-2000` LIGHTING LAYOUT), the arch plan (`-A-2001`), roof plan,
   elevations & sections (`-A-3001`). Prefer a building that has its own arch sheets.
2. **Look at the PDFs**: `python scripts/pdf_to_png.py <scratch>\img 110 a.pdf b.pdf` then Read the PNGs.
   From them collect: legend (fixture type, wattage, length, IP), notes (mounting height `H=4.5M`,
   switch height 1200), lux per area, room names/areas, FFL / road level, RFL, roof slope and fall
   direction (downpipes `DP` side = low side), overhangs, wall build-up (base masonry height,
   cladding above), open bays (X-marked panels in elevations), stairs/ladders, finish codes (floor
   F-codes → colours in renders).
3. **Probe the DWG** (exact positions): `powershell -File scripts\dwg_probe.ps1 -File "<full path>.dwg"`
   shows fixture block names and the Revit background block (`*_rvt-*`) holding walls/doors/windows.
4. **Extract** with origin = first grid / grid A (read GRID lines on a first run with origin 0,0):
   `dwg_extract.ps1 -DocLike "*E-2000*" -OriginX .. -OriginY .. -Out dump.txt -Block "<rvt block>"`
   then `python scripts/wall_lines.py dump.txt A-WALL` → wall faces; two faces ~200 apart = a wall,
   a face that stops = opening / open bay. Door/window/louvre/mesh-panel blocks (`BB|` lines) carry
   size in their name (`4000x3000`, `4450x1420`, `H2400`) and their insertion point = centre on wall.
5. Write the data sheet (in chat or a file) before modelling. Note fixture orientation: a block
   with rotation 0 may be drawn along Y - check the symbol in the PDF.
6. **HVAC drawings** (layout `-H-2xxx`, equipment schedule, air/AC schematic): positions from the
   layout DWG blocks (`ODU…`, `Ceiling Suspended…`, `PRD…`, `Van MD…`, `Fan On Wall…`) + their MText
   tags; sizes/capacities from the schedule (IDU/ODU HxWxD, kW, m³/h, refrigerant, pipe Ø); routing
   and control intent (1 run / 1 standby, natural vs mechanical ventilation) from the schematic.
   Mounting heights are often NOT dimensioned - scale them from elevations and list them as assumptions.
   Also pull the building's lighting DWG so night views are lit. Each DWG may use a different origin
   (the lighting one used the arch xref insertion point) - find it per drawing.
7. **Stairs**: `DSC_S-STRS` lines give the flight footprint (vertical x = sides, horizontal y = treads).

## Stage 2 - Build the 3D model

Copy `templates/build_template.ps1` to `<project>\3D Models\build_<bldg>.ps1`, fill the DATA block,
add the building's walls/openings/specials (see `examples/17B/build17b.ps1` for partitions, mesh
fences, louvres, ramps, cage ladder, switches, DB), run:

```
powershell -NoProfile -ExecutionPolicy Bypass -File build_<bldg>.ps1 -OutFile "<...>\<bldg>_3D.dwg"
```

Order matters: slab → roof/rafters/columns → all walls → `Opening ...` (cuts every recorded wall it
touches and drops a panel in) → fixtures → `Save-Model` (also deletes empty cutter solids on layer 0).
Run long builds in the background or with a 300-600 s timeout.

**Verify visually**: request computer-use access to "progeCAD 2026 - English (x64)", then from its
command line `VPOINT` `-1.2,-1,0.7`, `ZOOM` `E`, `SHADEMODE` → pick *shaded with Edges* from the menu.
Freeze `A-ROOF` (via COM: `$doc.Layers.Item('A-ROOF').Freeze=$true; $doc.Regen(1)`) to see inside.
Compare counts per layer with the drawing (fixtures, doors, louvres).

**Never skip Stage 2.** The user expects `<bldg>_3D.dwg` in every package, even when the task is
"simulation" / "render" - deliver the DWG together with the HTML viewer and the 4K renders.

### progeCAD COM pitfalls (all hit for real)

- Points are COM objects: `$p.X`, `$p.Y` - indexing `$p[0]` throws "Could not find member".
- PowerShell passes bare `-400` as a **string**; `$z1+$z2` then concatenates. Type params `[double]`.
- Variable names are case-insensitive: `$N` overwrote the counter `$n`. Use distinct names.
- `GetBoundingBox` fails via COM → record extents yourself (the lib's `Box` does).
- `Boolean(2,cutter)` leaves an empty 3dSolid on layer 0 → delete before saving (lib does).
- Entity `.Color` throws; colour by layer (`Layer.Color.ColorIndex`).
- `-VIEW` has no `SWISO` option in progeCAD; use `VPOINT`. `SendCommand` that hits an unexpected
  prompt blocks the COM call → run such scripts with `timeout`, press Escape via computer-use.
- Typing into the command line via clipboard can garble (`E` became ERASE) - prefer `$doc.SendCommand`
  or COM properties; if a prompt like *Select entities to delete* appears, press Escape twice.
- Opening a source DWG may mark it modified (`*`): always `Close($false)`.
- **`Rotate3D(p1, p2, ang)` ALWAYS rotates about an axis through the ORIGIN** - p1/p2 only give the
  direction (test: box at x=10000 rotated 90° "about" a z axis through itself ended at y=10000).
  Angle is in radians, right-hand rule. Use the lib's `Rot3D $s $pivot ax ay az ang` (move pivot to
  origin → rotate → move back); `Tilt` now uses it. Before 2026-11-07 `Tilt` used Rotate3D directly, so
  17B / 057 roofs built earlier may sit offset - rebuild them if their roof matters. Symptom: every
  rotated solid (sloped rails, conduits, ramps) is flung tens of metres out in a fan around 0,0,0.
- `Documents.Add()` with **zero documents open** throws `RPC_E_SERVERFAULT` and leaves an empty
  `DrawingN` → close that one, `Quit()`, and let the build script start progeCAD fresh.
- `$PSScriptRoot` is empty inside a `param()` default when the script is launched via `-File` from
  another PowerShell - resolve paths after `param` with `Split-Path -Parent $MyInvocation.MyCommand.Path`.
- `$solid.Centroid` (`.X .Y .Z`) works via COM - use it to test positions instead of GetBoundingBox.

### Alternative Stage 2: export the solids from the render scene (LP-PARKING, 3 820 solids)
When the WebGL scene is already the richest model (MEP details read from sections: trays dipping
under girders, hanger rods, flexible conduits, conduits detouring below beams, steel rails, stairs),
build the DWG **from the scene** so DWG and renders share one data set:
1. In the scene add `window.exportSolids()`: traverse the un-merged meshes (keep originals hidden
   after merging; skip collision-only boxes via `userData.co`), map material/group → CAD layer, and emit
   `{t:'B', L, c:[x,y,z] mm, d:[dx,dy,dz] mm, a:[axis], g:angle}` for BoxGeometry, `t:'C'` (r, h) for
   cylinders, tube paths split into 4 cylinders, `t:'T'` for zone texts. World→model: `(X, -Z, Y)`;
   box dims map local (X, Z, Y) → model (dx, dy, dz); quaternion → axis-angle with axis also mapped.
2. POST it to the render server as `application/octet-stream` (`/save/<name>.json`).
3. Build script loops the JSON: rotated items `AddBox/AddCylinder` at 0,0,0 → `Rotate3D` about the
   axis through the origin → `Move` to the centre (≈ 22 solids/s; 3 820 in ~3 min, run in background).
Example: `OneDrive\Desktop\CB-LP-Parking Modulation\3D Models\build_LPP.ps1` + `src\lpp_solids.json`
(22 layers S-/A-/E-); scene source `src\LPP_viewer.src.html` (Project A-style viewer UI).

## Stage 3 - Render

progeCAD's own renderer is not presentation quality. Rebuild the same geometry in the WebGL scene:

1. Copy `templates/render_scene.html` → `<project>\3D Models\render-source\index.html` and
   `scripts/render_server.py` → same folder.
2. Adapt the scene - **every item below is 17B data today; change all of them** (sections are
   marked `// ---------------- ... ----------------`, all in **metres**, origin = first grid / grid A):

   | Where | What to set |
   |---|---|
   | `CFG` (top) | `code` (file-name prefix), `title`, `project`, `gridPrefix` (HUD grid labels) |
   | *site* | yard/apron/road extents, gutters + ramps along the right sides, tree rows clear of cameras |
   | *structure* | `gx` grid list, columns, rafters, purlins, `roofTop` / `roofUnder` (RFL, slope, overhangs) |
   | *walls* | perimeter segments (closed vs open bays), internal walls, fences, `RS`/`ED`/louvre openings |
   | finishes | floor `zones` (F-codes → `tileF2` / `tileF3` ...), wall materials from the finish schedule |
   | *lighting* | `fx` fixture list (from `dwg_extract` INS lines), mounting height, fixture size/orientation |
   | *labels* | room names + lux **only where the drawing gives lux** |
   | `views` | camera `cam`, target `tgt`, `fov`, mood `day / dusk / cutaway / night`, `roof`, `labels` |
   | `tour` | video key frames (Stage 4) |
   | `zoneDefs` (walk mode) | one zone per room, x ranges matching the walls |

   Trees are procedural (clumped noisy canopies + branches) - keep them.
3. Start the server (background): `python render_server.py "<project>\3D Models\Renders"`
   (serves its own folder on http://127.0.0.1:8765, POST /save/<name> writes the PNG).
4. Open in the built-in browser: `preview_start` url `http://127.0.0.1:8765/index.html`
   (`?res=4k` for 3840x2160; files get suffix `_4K`).
5. The pane may be hidden → never `await` a long render in one javascript_tool call (45 s limit).
   Pattern: wait ~15 s for `window.ready`, then
   `window._res='running'; window.shootAll().then(r=>window._res=r); 'started'`,
   then poll `await new Promise(r=>setTimeout(r,30000)); window._res`.
   Single view: `window.shoot('<view-name>')`.
6. **Read every PNG** and fix what looks wrong before delivering; re-render. Send finished
   images with SendUserFile (`display: render` for previews, `attach` for 4K).

### Render pitfalls (all hit for real)

- Changing `shadow.camera` bounds needs `shadow.camera.updateProjectionMatrix()` - else no shadows.
- Camera `far` must exceed the sky dome radius (5000 vs 1400) - else black sky.
- Ground must be huge (3000 m) and fog colour = horizon colour, or a grey ground edge shows.
- Area lights near glossy floors make glare blobs: floor roughness ≥ 0.8, intensity 3-6.
- Under-roof looks black without bounce: hemisphere ground colour light (`0xb8b2a6`) + insulation lining.
- Keep cameras out of tree rows; labels alternate rows (y=1.8 / 8.2) so they don't overlap.
- 4K PNGs are 7-15 MB each; offer JPG copies for PowerPoint.
- **White painted walls** blow out at dusk/cutaway with bloom threshold .75 → use threshold ≥ .93
  (057). Closed rooms get a black concrete soffit → small `emissive` on the soffit material.
- Trees: skip any tree within ~8 m of a camera position (`camXY` list) - a foreground tree ruined
  the 057 north-west view.
- Interior views need doors open: put door leaves in `shutters` and set `open: true` on the view.

## Stage 4 - Walkthrough video + Enscape-style viewer (same scene file)

**Video (H.264 MP4, plays in PowerPoint).** No ffmpeg on this machine and OpenCV has no H.264;
the scene encodes in-browser with WebCodecs + `mp4-muxer` and POSTs the MP4 (binary) to the server.
1. Edit the `tour` key list `[t s, eye x,y,z, look-at x,y,z]` (metres, model coords). Eye 1.65 m.
   **Plan the path on the plan drawing**: enter/leave only through open bays or roller-shutter
   openings (the recorder opens shutters); a Catmull-Rom curve between two points inside
   different rooms WILL cut through fences/louvres - add a key at the opening.
2. Check frames first: `window.tourAt(t)` then `canvas.toDataURL` → POST `/save/check_t<t>.jpg`;
   contact-sheet them with PIL and Read.
3. Record: `window.recordTour()` (default **60 fps, 20 Mbit/s** - user asked for the max their screens show; laptop 60 Hz, ARZOPA 75 Hz → 60 is the common max and the projector standard) (returns immediately if called without await; poll
   `window._prog` = "frame/total" → "done NN MB ok"). 93 s at 1080p 60 fps ≈ 3 min to render, ≈ 230 MB. Keep polling - the hidden pane can reload near the end; check the file timestamp before re-recording.
   `?res=4k` gives a 4K video. Verify with OpenCV: frame count, fps, codec `h264`, contact sheet.

**Viewer.** The same file opened by double-click (`file://`) or with `?mode=walk` becomes an
interactive walk viewer: WASD, mouse look (pointer lock), Shift run, Space jump, F Ghost
(fly, no collision; Space/E up, Q down), 1/2/3 day/dusk/night, R roof, L labels+lux, O shutters.
Collision = AABBs of building/site meshes (not foliage/lights/roof), ground = raycast down
(ramps and steps ≤ 0.4 m work). Deliver a copy named `<bldg>_Viewer.html`.
- Performance (user saw ~20 fps before these): walk mode merges static meshes per material
  (`mergeStatic`, ~1100 → ~28 draw calls; hidden originals kept for collision/raycast, shutters
  kept separate), replaces the per-fixture RectAreaLights with one per zone (same total output,
  off by day), disables bloom by day, renders at pixel ratio 1 and adapts 0.6-1.0 to hold ~50 fps.
  Keep `zoneDefs` in sync with the building's rooms.
- If the user reports low fps / GPU 0 %: check the WebGL renderer string first (in their Chrome via
  the extension: `WEBGL_debug_renderer_info`). "Microsoft Basic Render Driver"/SwiftShader = CPU
  rendering; on this machine Chrome had `hardware_acceleration_mode.enabled=false` in
  `%LOCALAPPDATA%\Google\Chrome\User Data\Local State`. The user turns it on (Settings → System →
  graphics acceleration → Relaunch) - do not edit their browser config yourself. The viewer shows
  a red warning on the start card when this happens.
- The built-in browser pane is usually hidden → requestAnimationFrame stops (0 fps). Test the
  physics by calling `window._forceWalk=true; window._walk.update(1/60)` in a loop and checking
  `_walk.player.feet` (walk into a fence/wall, out through an open bay, jump peak ≈ 0.7 m, Ghost).
  Pick test spots that are not on a grid line (columns / fence upstands sit there).
  Walk mode **opens doors/shutters by default** and `O` toggles - a test that presses O first
  closes them (057: looked like "can't enter"). Spawn test points on raised surfaces with the right
  z (`V(x, y, 0.75)` on a landing), else the player starts inside the solid and gets stuck.
  Good 057 checks: yard → stair treads → landing → raised floor (z 0 → .45 → .75 → .80), then
  room walls/firewalls/equipment that projects from walls (MD damper stopped the player - correct).
- To measure **real** fps on the user's machine, use the Claude-in-Chrome extension on
  `http://127.0.0.1:8765/index.html?mode=walk` (it cannot open `file://` or `chrome://`):
  count requestAnimationFrame callbacks over 3 s per mood, and for GPU headroom render 60 frames
  back-to-back ending with `gl.readPixels` (uncapped fps). Wait ~3 s after load - the first
  seconds are shader compilation (reads ~1 fps). Playwright's software WebGL times out - don't use it.
- **fps is capped by the monitor refresh rate** in any browser. On this machine: laptop panel BOE
  40/60 Hz, ARZOPA 60/75 Hz (check with `Get-CimInstance -Namespace root\wmi
  WmiMonitorListedSupportedSourceModes`). Measured 880M headroom for 17B: ~1150 fps day / ~170 fps
  night at 1080p - so "more fps" requests are a monitor question, not a code one. Never uncap the
  render loop (wasted frames, heat).

## Stage 5 - Whole project on the master plan (reuse detailed buildings)

User preference: **render the whole project**, not building by building; detailed buildings already
done are **relocated** onto the master plan. Example: `examples/site_render_scene_SITE.html`
(Project A: 88 massing footprints + 17B + 057 relocated, georeferenced roads/lawns, 320 trees).
Scripts in `scripts/site/`:

1. **Find the site sheets**: master plan / site plan (`000-XX-DR-A-2001` SITE PLAN has the Phase-16
   **height table**), 3D overview (`A-0002`), civil road & pavement layout (`C-0100`).
2. `site_dump.ps1 <out.txt>` (open the site-plan DWG first) → footprints + labels from the master
   plan block. `footprints.py` → closed polygons labelled by the building number inside;
   `classify_buildings.py` → kind + height (Phase-16 from the table, existing **estimated** from the
   3D view - flag `est`). True width = 2·area/perimeter; < 4 m = covered walkway, not a 6 m wall.
3. **Ground**: georeference the C-0100 PDF with an affine fit on ≥5 building labels (fitz
   `search_for` on the rotated page ↔ DWG MText coords; residuals were < 0.35 m), then
   `ground_texture.py` classifies the **full-res** raster (sampling first loses the thin grass ticks):
   solid grey = asphalt, yellow = new concrete, no strokes in 5 m = paving, else grass. Embed the
   JPEG as a data URI (file:// viewer cannot load external textures into WebGL).
4. `assemble_site.py` builds the scene: `V()`/`prism()` take a site offset `OX/OY`, each detailed
   block is pasted **unchanged** inside its own `{ }` scope with `OX,OY` = its footprint min corner
   (= grid 1 / grid A). Units: site plan in **metres**, building DWGs in **mm**.
5. Views: aerials (`sh` ≈ 650 shadow frame), birdseye on the new cluster, close-ups of relocated
   buildings, street level; tour = aerial → roofs → along real roads → eye level → aerial.

### Site-scale pitfalls (all hit on Project A)
- **The master-plan hatch of a new building is often CONCEPTUAL** (Project A 06B: blue dashed hatch
  ≠ real building). Real outlines = Revit A-WALL lines of the building's own background block
  (e.g. `…06B-ZZ-M3-A-0001_rvt-1-…` inside an E-sheet), moved into the site frame by the offset that
  makes an already-placed building land on the master plan (Project A T = (−4.33, −7.44)); check
  areas against the A-2001 area table (LBY 24×48.2 = 1 157 m² ✓). A "clash" with the hatch may be
  roof/overhang only - compare A-WALL vs A-ROOF-OTLN before moving anything.
- Relocations: **move as little as possible** - architects already planned roads/paths around the
  plot. Keep the master-plan position and orientation (parallel to neighbours), shift only enough
  for the required clearance (057: +0.11 m so CDUs are 2.0 m from the real wall). Never move a
  building to "somewhere free" without the user's OK.
- A-2001 also carries Revit `…rvt-1-site plan` blocks (inserted at 0,0 = site frame) for small
  buildings (04B, M01, M02, UD1) - read their A-230-M_FLOOR lines for real outlines.
- **Model every building of the package table** (code, height) as its own block with a `code`,
  even "–"/as-existing ones; demolish existing footprints that fall inside a new real outline.
- **Show/hide per building**: tag meshes (`markAll()` before / `tagFrom(mark, code)` after each
  block), merge per *tag + material* (never across buildings), toggle merged meshes only, make
  walk collision / ground raycast skip hidden tags. Viewer panel (top-right, key **B** unlocks the
  mouse), `?hide=EXIST` in render mode, views can carry `hide:[…]`, `codes:true` (code sprites with
  `sizeAttenuation:false`).
- Combining blocks: each block must loop only its own fixtures (`fx.slice(n0)`), else NaN boxes.
- **No per-fixture RectAreaLights at site scale**: 68 lights × every material crashed the GPU
  process; the built-in browser then disables WebGL until the app restarts → render in the
  user's Chrome via the extension (`http://127.0.0.1:8765`), saves still go to the local server.
- Z-fighting at 1 km: outer grass at −1.5 m and camera `near` by height (aerial 5 m, close 0.1 m).
- Shots must `await window._groundReady` (big data-URI texture decodes async → black ground).
- Merge meshes in render mode too (`mergeStaticRender`, 7 435 → 55) or 60 fps video crawls.
- Day fill: hemi 1.05 / env .85 - asphalt in the shadow of 16 m halls otherwise reads black.
- 4K `shootAll` blocks the page > 45 s: start it, then wait on the files with an until-loop.
- Walk-mode merge must split multi-material meshes by geometry group (extruded buildings
  `[roof, wall]`) or the merged mesh draws NOTHING - and **always look at a walk-mode screenshot**,
  a passing collision test does not prove anything is drawn.
- progeCAD: open sources read-only and close **only the documents you opened** (by FullName) -
  never a close-all loop; the user may have unsaved drawings open.

### Detailed hall + MEPF from a tender set (Project A 06B, scripts in `scripts/mep/`)
- **Read big sheets as DXF, not via COM enumeration**: COM `foreach ModelSpace` on a 17-45 MB
  Revit export can take > 10 min; `to_dxf.ps1` (open read-only → `SaveAs` .dxf in scratch → close)
  takes ~20 s, then parse with `ezdxf` (`mepdxf.py`). Never open a sheet the user has open - read
  the open document instead (`mep_dump.ps1` reuses it and never closes it).
- **Frames**: ARC sheets (A-2001/RF/M1) were already in site metres; Revit-exported MEP sheets
  (E/H/F/P, mm) are in the Revit frame → site = revit/1000 + (−4.321, −7.490) (fit from grid lines).
  Some sheets put a view elsewhere (F-2106 local x, under-platform views shifted 81 m) → align each
  DXF by **matching its grid lines to the reference grid** (`shift()` in `build06b.py`).
- Pipes/ducts are **double lines**: pair parallel lines (overlap > 60 %, gap 20-260 mm) → centreline
  + diameter; elevation = nearest `COP/BOP/BOD: FFL nnnn` label (default per sheet / zone).
- Fabric ducts / AHUs are blocks: footprint = `ezdxf.bbox.extents(insert.virtual_entities())`.
- Read sections for levels (GFL / MCC +4.4 / AHU +5.9 / eave +13.2 / TOF +15.9), gable ridge on the
  ridge-vent grid, canopy from the section (roof +10.1 → +8.9) and its columns from the GF plan;
  canopy WP fittings **surface-mounted to the canopy underside (no rods)**; high-bays hang from the
  lighting trunking (BOT from the tray sheet). Floor slab inside every block (else grass shows).
- Tour: a `t`-window with `groups.roof.visible = false` gives a MEPF fly-over in the video.

## Deliverable package (what the user expects in `3D Models\`)

```
<bldg>_3D.dwg            3D model, one layer per element type
<source sheets>.pdf      the drawings used (PDF only unless asked for DWG too)
build_<bldg>.ps1         script that rebuilds the model
Renders\4K\*.png         renders (ask 1080p vs 4K; user kept only 4K last time)
Walkthrough\             <bldg>_walkthrough.mp4 + <bldg>_Viewer.html (WASD viewer)
render-source\           index.html + render_server.py to re-render
```

User preferences seen so far: keeps only the 4K renders (deletes 1080p), wants the source
drawings as **PDF only** in the package (no duplicate DWG), replies in Vietnamese.

End the reply with: what was read from which sheet, assumptions to confirm (roof fall, partition
types, heights inferred), and counts (fixtures, doors, louvres) so the user can check them.
