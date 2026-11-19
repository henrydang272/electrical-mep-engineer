# qto_config.json - the project file you write

One JSON file per project holds everything project-specific. The scripts never contain
project knowledge. A worked example (MASCOT GIA LAI, trimmed) is in
`assets/example_config.json`.

## Top level

| key | what |
|---|---|
| `project`, `title` | names printed on the workbook |
| `workdir` | work folder (extract/, out/, dxf/, render/). Keep the path short. |
| `output_xlsx` | the ONE take-off workbook, rewritten in place on every run |
| `legend_sheet` | name of the legend drawing, quoted in the method notes |
| `sheet_name_regex` | regex with named groups `zone`, `level`, `series` read from the drawing file name |
| `zones`, `levels` | code → display name |
| `systems_by_folder` | sub-folder → system name (checked first) |
| `systems_by_series` | series prefix → system name; the LONGEST matching key wins (`"2041"` beats `"20"`) |
| `systems_by_file` | `[{"file": regex, "system": ...}]`, checked before folder and series |
| `exclude_boxes` | symbol tables drawn in model space (see below) |
| `pictures` | options of `qto_pictures.py`: `device_layers`, `legend_sheets`, `area_min_pad_mm` |
| `sheet_roles` | ordered rules, first match wins, default `layout` (see below) |
| `legend` | code → `{"vi": ..., "en": ...}` copied from the legend sheet, verbatim |
| `code_order`, `group_order` | column order in the summary sheet |
| `exclude` | extra structural exclusions (see below) |
| `blocks`, `tags`, `group_notes`, `suffix_markers` | the counting rules |
| `extra_devices` | glob(s), relative to the config file, of CSVs from custom detectors |
| `dedup` | tolerances (defaults are the tested ones) |
| `method_notes` | list of project-specific sentences for the method sheet (sources chosen, RFIs) |

## sheet_roles

Only `layout` sheets are counted by block and tag rules. Everything else - legend,
schedule (SLDs, panel schedules), detail - is read but not counted unless a rule says
`"roles": ["schedule"]`.

```json
"sheet_roles": [
  {"file": "~|MSB|Main Single Line|General notes", "role": "schedule"},
  {"zone": "XX", "series": "^1", "role": "legend"},
  {"series": "^1", "role": "schedule"},
  {"series": "^6", "role": "detail"},
  {"zone": "XX", "level": "XX", "role": "legend"},
  {"series": "^00", "role": "detail"}
]
```
Keys in one rule must all match: `file` (regex on file name), `series` (regex),
`zone`, `level` (exact), `folder` (regex on sub-folder).

## exclude

Defaults already drop grids, title blocks, section/level heads, north arrows, revision
clouds, legends, "symbol" families, and layers containing S-GRID, TTLB, -NPLT,
DEFPOINTS, G-ANNO, REVC. Add to them, or rescue a real device:
```json
"exclude": {"family_keep": ["Symbol Sampling Smoke Detector"],
            "family_contains": ["dim-"], "layer_contains": ["X-REF"]}
```

## blocks - first matching rule wins

```json
{"family": "^HAS_E_Socket-Duplex", "type": "^S2$", "code": "S2", "group": "Ổ cắm"}
{"family": "^HAS_Philips-BN398C LED L1200_Workshop$", "code": "LN1-WS", "group": "Đèn chiếu sáng",
 "vi": "ĐÈN BATTEN LED 29W ... (LN1) — nhà xưởng"}
{"family": "^HAS_E_Isolator", "code": "ISO", "group": "Isolator / Cầu dao",
 "vi": "CẦU DAO CÁCH LY, CÓ HỘP BẢO VỆ — {type}"}
{"family": "^FL2$", "code": "LF1", "group": "Đèn chiếu sáng",
 "drop_scale_below": 1.0, "code_from_tags": ["LF1", "LF2"]}
{"family": "^63_PHILIPS_Coreline_tempo_large", "exclude": "nét bao chi tiết vẽ chồng lên đèn LF"}
```
| field | meaning |
|---|---|
| `family`, `type` | regex on the parsed Revit family / type (type is case-insensitive). Omit `type` to match any. |
| `layer`, `sheets`, `zones` | optional filters: layer regex, file-name regex, list of zone codes |
| `code`, `group` | legend code and summary group |
| `vi`, `en` | override the legend name. `{type}` / `{family}` are substituted - use it when one legend row covers several priced ratings (isolators, manholes). |
| `exclude` | a reason string: the family is not a device. Always give the reason. |
| `drop_scale_below` | drop inserts whose x-scale is below this (legend symbols in model space) |
| `code_from_tags` | the nearest of these tags on the same sheet decides the code |

