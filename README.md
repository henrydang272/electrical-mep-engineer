# Electrical MEP Engineer (Claude Code plugin)

Skills for electrical / ELV tender quantity work on CAD drawings (Windows, progeCAD 2026 COM, Excel, Python 3).

| Skill | What it does |
|---|---|
| `cad-qto` | Count devices (lights, switches, sockets, fire alarm, CCTV, data, PA, panels...) on electrical/ELV DWGs, build the quantity workbook, fill the bidder column of a BOQ copy. |
| `schedule-of-load` | Build the Schedule of Load workbook (PARAM, SOL, PANEL_REG, SUMMARY, QA_LOG) from single-line diagrams and the load list; SUMMARY totals cables and conduits. |
| `cable-estimate` | Route each SOL circuit along the tray centre-lines to its loads, fill Hor./Ver./conduit columns, draw the routes on per-panel layer groups in progeCAD. Starts with a thorough read of specs, standards and typical installation details - every project is taken off differently. |
| `cad-3d-render` | Build a 3D model of a building and its services from 2D drawings in progeCAD and produce renders, a walkthrough video and a browser walk viewer. |

## Install

```
/plugin marketplace add henrydang272/electrical-mep-engineer
/plugin install electrical-mep-engineer@electrical-mep-engineer
```

## Notes
- Project-specific examples (configs, worked data, per-building scripts) from the projects these skills were
  developed on are **not** included; files referenced as `example_projectA*` / `projectA_*` are placeholders.
- `cable-estimate/scripts/cad/*.dll` are prebuilt progeCAD .NET plugins; sources are next to them
  (`references/plugins.md` has the build command).
- Requirements: progeCAD (COM `Icad.Application`), Microsoft Excel, Python 3 with `openpyxl`, `PyMuPDF`, `networkx`, `ezdxf`, `matplotlib`.

License: MIT.
