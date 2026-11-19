# progeCAD .NET plugins (scripts/cad)

Prebuilt for progeCAD 2026 (Teigha/IntelliCAD 24.12). Load with `NETLOAD` + full path (via COM:
`doc.SendCommand("NETLOAD`n<path>\CtDraw2.dll`n")`). Rebuild after a progeCAD upgrade:

```
C:\Windows\Microsoft.NET\Framework64\v4.0.30319\csc.exe /t:library /out:CtDraw2.dll ^
  /r:"C:\Program Files\PSOFT\progeCAD 2026 Professional ENG\TD_Mgd_24.12_17.dll" ^
  /r:"C:\Program Files\PSOFT\progeCAD 2026 Professional ENG\IcMgd_24.12_17.dll" CtDraw2.cs
```
(csc v4 = C# 5: no `$""` strings, no `?.`; keep string literals on one line.)

| Command | Input | Does |
|---|---|---|
| `CTDRAW2 <tsv>` | lines `group<TAB>layer<TAB>aci<TAB>x,y x,y ...` | 2D polylines; creates layer + puts it in layer group `group` |
| `CTCOPYD src.dwg\|lay1,lay2\|dx,dy` | open source doc name, layers, displacement | WblockCloneObjects of those layers' entities into the current drawing, moved by (dx,dy) - tray + QPM panel tags |
| `CTCLEARL a\|b\|...` | layer names | erase entities on those layers. Unreliable for long input - for redo, delete via COM (iterate ModelSpace backwards) |
| `CtExport3 <tsv>` | output path | model-space dump: lines/polylines with points, blocks as extents box + block name (symbol centres) |
| `LAYGROUPS <spec>` | lines `group<TAB>layer<TAB>aci` | create layers + layer groups only |

COM quirks: `AddLightWeightPolyline` raises a type error from PowerShell - use the plugin. Wait for
`GetVariable('CMDACTIVE') -eq 0` after each SendCommand before Save.