Put specific rules (with `sheets`/`type`) before general ones.

## tags - devices that are only a text label

```json
{"text": "^SW1$", "code": "SW1", "group": "Công tắc"}
{"text": "^ISW$", "zones": ["02", "03"], "code": "ISW", "group": "Isolator / Cầu dao"}
{"text": "^IS$", "layer": "EE-SO-EQUI", "roles": ["schedule"], "sheets": "-01-XX-DR-E-1111",
 "code": "ISW-WS", "group": "Isolator / Cầu dao"}
```
`text` is a case-insensitive regex on the whole label; `layer` defaults to `IDEN`;
`roles` defaults to `["layout"]`. Tags go through de-duplication like blocks.

## group_notes - "11x ISW"

```json
{"pattern": "^(\\d+)\\s*x\\s*ISW$", "code": "ISW", "zones": ["02", "03"],
 "circuit_range": true, "group": "Isolator / Cầu dao"}
```
Group 1 of `pattern` is the quantity. `circuit_range: true` reads a range such as
`4-S16 ~ 4-S26` printed within 3 m and takes its count when it disagrees. Notes are added
after de-duplication; an identical note at the same spot on another sheet is dropped.

## suffix_markers - variants written beside a device

```json
{"marker": "^\\(?WP\\)?$", "base_code": "S2", "code": "S2-wp", "group": "Ổ cắm",
 "vi": "Ổ CẮM ĐÔI ... — VỎ BẢO VỆ CHỐNG NƯỚC (S2-wp)"}
```
For each marker on a sheet one `base_code` device on that sheet is re-coded; markers
beyond the number of drawn devices become devices of their own (the note is then the
only evidence). Only the count per sheet is claimed, not which device.

## extra_devices - custom detectors

CSV with at least `dwg, code, group, device_vi, x, y` (and optionally `qty`, `zone`,
`lvl`, `device_en`, `fam`, `typ`, `attrs`, `layer`). If `dwg` matches a converted sheet,
zone/level/system are filled from it. Rows are added after de-duplication, so the
detector must de-duplicate its own results across overall and part sheets.

## exclude_boxes - symbol tables drawn in model space

```json
"exclude_boxes": [{"sheets": "-000-00-DR-E-2000$", "box": [820000, 120000, 930000, 230000],
                   "reason": "bảng ký hiệu (SYMBOL/DESCRIPTION) vẽ trong model space"}]
```
A legend table drawn next to the plan holds real device blocks at plan scale, so neither the
insert-scale filter nor de-duplication removes them. Every counted device (block, tag, note,
extra CSV) inside a box is dropped and listed in `count_report.json` (`box_dropped`). Find the
box from the SYMBOL / DESCRIPTION header texts and a picture of the table.

## dedup (defaults shown)

```json
"dedup": {"tol_mm": 50, "offset_match_tol": 600, "offset_match_frac": 0.8,
          "sheet_count_tol": 0.10, "sheet_overlap_max": 0.20,
          "keyplan_box_mm": 2000, "keyplan_origin_mm": 5000,
          "note_dedup_mm": 2500, "note_range_reach_mm": 3000}
```
